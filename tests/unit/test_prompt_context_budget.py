"""Tests for how retrieved context is budgeted into the review prompt.

Regression cover for a defect found during evaluation: a flat `context[:3]` cap let
three retrieved chunks evict the surrounding_code section, so a RAG review could not
see the file it was reviewing while a no-RAG review always could. The prompt's own
instructions require surrounding_code to confirm "symbol is missing" claims, so its
absence produced confident false positives about absent imports and fixtures.
"""
import pytest

from acr_system.domain.entities.entities import CodeContext, DiffHunk
from acr_system.domain.value_objects.value_objects import FilePath
from acr_system.infrastructure.llm.anthropic_adapter import AnthropicAdapter
from acr_system.infrastructure.llm.openai_adapter import OpenAIAdapter

FILE_MARKER = "THE ACTUAL FILE CONTENT"
CONVENTION = "CONVENTION: prefer entry.runtime_data over hass.data"


def _hunk() -> DiffHunk:
    return DiffHunk(
        file_path=FilePath("homeassistant/components/demo/sensor.py"),
        old_start_line=1,
        old_line_count=1,
        new_start_line=10,
        new_line_count=3,
        content="@@ -1 +10,3 @@\n+coordinator = entry.runtime_data\n",
    )


def _context(n_retrieved: int = 0, n_docs: int = 0, with_surrounding: bool = True):
    ctx = [
        CodeContext(content=f"prior review thread {i}", source="pr_history_comment_thread", relevance_score=0.7)
        for i in range(n_retrieved)
    ]
    ctx += [
        CodeContext(content=CONVENTION, source="documentation", relevance_score=0.6)
        for _ in range(n_docs)
    ]
    if with_surrounding:
        # Appended last, exactly as ContextBuilder.build_context orders it.
        ctx.append(CodeContext(content=FILE_MARKER, source="surrounding_code", relevance_score=1.0))
    return ctx


def _adapters():
    return [
        AnthropicAdapter.__new__(AnthropicAdapter),
        OpenAIAdapter.__new__(OpenAIAdapter),
    ]


@pytest.mark.parametrize("n_retrieved", [0, 1, 3, 5, 9])
def test_surrounding_code_is_never_evicted_by_retrieved_chunks(n_retrieved):
    for adapter in _adapters():
        prompt = adapter._build_review_prompt(_hunk(), "rules", _context(n_retrieved), [])
        assert FILE_MARKER in prompt, (
            f"{type(adapter).__name__}: file content dropped with {n_retrieved} retrieved chunks"
        )


def test_documentation_is_labelled_as_binding_convention():
    for adapter in _adapters():
        prompt = adapter._build_review_prompt(_hunk(), "rules", _context(3, n_docs=1), [])
        assert "Project convention" in prompt
        assert CONVENTION in prompt


def test_retrieved_history_is_capped_but_conventions_and_file_survive():
    for adapter in _adapters():
        prompt = adapter._build_review_prompt(_hunk(), "rules", _context(9, n_docs=3), [])
        assert prompt.count("### From pr_history") == adapter.MAX_RETRIEVED_SECTIONS
        assert prompt.count("### Project convention") == adapter.MAX_DOC_SECTIONS
        assert FILE_MARKER in prompt


def test_surrounding_code_budget_is_large_enough_to_verify_claims():
    """500 characters was ~10 lines, too little to confirm an import is absent."""
    for adapter in _adapters():
        assert adapter.SURROUNDING_CHAR_BUDGET >= 4000
        assert adapter.DOC_CHAR_BUDGET >= 1000


def test_instructions_forbid_absence_claims_without_surrounding_code():
    for adapter in _adapters():
        prompt = adapter._build_review_prompt(_hunk(), "rules", _context(3, with_surrounding=False), [])
        assert "do not claim that any symbol, import or fixture is missing" in prompt


def test_instructions_require_checking_the_diff_against_conventions():
    for adapter in _adapters():
        prompt = adapter._build_review_prompt(_hunk(), "rules", _context(1, n_docs=1), [])
        assert "check the changed lines against each convention" in prompt
        assert "project documentation" in prompt  # present in the evidence hierarchy
