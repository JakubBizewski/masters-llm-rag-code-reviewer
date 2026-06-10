#!/usr/bin/env python3
"""Aggregate ACR evaluation JSON reports into a comparison table.

Usage:
    python exp/aggregate_reports.py [DIR]

DIR defaults to the directory containing this script.

Report files are expected in subdirectories named after the repository:
    <DIR>/<repo>/pr<NUMBER>_rag.json
    <DIR>/<repo>/pr<NUMBER>_no_rag.json

For example:
    exp/sentry/pr123_rag.json
    exp/vscode/pr11222_no_rag.json
    exp/home-assistant/pr12345_rag.json

The script outputs:
  - A human-readable comparison table to stdout
  - aggregate_results.csv  — flat table of all rows
  - aggregate_results.json — structured report with per-PR comparisons,
    aggregated statistics (by mode and by repository), and expert evaluation
    placeholders ready to be filled in manually.
"""
from __future__ import annotations

import csv
import datetime
import json
import sys
from pathlib import Path


def load_report(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def extract_row(report: dict, mode: str) -> dict:
    """Return metrics dict with native Python types (int / float / None)."""
    timings = report.get("timings", {})
    costs = report.get("token_costs", {})
    metrics = report.get("metrics_summary", {})
    loc = metrics.get("change_localization", {})

    llm_prompt = costs.get("llm_prompt_tokens", 0)
    llm_completion = costs.get("llm_completion_tokens", 0)
    emb_index = costs.get("embedding_index_tokens", 0)
    emb_review = costs.get("embedding_review_tokens", 0)

    def _r(v):
        return round(v, 4) if v is not None else None

    return {
        "repository": report.get("repository", ""),
        "pr_number": report.get("pr_number", ""),
        "mode": mode,
        "used_indexed_knowledge": report.get("used_indexed_knowledge", 0),
        "indexing_s": round(timings.get("indexing_seconds", 0.0), 2),
        "review_s": round(timings.get("review_seconds", 0.0), 2),
        "total_s": round(
            timings.get("indexing_seconds", 0.0) + timings.get("review_seconds", 0.0), 2
        ),
        "llm_prompt_tokens": llm_prompt,
        "llm_completion_tokens": llm_completion,
        "embedding_index_tokens": emb_index,
        "embedding_review_tokens": emb_review,
        "total_tokens": llm_prompt + llm_completion + emb_index + emb_review,
        "generated_comments": metrics.get("generated_count", 0),
        "reference_comments": metrics.get("reference_count", 0),
        "exact_match_rate": _r(metrics.get("exact_match_rate")),
        "bleu4_mean": _r(metrics.get("bleu4_mean")),
        "rougeL_f1_mean": _r(metrics.get("rougeL_f1_mean")),
        "meteor_mean": _r(metrics.get("meteor_simplified_mean")),
        "semantic_sim_mean": _r(metrics.get("semantic_similarity_mean")),
        "bertscore_f1_mean": _r(metrics.get("bertscore_f1_mean")),
        "gen_file_in_diff_rate": _r(loc.get("generated_file_in_diff_rate")),
        "gen_line_in_hunk_rate": _r(loc.get("generated_line_in_hunk_rate")),
    }


def _fmt(v) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def find_pairs(report_dir: Path) -> list[tuple[Path | None, Path | None, str]]:
    """Return [(rag_path, no_rag_path, label)] grouped by repo/pr.

    Scans one level of subdirectories: <report_dir>/<repo>/pr<N>_[no_]rag.json.
    Label is '<repo>/pr<N>', e.g. 'sentry/pr123'.
    """
    rag_files: dict[str, Path] = {}
    no_rag_files: dict[str, Path] = {}

    for f in sorted(report_dir.glob("*/*.json")):
        repo = f.parent.name
        name = f.stem
        if name.endswith("_no_rag"):
            key = f"{repo}/{name[: -len('_no_rag')]}"
            no_rag_files[key] = f
        elif name.endswith("_rag"):
            key = f"{repo}/{name[: -len('_rag')]}"
            rag_files[key] = f

    all_keys = sorted(set(rag_files) | set(no_rag_files))
    return [(rag_files.get(k), no_rag_files.get(k), k) for k in all_keys]


# ---------------------------------------------------------------------------
# Console display helpers
# ---------------------------------------------------------------------------

def print_comparison(rag_row: dict | None, no_rag_row: dict | None, label: str) -> None:
    repo = (rag_row or no_rag_row or {}).get("repository", label)
    pr = (rag_row or no_rag_row or {}).get("pr_number", "?")
    print(f"\n{'='*60}")
    print(f"  {repo}  PR #{pr}")
    print(f"{'='*60}")

    metrics_to_compare = [
        ("total_s",               "Total time (s)"),
        ("review_s",              "Review time (s)"),
        ("total_tokens",          "Total tokens"),
        ("llm_prompt_tokens",     "LLM prompt tokens"),
        ("llm_completion_tokens", "LLM completion tokens"),
        ("generated_comments",    "Generated comments"),
        ("reference_comments",    "Reference comments"),
        ("bleu4_mean",            "BLEU-4"),
        ("rougeL_f1_mean",        "ROUGE-L F1"),
        ("meteor_mean",           "METEOR"),
        ("semantic_sim_mean",     "Semantic similarity"),
        ("bertscore_f1_mean",     "BERTScore F1"),
        ("gen_file_in_diff_rate", "Comment file in diff"),
        ("gen_line_in_hunk_rate", "Comment line in hunk"),
    ]

    col_label, col_val = 22, 14
    print(f"{'Metric':<{col_label}}  {'RAG':>{col_val}}  {'No RAG':>{col_val}}")
    print(f"{'-'*col_label}  {'-'*col_val}  {'-'*col_val}")
    for key, display in metrics_to_compare:
        rag_val   = _fmt(rag_row[key])   if rag_row   else "—"
        no_rag_val = _fmt(no_rag_row[key]) if no_rag_row else "—"
        print(f"{display:<{col_label}}  {rag_val:>{col_val}}  {no_rag_val:>{col_val}}")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

_NUMERIC_KEYS = [
    "indexing_s", "review_s", "total_s",
    "total_tokens", "llm_prompt_tokens", "llm_completion_tokens",
    "embedding_index_tokens", "embedding_review_tokens",
    "used_indexed_knowledge",
    "generated_comments", "reference_comments",
]
_FLOAT_METRIC_KEYS = [
    "exact_match_rate", "bleu4_mean", "rougeL_f1_mean", "meteor_mean",
    "semantic_sim_mean", "bertscore_f1_mean",
    "gen_file_in_diff_rate", "gen_line_in_hunk_rate",
]


def _compute_averages(rows: list[dict]) -> dict:
    result: dict = {"n": len(rows)}
    for k in _NUMERIC_KEYS:
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        result[k] = round(sum(vals) / len(vals), 4) if vals else None
    for k in _FLOAT_METRIC_KEYS:
        vals = [r[k] for r in rows if r.get(k) is not None]
        result[k] = round(sum(vals) / len(vals), 4) if vals else None
    return result


# ---------------------------------------------------------------------------
# Expert-evaluation placeholder
# ---------------------------------------------------------------------------

# Fields to be filled in manually after human inspection of generated comments.
_EXPERT_EVAL_TEMPLATE: dict = {
    # Ogólna ocena jakości komentarzy (1 = bardzo słaba, 5 = doskonała)
    "comment_quality_score": None,
    # Liczba komentarzy, które sygnalizują nieistniejące problemy (false positive)
    "false_positives_count": None,
    # Liczba realnych problemów pominiętych przez recenzenta (false negative)
    "false_negatives_count": None,
    # Czy komentarze są zbyt generyczne (brak konkretnego kontekstu)?
    "too_generic": None,
    # Czy komentarze są poparte faktami z kodu / dokumentacji?
    "fact_backed": None,
    # Czy wszystkie istotne problemy zostały wykryte?
    "all_problems_covered": None,
    # Dowolne uwagi eksperta
    "notes": "",
}


# ---------------------------------------------------------------------------
# JSON report builder
# ---------------------------------------------------------------------------

def build_json_report(
    row_pairs: list[tuple[dict | None, dict | None, str]],
    all_rows: list[dict],
) -> dict:
    """Build the full structured JSON report."""
    per_pr = []
    for rag_row, no_rag_row, label in row_pairs:
        repo = (rag_row or no_rag_row or {}).get("repository", label.split("/")[0])
        pr_number = (rag_row or no_rag_row or {}).get("pr_number", "")
        per_pr.append({
            "repository": repo,
            "pr_number": pr_number,
            "label": label,
            "metrics": {
                "rag": rag_row,
                "no_rag": no_rag_row,
            },
            "expert_evaluation": {
                "rag": dict(_EXPERT_EVAL_TEMPLATE),
                "no_rag": dict(_EXPERT_EVAL_TEMPLATE),
                "overall_notes": "",
            },
        })

    repos = sorted({r["repository"] for r in all_rows})
    rag_rows    = [r for r in all_rows if r["mode"] == "rag"]
    no_rag_rows = [r for r in all_rows if r["mode"] == "no_rag"]

    aggregated = {
        "by_mode": {
            "rag":    _compute_averages(rag_rows),
            "no_rag": _compute_averages(no_rag_rows),
        },
        "by_repository": {
            repo: {
                "rag":    _compute_averages([r for r in rag_rows    if r["repository"] == repo]),
                "no_rag": _compute_averages([r for r in no_rag_rows if r["repository"] == repo]),
            }
            for repo in repos
        },
    }

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "repositories": repos,
        "total_prs": len(per_pr),
        "per_pr": per_pr,
        "aggregated": aggregated,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) >= 2:
        report_dir = Path(sys.argv[1])
    else:
        report_dir = Path(__file__).parent

    if not report_dir.is_dir():
        print(f"Error: {report_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    pairs = find_pairs(report_dir)
    if not pairs:
        print(f"No report pairs found in {report_dir}.")
        print("Expected: <repo>/pr<N>_rag.json and <repo>/pr<N>_no_rag.json")
        sys.exit(1)

    all_rows: list[dict] = []
    row_pairs: list[tuple[dict | None, dict | None, str]] = []

    for rag_path, no_rag_path, label in pairs:
        rag_row    = extract_row(load_report(rag_path),    "rag")    if rag_path    else None
        no_rag_row = extract_row(load_report(no_rag_path), "no_rag") if no_rag_path else None

        print_comparison(rag_row, no_rag_row, label)

        row_pairs.append((rag_row, no_rag_row, label))
        if rag_row:
            all_rows.append(rag_row)
        if no_rag_row:
            all_rows.append(no_rag_row)

    if not all_rows:
        return

    # CSV — flat table
    csv_path = report_dir / "aggregate_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    # JSON — full structured report
    json_report = build_json_report(row_pairs, all_rows)
    json_path = report_dir / "aggregate_results.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    print(f"\n\nCSV written to:  {csv_path}")
    print(f"JSON written to: {json_path}")

    # Console averages summary
    print("\n\n=== AVERAGES BY MODE ===")
    for mode in ("rag", "no_rag"):
        avgs = _compute_averages([r for r in all_rows if r["mode"] == mode])
        n = avgs.pop("n")
        if n == 0:
            continue
        print(f"\n  Mode: {mode.upper()}  (n={n} PRs)")
        for k, v in avgs.items():
            display = _fmt(v)
            print(f"    {k:<35} avg = {display}")


if __name__ == "__main__":
    main()
