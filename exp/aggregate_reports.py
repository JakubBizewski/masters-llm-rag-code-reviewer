#!/usr/bin/env python3
"""Aggregate ACR evaluation JSON reports into a comparison table.

Usage:
    python exp/aggregate_reports.py ./reports/

Report files are expected to follow the naming convention:
    <repo_slug>_pr<NUMBER>_rag.json
    <repo_slug>_pr<NUMBER>_no_rag.json

For example:
    home_assistant_pr12345_rag.json
    home_assistant_pr12345_no_rag.json

The script outputs:
  - A human-readable comparison table to stdout
  - A CSV file (aggregate_results.csv) next to the reports directory
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def load_report(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def extract_row(report: dict, mode: str) -> dict:
    timings = report.get("timings", {})
    costs = report.get("token_costs", {})
    metrics = report.get("metrics_summary", {})
    loc = metrics.get("change_localization", {})

    llm_prompt = costs.get("llm_prompt_tokens", 0)
    llm_completion = costs.get("llm_completion_tokens", 0)
    emb_index = costs.get("embedding_index_tokens", 0)
    emb_review = costs.get("embedding_review_tokens", 0)
    total_tokens = llm_prompt + llm_completion + emb_index + emb_review

    return {
        "repository": report.get("repository", ""),
        "pr_number": report.get("pr_number", ""),
        "mode": mode,
        "indexed_prs": report.get("indexed_prs", 0),
        "indexing_s": round(timings.get("indexing_seconds", 0.0), 2),
        "review_s": round(timings.get("review_seconds", 0.0), 2),
        "total_s": round(timings.get("indexing_seconds", 0.0) + timings.get("review_seconds", 0.0), 2),
        "llm_prompt_tokens": llm_prompt,
        "llm_completion_tokens": llm_completion,
        "embedding_index_tokens": emb_index,
        "embedding_review_tokens": emb_review,
        "total_tokens": total_tokens,
        "generated_comments": metrics.get("generated_count", 0),
        "reference_comments": metrics.get("reference_count", 0),
        "exact_match_rate": _fmt(metrics.get("exact_match_rate")),
        "bleu4_mean": _fmt(metrics.get("bleu4_mean")),
        "rougeL_f1_mean": _fmt(metrics.get("rougeL_f1_mean")),
        "meteor_mean": _fmt(metrics.get("meteor_simplified_mean")),
        "semantic_sim_mean": _fmt(metrics.get("semantic_similarity_mean")),
        "bertscore_f1_mean": _fmt(metrics.get("bertscore_f1_mean")),
        "gen_file_in_diff_rate": _fmt(loc.get("generated_file_in_diff_rate")),
        "gen_line_in_hunk_rate": _fmt(loc.get("generated_line_in_hunk_rate")),
    }


def _fmt(v) -> str:
    if v is None:
        return "N/A"
    return f"{v:.4f}"


def find_pairs(report_dir: Path) -> list[tuple[Path | None, Path | None, str]]:
    """Return [(rag_path, no_rag_path, label)] pairs grouped by PR."""
    rag_files: dict[str, Path] = {}
    no_rag_files: dict[str, Path] = {}

    for f in sorted(report_dir.glob("*.json")):
        name = f.stem
        if name.endswith("_no_rag"):
            key = name[: -len("_no_rag")]
            no_rag_files[key] = f
        elif name.endswith("_rag"):
            key = name[: -len("_rag")]
            rag_files[key] = f

    all_keys = sorted(set(rag_files) | set(no_rag_files))
    return [(rag_files.get(k), no_rag_files.get(k), k) for k in all_keys]


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No rows to display.")
        return

    col_widths = {k: len(k) for k in rows[0]}
    for row in rows:
        for k, v in row.items():
            col_widths[k] = max(col_widths[k], len(str(v)))

    header = "  ".join(k.ljust(col_widths[k]) for k in rows[0])
    separator = "  ".join("-" * col_widths[k] for k in rows[0])
    print(header)
    print(separator)
    for row in rows:
        print("  ".join(str(row[k]).ljust(col_widths[k]) for k in row))


def print_comparison(rag_row: dict | None, no_rag_row: dict | None, label: str) -> None:
    repo = (rag_row or no_rag_row or {}).get("repository", label)
    pr = (rag_row or no_rag_row or {}).get("pr_number", "?")
    print(f"\n{'='*60}")
    print(f"  {repo}  PR #{pr}")
    print(f"{'='*60}")

    metrics_to_compare = [
        ("total_s", "Total time (s)"),
        ("review_s", "Review time (s)"),
        ("total_tokens", "Total tokens"),
        ("llm_prompt_tokens", "LLM prompt tokens"),
        ("llm_completion_tokens", "LLM completion tokens"),
        ("generated_comments", "Generated comments"),
        ("reference_comments", "Reference comments"),
        ("bleu4_mean", "BLEU-4"),
        ("rougeL_f1_mean", "ROUGE-L F1"),
        ("meteor_mean", "METEOR"),
        ("semantic_sim_mean", "Semantic similarity"),
        ("bertscore_f1_mean", "BERTScore F1"),
        ("gen_file_in_diff_rate", "Comment file in diff"),
        ("gen_line_in_hunk_rate", "Comment line in hunk"),
    ]

    col_label = 20
    col_val = 14
    print(f"{'Metric':<{col_label}}  {'RAG':>{col_val}}  {'No RAG':>{col_val}}")
    print(f"{'-'*col_label}  {'-'*col_val}  {'-'*col_val}")
    for key, display in metrics_to_compare:
        rag_val = str(rag_row[key]) if rag_row else "—"
        no_rag_val = str(no_rag_row[key]) if no_rag_row else "—"
        print(f"{display:<{col_label}}  {rag_val:>{col_val}}  {no_rag_val:>{col_val}}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    report_dir = Path(sys.argv[1])
    if not report_dir.is_dir():
        print(f"Error: {report_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    pairs = find_pairs(report_dir)
    if not pairs:
        print(f"No report pairs found in {report_dir}.")
        print("Expected files named: <label>_rag.json and <label>_no_rag.json")
        sys.exit(1)

    all_rows: list[dict] = []

    for rag_path, no_rag_path, label in pairs:
        rag_row = extract_row(load_report(rag_path), "rag") if rag_path else None
        no_rag_row = extract_row(load_report(no_rag_path), "no_rag") if no_rag_path else None

        print_comparison(rag_row, no_rag_row, label)

        if rag_row:
            all_rows.append(rag_row)
        if no_rag_row:
            all_rows.append(no_rag_row)

    if not all_rows:
        return

    csv_path = report_dir / "aggregate_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n\nCSV written to: {csv_path}")

    # Print summary averages per mode
    print("\n\n=== AVERAGES BY MODE ===")
    for mode in ("rag", "no_rag"):
        mode_rows = [r for r in all_rows if r["mode"] == mode]
        if not mode_rows:
            continue
        numeric_keys = [
            "indexing_s", "review_s", "total_s",
            "total_tokens", "llm_prompt_tokens", "llm_completion_tokens",
            "generated_comments",
        ]
        float_metric_keys = [
            "bleu4_mean", "rougeL_f1_mean", "meteor_mean",
            "semantic_sim_mean", "bertscore_f1_mean",
            "gen_file_in_diff_rate", "gen_line_in_hunk_rate",
        ]
        print(f"\n  Mode: {mode.upper()}  (n={len(mode_rows)} PRs)")
        for k in numeric_keys:
            vals = [float(r[k]) for r in mode_rows if str(r[k]).replace(".", "").isdigit()]
            avg = sum(vals) / len(vals) if vals else 0
            print(f"    {k:<30} avg = {avg:.2f}")
        for k in float_metric_keys:
            vals = [float(r[k]) for r in mode_rows if r[k] != "N/A"]
            avg = sum(vals) / len(vals) if vals else None
            display = f"{avg:.4f}" if avg is not None else "N/A"
            print(f"    {k:<30} avg = {display}")


if __name__ == "__main__":
    main()
