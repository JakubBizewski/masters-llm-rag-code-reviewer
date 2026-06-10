# ACR System — Automated Code Review

> An LLM-powered code review engine with Retrieval-Augmented Generation, AST-based impact analysis, and a rigorous evaluation pipeline — built on Clean/Hexagonal Architecture and validated against real-world open-source repositories.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-red.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://mypy.readthedocs.io/)

---

## What It Does

ACR fetches a GitHub or GitLab pull request, enriches it with semantic context from the repository's own history and documentation, then generates actionable review comments using an LLM of your choice. Comments are filtered by a configurable publish policy and posted back to the PR — or exported as a structured JSON report for offline evaluation.

```
PR URL ──► Diff + Metadata ──► Context Assembly ──► LLM ──► Filtered Comments ──► PR / Report
                                      │
                      ┌───────────────┴───────────────┐
                 FAISS Vector Search            Tree-sitter AST
               (similar code, past PRs,       (call graph, breaking
                 architectural docs)            change detection)
```

---

## Highlights

| Capability | Detail |
|---|---|
| **Multi-LLM** | OpenAI (GPT-4o) and Anthropic (Claude 3.5 Sonnet/Opus/Haiku), switchable per file pattern |
| **RAG pipeline** | FAISS-backed semantic search over repo docs, architectural ADRs, and past PR diffs |
| **AST analysis** | Tree-sitter call-graph analysis for Python, JS, TypeScript, and Go — detects breaking changes before the LLM sees the diff |
| **Dual VCS** | GitHub (App-authenticated) and GitLab (token), including CI result ingestion |
| **Publish policy** | Per-severity filtering, rule exclusions, regex suppression, and praise stripping |
| **Evaluation suite** | BLEU-4 · ROUGE-L · METEOR · BERTScore · semantic cosine similarity vs. human-authored reviews |
| **Evaluation at scale** | Benchmarked against real PRs from `home-assistant/core`, `getsentry/sentry`, and `microsoft/vscode` |
| **Architecture** | Clean Architecture + Hexagonal (Ports & Adapters) — every external dependency is behind an interface |

---

## Architecture

The system is split into four strict layers with all dependencies pointing inward.

```
┌─────────────────────────────────────────────────────┐
│  Presentation  │  FastAPI webhooks  │  Click CLI     │
├─────────────────────────────────────────────────────┤
│  Application   │  ProcessPullRequest  PublishReview  │
│  (Use Cases)   │  IndexPRHistory      EvaluatePR     │
├─────────────────────────────────────────────────────┤
│  Domain        │  Entities  Value Objects  Services  │
│  (Pure logic)  │  ReviewOrchestrator  ContextBuilder │
├─────────────────────────────────────────────────────┤
│  Infrastructure│  VCS · LLM · RAG · CI · AST · Auth │
│  (Adapters)    │  GitHub  GitLab  OpenAI  Anthropic  │
└─────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Factory + Strategy** — `LLMProviderFactory` caches adapters by `(provider, model)` key; language-specific AST queries live in independent `LanguageStrategy` implementations registered in `LanguageRegistry`. Adding Go support required zero changes to the core parser (OCP by design).
- **Value Objects** — `FilePath`, `Language`, `Severity`, `LLMConfig`, `RAGConfig` are immutable; domain logic never leaks infrastructure concerns.
- **Double-layer RAG** — retrieval searches both project documentation and historical PR diffs + discussions, so the LLM sees how similar changes were reviewed in the past.
- **Pluggable VCS** — `VCSRepository` port lets GitHub and GitLab adapters swap transparently. The same use case runs against both.

---

## Project Structure

```
acr_system/
├── domain/
│   ├── entities/          # PullRequest, DiffHunk, ReviewComment, CIToolResult
│   ├── interfaces/        # Ports: VCSRepository, LLMProvider, EmbeddingStore, …
│   ├── services/          # ReviewOrchestrator, ContextBuilder
│   └── value_objects/     # FilePath, Language, Severity, LLMConfig, RAGConfig
├── application/
│   ├── use_cases/         # ProcessPullRequest, PublishReview, IndexPRHistory, EvaluatePullRequest
│   └── dto/               # PRReviewRequest, ReviewResult
├── infrastructure/
│   ├── vcs/               # GitHubAdapter, GitLabAdapter (REST + webhooks)
│   ├── llm/               # OpenAIAdapter, AnthropicAdapter, LLMProviderFactory
│   ├── rag/               # FAISSStore, embedding pipeline (sentence-transformers)
│   ├── ci/                # GitHub Checks API, GitLab CI adapters
│   ├── analysis/          # Tree-sitter call graph analyzer
│   ├── auth/              # GitHub App JWT authentication
│   └── config/            # .acr-config.yml loader
├── ast/
│   ├── tree_sitter_adapter.py
│   ├── language_registry.py
│   └── strategies/        # Python · JavaScript · TypeScript · Go
├── presentation/
│   ├── api/               # FastAPI app, webhook endpoints
│   └── cli/               # Click commands: review, index-history, evaluate
└── experimental/
    ├── metrics.py         # BLEU-4, ROUGE-L, METEOR, BERTScore, semantic similarity
    └── reporting.py       # JSON report generation

exp/                       # Evaluation experiments
├── home-assistant/        # 4 real PRs, FAISS index (~1.8 M docs)
├── sentry/                # 4 real PRs, FAISS index (~2.8 M docs)
└── vscode/                # 4 real PRs, FAISS index (~1.9 M docs)

