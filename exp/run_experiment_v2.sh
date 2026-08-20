#!/usr/bin/env bash
# v2 experiment runner — runs RAG and no-RAG ACR evaluations for the PR URLs
# listed in the per-repo pr_urls2.txt files.
#
# Usage:
#   ./exp/run_experiment_v2.sh                      # all exp/*/pr_urls2.txt
#   ./exp/run_experiment_v2.sh exp/vscode/pr_urls2.txt [more_urls.txt ...]
#   FORCE=1 ./exp/run_experiment_v2.sh              # re-run and overwrite reports
#
# Differences vs run_experiment.sh (v1):
#   * URL lists live next to each repo's config (exp/<repo-dir>/pr_urls2.txt)
#     and all of them are picked up by default.
#   * Existing report files are never overwritten — such PRs are skipped
#     unless FORCE=1 is set.
#
# File naming (unchanged):
#   pr<NUMBER>[<OUT_SUFFIX>]_rag.json / .log
#   pr<NUMBER>[<OUT_SUFFIX>]_no_rag.json / .log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

URLS_GLOB_NAME="pr_urls2.txt"
FORCE="${FORCE:-0}"
# Optional suffixes for A/B re-runs:
#   FAISS_SUFFIX=_v2      -> use faiss_index_<repo>_v2 instead of faiss_index_<repo>
#   OUT_SUFFIX=_tuned     -> write pr<N>_tuned_rag.json instead of pr<N>_rag.json
# The suffix is inserted before _rag/_no_rag so exp/aggregate_reports.py still
# pairs the two modes, while the label keeps the two runs apart.
FAISS_SUFFIX="${FAISS_SUFFIX:-}"
OUT_SUFFIX="${OUT_SUFFIX:-}"

# ── repo → experiment config mapping ──────────────────────────────────────────
# Add a new line here if you add another repository to the experiment.
# Format:  ["owner/repo"]="<output-dir>|<rag-config>|<no-rag-config>|<faiss-index-path>"
declare -A REPO_CONFIG
REPO_CONFIG["home-assistant/core"]="$SCRIPT_DIR/home-assistant|$SCRIPT_DIR/home-assistant/.acr-config.yml|$SCRIPT_DIR/home-assistant/.acr-config-no-rag.yml|$PROJECT_ROOT/faiss_index_home_assistant${FAISS_SUFFIX}"
REPO_CONFIG["microsoft/vscode"]="$SCRIPT_DIR/vscode|$SCRIPT_DIR/vscode/.acr-config.yml|$SCRIPT_DIR/vscode/.acr-config-no-rag.yml|$PROJECT_ROOT/faiss_index_vscode${FAISS_SUFFIX}"
REPO_CONFIG["getsentry/sentry"]="$SCRIPT_DIR/sentry|$SCRIPT_DIR/sentry/.acr-config.yml|$SCRIPT_DIR/sentry/.acr-config-no-rag.yml|$PROJECT_ROOT/faiss_index_sentry${FAISS_SUFFIX}"

# ── collect URL files ─────────────────────────────────────────────────────────
URL_FILES=()
if [[ $# -gt 0 ]]; then
  URL_FILES=("$@")
else
  while IFS= read -r f; do
    URL_FILES+=("$f")
  done < <(find "$SCRIPT_DIR" -mindepth 2 -maxdepth 2 -name "$URLS_GLOB_NAME" | sort)
fi

if [[ ${#URL_FILES[@]} -eq 0 ]]; then
  echo "Error: no $URLS_GLOB_NAME files found under $SCRIPT_DIR" >&2
  echo "Create one per repository, e.g. exp/vscode/$URLS_GLOB_NAME, with one PR URL per line." >&2
  exit 1
fi

for f in "${URL_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Error: URL file not found: $f" >&2
    exit 1
  fi
done

# ── helpers ────────────────────────────────────────────────────────────────────
extract_repo() {
  # https://github.com/owner/repo/pull/123  →  owner/repo
  echo "$1" | sed -E 's|https://github\.com/([^/]+/[^/]+)/pull/.*|\1|'
}

extract_pr_number() {
  # https://github.com/owner/repo/pull/123  →  123
  echo "$1" | sed -E 's|.*/pull/([0-9]+).*|\1|'
}

run_eval() {
  local pr_url="$1"
  local config="$2"
  local faiss_path="$3"
  local report="$4"
  local log="$5"
  local label="$6"

  if [[ -e "$report" && "$FORCE" != "1" ]]; then
    echo "  [$label] SKIP — report already exists: $report"
    ((skipped++)) || true
    return 0
  fi

  echo "  [$label] $pr_url"
  echo "  [$label] report → $report"

  acr evaluate \
    --pr-url "$pr_url" \
    --config-path "$config" \
    --faiss-index-path "$faiss_path" \
    --skip-indexing \
    --report-path "$report" \
    2>&1 | tee "$log"

  local exit_code="${PIPESTATUS[0]}"
  if [[ $exit_code -ne 0 ]]; then
    echo "  [$label] FAILED (exit $exit_code) — see $log" >&2
  else
    echo "  [$label] done"
  fi
  return $exit_code
}

# ── main loop ──────────────────────────────────────────────────────────────────
total=0
succeeded=0
failed=0
skipped=0

for urls_file in "${URL_FILES[@]}"; do
  echo ""
  echo "############################################################"
  echo "  URL list: $urls_file"
  echo "############################################################"

  while IFS= read -r line || [[ -n "$line" ]]; do
    # Strip trailing CR (files edited on Windows) and surrounding whitespace
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"

    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue

    pr_url="$line"
    repo="$(extract_repo "$pr_url")"
    pr_number="$(extract_pr_number "$pr_url")"

    if [[ -z "$repo" || -z "$pr_number" || "$repo" == "$pr_url" || "$pr_number" == "$pr_url" ]]; then
      echo "Skipping unrecognised line: $line" >&2
      continue
    fi

    if [[ -z "${REPO_CONFIG[$repo]+_}" ]]; then
      echo "No config mapping for repo '$repo' — add it to REPO_CONFIG in this script." >&2
      ((failed++)) || true
      continue
    fi

    IFS='|' read -r out_dir cfg_rag cfg_no_rag faiss_path <<< "${REPO_CONFIG[$repo]}"

    mkdir -p "$out_dir"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  repo=$repo  PR #$pr_number"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    ((total++)) || true
    pr_failed=0

    run_eval \
      "$pr_url" \
      "$cfg_rag" \
      "$faiss_path" \
      "$out_dir/pr${pr_number}${OUT_SUFFIX}_rag.json" \
      "$out_dir/pr${pr_number}${OUT_SUFFIX}_rag.log" \
      "RAG" || pr_failed=1

    run_eval \
      "$pr_url" \
      "$cfg_no_rag" \
      "$faiss_path" \
      "$out_dir/pr${pr_number}${OUT_SUFFIX}_no_rag.json" \
      "$out_dir/pr${pr_number}${OUT_SUFFIX}_no_rag.log" \
      "no-RAG" || pr_failed=1

    if [[ $pr_failed -eq 0 ]]; then
      ((succeeded++)) || true
    else
      ((failed++)) || true
    fi

  done < "$urls_file"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done: $total PRs processed — $succeeded succeeded, $failed failed"
echo "  Runs skipped (report existed): $skipped  (set FORCE=1 to re-run)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
