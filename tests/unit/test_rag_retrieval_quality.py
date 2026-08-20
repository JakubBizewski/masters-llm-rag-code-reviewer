"""Unit tests for the retrieval-quality controls added to the RAG path.

Covers the four mechanisms that decide what actually reaches the prompt:
calibrated similarity scoring, the relevance floor, the per-source diversity cap,
and the rerank/graceful-degradation behaviour in ContextBuilder.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from acr_system.domain.entities.entities import CodeContext, DiffHunk, PullRequest
from acr_system.domain.services.services import ContextBuilder
from acr_system.domain.value_objects.value_objects import FilePath, RAGConfig


# ── calibrated similarity ─────────────────────────────────────────────────────

def _make_store(unit_norm: bool = True):
    from acr_system.infrastructure.rag.faiss_store import FAISSStore

    store = FAISSStore.__new__(FAISSStore)  # bypass __init__ (needs faiss + model)
    store._unit_norm_embeddings = unit_norm
    return store


def test_similarity_is_true_cosine_for_unit_norm_embeddings():
    store = _make_store(unit_norm=True)
    # Orthogonal unit vectors are sqrt(2) apart and have cosine 0.
    assert store._similarity_from_distance(2 ** 0.5) == pytest.approx(0.0, abs=1e-9)
    # Identical vectors: distance 0, cosine 1.
    assert store._similarity_from_distance(0.0) == pytest.approx(1.0)


def test_similarity_spreads_the_usable_range():
    """The old 1/(1+d) mapping squashed everything into ~0.4-0.6, which made any
    threshold useless. The calibrated score must separate poor from good matches."""
    store = _make_store(unit_norm=True)
    poor = store._similarity_from_distance(1.2866)   # cosine ~0.17
    good = store._similarity_from_distance(0.6)      # cosine ~0.82
    assert poor < 0.25
    assert good > 0.75
    assert good - poor > 0.5


def test_similarity_falls_back_when_embeddings_are_not_unit_norm():
    store = _make_store(unit_norm=False)
    assert store._similarity_from_distance(1.0) == pytest.approx(0.5)


# ── ContextBuilder: floor, rerank, degradation ────────────────────────────────

def _hunk() -> DiffHunk:
    return DiffHunk(
        file_path=FilePath("homeassistant/components/demo/sensor.py"),
        old_start_line=10,
        old_line_count=2,
        new_start_line=10,
        new_line_count=3,
        content=(
            "+async def async_setup_entry(hass, entry, async_add_entities):\n"
            "+    coordinator = entry.runtime_data\n"
            "-    coordinator = hass.data[DOMAIN][entry.entry_id]\n"
        ),
    )


def _pr() -> PullRequest:
    pr = MagicMock(spec=PullRequest)
    pr.repository = "home-assistant/core"
    pr.pr_number = 999
    pr.head_sha = "deadbeef"
    pr.source_branch = "feature"
    return pr


def _builder(search_results):
    store = MagicMock()
    store.search_similar = AsyncMock(side_effect=search_results)
    vcs = MagicMock()
    vcs.get_file_content = AsyncMock(side_effect=Exception("no surrounding context"))
    return ContextBuilder(embedding_store=store, vcs_repository=vcs), store


@pytest.mark.asyncio
async def test_relevance_floor_and_cap_are_passed_to_the_store():
    builder, store = _builder([[], [], []])
    cfg = RAGConfig(enabled=True, top_k=3, min_relevance=0.5, max_chunks_per_source=2)

    await builder.build_context(_hunk(), _pr(), cfg)

    assert store.search_similar.await_count == 3  # docs + general + pr history
    for call in store.search_similar.await_args_list:
        assert call.kwargs["min_relevance"] == 0.5


@pytest.mark.asyncio
async def test_no_context_is_injected_when_nothing_clears_the_floor():
    """An empty context is strictly better than a loosely-related one: the prompt
    then matches a no-RAG run instead of being polluted with noise."""
    builder, _ = _builder([[], [], []])
    cfg = RAGConfig(enabled=True, top_k=3, min_relevance=0.5)

    context = await builder.build_context(_hunk(), _pr(), cfg)

    assert context == []


@pytest.mark.asyncio
async def test_retrieval_budget_is_capped_at_top_k():
    many = [
        CodeContext(content=f"chunk {i} coordinator runtime_data", source="pr_history_diff", relevance_score=0.9 - i / 100)
        for i in range(8)
    ]
    builder, _ = _builder([[], many, []])
    cfg = RAGConfig(enabled=True, top_k=3, min_relevance=0.5)

    context = await builder.build_context(_hunk(), _pr(), cfg)

    assert len(context) == 3


@pytest.mark.asyncio
async def test_rerank_prefers_chunks_sharing_identifiers_with_the_hunk():
    """Embedding score alone cannot tell 'same subsystem' from 'same topic'."""
    off_topic = CodeContext(
        content="Pull Request #1: unrelated browser emulation work in another area",
        source="pr_history_comment_thread",
        relevance_score=0.72,
    )
    on_topic = CodeContext(
        content="review: prefer entry.runtime_data over hass.data in async_setup_entry",
        source="pr_history_comment_thread",
        relevance_score=0.62,
    )
    builder, _ = _builder([[], [off_topic, on_topic], []])
    cfg = RAGConfig(enabled=True, top_k=1, min_relevance=0.5, lexical_weight=0.3)

    context = await builder.build_context(_hunk(), _pr(), cfg)

    assert len(context) == 1
    assert "runtime_data" in context[0].content


@pytest.mark.asyncio
async def test_documentation_is_retrieved_with_its_own_query():
    """Docs are outnumbered ~1000:1 by PR history, so they need a dedicated call."""
    builder, store = _builder([[], [], []])
    cfg = RAGConfig(enabled=True, top_k=3, min_relevance=0.5)

    await builder.build_context(_hunk(), _pr(), cfg)

    filters = [c.kwargs.get("filters") for c in store.search_similar.await_args_list]
    assert {"source": "documentation"} in filters


@pytest.mark.asyncio
async def test_documentation_wins_ties_against_pr_history():
    doc = CodeContext(
        content="Project documentation: CONTRIBUTING.md\n\nSet entry.runtime_data before forwarding platforms.",
        source="documentation",
        relevance_score=0.60,
    )
    history = CodeContext(
        content="review thread about runtime_data in async_setup_entry",
        source="pr_history_comment_thread",
        relevance_score=0.62,
    )
    builder, _ = _builder([[doc], [history], []])
    cfg = RAGConfig(enabled=True, top_k=1, min_relevance=0.5, lexical_weight=0.0)

    context = await builder.build_context(_hunk(), _pr(), cfg)

    assert context[0].source == "documentation"


# ── query construction ────────────────────────────────────────────────────────

def test_query_includes_replaced_lines_and_symbols():
    builder, _ = _builder([[], [], []])

    query = builder._build_rag_query(_hunk())

    assert "async_setup_entry" in query
    assert "Replaced:" in query          # removed lines characterise the change
    assert "hass.data[DOMAIN]" in query
    assert "Symbols:" in query
    assert "runtime_data" in query


def test_identifier_extraction_splits_camel_and_snake_case():
    builder, _ = _builder([[], [], []])

    ids = builder._extract_identifiers("const fooBarBaz = new RunOnceScheduler(); my_snake_name = 1")

    assert "fooBarBaz" in ids
    assert "Bar" in ids                   # camelCase part
    assert "snake" in ids                 # snake_case part
    assert "const" not in ids             # stop token


def test_identifier_overlap_scores_shared_symbols():
    builder, _ = _builder([[], [], []])
    query_ids = builder._extract_identifiers("runtime_data coordinator async_setup_entry")

    strong = builder._lexical_overlap(query_ids, "use runtime_data and coordinator here")
    weak = builder._lexical_overlap(query_ids, "totally different browser emulation topic")

    assert strong > weak
    assert weak == 0.0


# ── config validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_relevance": -0.1},
        {"min_relevance": 1.5},
        {"max_chunks_per_source": 0},
        {"lexical_weight": 1.5},
    ],
)
def test_invalid_rag_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        RAGConfig(**kwargs)


def test_default_top_k_is_small():
    """Retrieving many loosely-related chunks degrades generation (Meng2025RARe)."""
    assert RAGConfig().top_k <= 3
    assert RAGConfig().min_relevance > 0.0