tests/
├── unit/                  # Adapter unit tests (GitHub, GitLab, OpenAI, FAISS)
├── integration/           # End-to-end workflow tests
├── ast/                   # Tree-sitter tests per language
└── e2e/                   # Full system tests
```

---

## Quickstart

### Requirements

- Python 3.11+
- `pip` or [`uv`](https://github.com/astral-sh/uv)

### Install

```bash
python -m venv venv && source venv/bin/activate

# Core only
pip install -e .

# LLM + RAG + AST extras
pip install -e ".[all]"
```

### Environment

Copy `.env.example` to `.env` and fill in the values for your chosen providers.

**Minimal setup (OpenAI + GitHub token):**

```bash
# .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
DEFAULT_LLM_MODEL=gpt-4o

GITHUB_TOKEN=ghp_...
```

**GitHub App authentication (recommended for production):**

```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=./github-app-private-key.pem
GITHUB_APP_INSTALLATION_ID=12345678   # optional — auto-detected
```

See [`acr_system/infrastructure/auth/README.md`](acr_system/infrastructure/auth/README.md) for GitHub App setup steps.

---

## Usage

### CLI

```bash
# Review a pull request and print comments to stdout
acr review --pr-url https://github.com/owner/repo/pull/123

# Review and post comments back to the PR
acr review --pr-url https://github.com/owner/repo/pull/123 --publish

# Switch to Anthropic Claude
acr review --pr-url https://github.com/owner/repo/pull/123 \
  --provider anthropic --model claude-3-5-sonnet-20241022

# Build a FAISS index from the last 50 merged PRs (enables RAG)
acr index-history --repo owner/repo --max-prs 50

# Run the evaluation pipeline (generates metrics vs. human reviews)
acr evaluate --pr-url https://github.com/owner/repo/pull/123 \
  --config .acr-config.yml --report-path report.json
```

### Webhook server

```bash
uvicorn acr_system.presentation.api.main:app --reload
# Listens on http://localhost:8000/webhooks/github
```

Configure your GitHub App to deliver `pull_request` events to this endpoint and the system will review new PRs automatically.

---

## Configuration

Drop an `.acr-config.yml` in your repository to control exactly what gets reviewed and how:

```yaml
review:
  enabled: true

# Rules applied to every file in the PR
global_rules:
  - name: security
    rules_text: |
      - Check for SQL injection and XSS vulnerabilities
      - Validate all user-supplied input at system boundaries

# Rules and LLM settings scoped to file patterns
file_patterns:
  - pattern: "**/*.py"
    rules_text: |
      - Follow PEP 8 style guide
      - Require type hints on all public functions
    llm_config:
      provider: anthropic
      model: claude-3-5-sonnet-20241022
      temperature: 0.3

  - pattern: "**/*.test.*"
    rules_text: |
      - Verify test isolation — no shared mutable state between cases

# Default LLM
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.3
  max_tokens: 2000

# RAG: retrieve from docs and past PR diffs
rag:
  enabled: true
  top_k: 5
  documentation_paths:
    - docs/
    - README.md
  architectural_docs:
    - ARCHITECTURE.md
    - docs/adr/*.md

# Breaking change detection via call-graph analysis
impact_analysis:
  enabled: true
  depth: 1
  max_callers_per_function: 10
  severity_threshold: medium

# Publish policy — controls which comments reach the PR
publish:
  min_severity: warning          # skip 'info' level
  exclude_rule_names:
    - style_hint
  exclude_message_patterns:
    - "more descriptive"
    - "documentation|api contracts"
  exclude_positive_feedback: true
```

---

## Evaluation

The evaluation pipeline compares LLM-generated review comments against human-authored PR discussions using five complementary metrics:

| Metric | What it measures |
|---|---|
| **BLEU-4** | 4-gram precision with add-1 smoothing |
| **ROUGE-L F1** | Longest common subsequence recall + precision |
| **METEOR** | Unigram alignment with recall emphasis |
| **BERTScore F1** | Contextual token-level semantic similarity |
| **Semantic similarity** | Cosine distance on sentence embeddings |

Additional change-localization metrics track what percentage of generated comments land on actually-modified lines.

Experiments were run on 12 real PRs across three large open-source repositories:

| Repository | Index size | PRs evaluated |
|---|---|---|
| `home-assistant/core` | ~1.8 M document chunks | 4 |
| `getsentry/sentry` | ~2.8 M document chunks | 4 |
| `microsoft/vscode` | ~1.9 M document chunks | 4 |

Each PR was reviewed twice — with RAG enabled and without — to isolate the contribution of retrieval-augmented context.

Results are aggregated with `exp/aggregate_reports.py` and exported to `aggregate_results.json` / `aggregate_results.csv`.

---

## Development

### Running tests

```bash
pytest                                      # full suite
pytest --cov=acr_system --cov-report=html  # with coverage
pytest tests/unit                           # unit only
pytest tests/ast                            # AST / tree-sitter only
```

### Linting and formatting

```bash
black acr_system tests    # format
ruff check acr_system tests  # lint
mypy acr_system           # type check
```

### Pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| REST API | [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/) |
| CLI | [Click](https://click.palletsprojects.com/) |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) |
| LLM providers | [OpenAI SDK](https://github.com/openai/openai-python) · [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) |
| Vector search | [FAISS](https://github.com/facebookresearch/faiss) + [sentence-transformers](https://www.sbert.net/) |
| Lexical search | [rank-bm25](https://github.com/dorianbrown/rank_bm25) |
| AST parsing | [tree-sitter](https://tree-sitter.github.io/tree-sitter/) |
| Auth | [PyJWT](https://pyjwt.readthedocs.io/) (GitHub App RS256) |
| Testing | [pytest](https://pytest.org/) + pytest-asyncio + pytest-cov |
| HTTP client | [httpx](https://www.python-httpx.org/) (async) |

---

## License

MIT — see [LICENSE](LICENSE).
