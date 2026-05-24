#!/usr/bin/env bash
# Run RAG and no-RAG ACR evaluations for every PR URL listed in pr_urls.txt.
#
# Usage:
#   ./exp/run_experiment.sh [pr_urls.txt]
#
# Defaults:
#   pr_urls.txt   — one GitHub PR URL per line, relative to the project root
#   Output files are placed next to this script in exp/<repo-dir>/
#
# File naming:
#   pr<NUMBER>_rag.json / pr<NUMBER>_rag.log
#   pr<NUMBER>_no_rag.json / pr<NUMBER>_no_rag.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

URLS_FILE="${1:-$PROJECT_ROOT/pr_urls.txt}"

if [[ ! -f "$URLS_FILE" ]]; then
  echo "Error: URL file not found: $URLS_FILE" >&2
  echo "Create it with one GitHub PR URL per line, e.g.:" >&2
  echo "  https://github.com/home-assistant/core/pull/12345" >&2
  exit 1
fi

# ── repo → experiment config mapping ──────────────────────────────────────────
# Add a new line here if you add another repository to the experiment.
# Format:  ["owner/repo"]="<output-dir>|<rag-config>|<no-rag-config>|<faiss-index-path>"
declare -A REPO_CONFIG
REPO_CONFIG["home-assistant/core"]="$SCRIPT_DIR/home-assistant|$SCRIPT_DIR/home-assistant/.acr-config.yml|$SCRIPT_DIR/home-assistant/.acr-config-no-rag.yml|$PROJECT_ROOT/faiss_index_home_assistant"
REPO_CONFIG["microsoft/vscode"]="$SCRIPT_DIR/vscode|$SCRIPT_DIR/vscode/.acr-config.yml|$SCRIPT_DIR/vscode/.acr-config-no-rag.yml|$PROJECT_ROOT/faiss_index_vscode"

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

while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip blank lines and comments
  [[ -z "$line" || "$line" == \#* ]] && continue

  pr_url="$line"
  repo="$(extract_repo "$pr_url")"
  pr_number="$(extract_pr_number "$pr_url")"

  if [[ -z "$repo" || -z "$pr_number" ]]; then
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
    "$out_dir/pr${pr_number}_rag.json" \
    "$out_dir/pr${pr_number}_rag.log" \
    "RAG" || pr_failed=1

  run_eval \
    "$pr_url" \
    "$cfg_no_rag" \
    "$faiss_path" \
    "$out_dir/pr${pr_number}_no_rag.json" \
    "$out_dir/pr${pr_number}_no_rag.log" \
    "no-RAG" || pr_failed=1

  if [[ $pr_failed -eq 0 ]]; then
    ((succeeded++)) || true
  else
    ((failed++)) || true
  fi

done < "$URLS_FILE"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done: $total PRs processed — $succeeded succeeded, $failed failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
