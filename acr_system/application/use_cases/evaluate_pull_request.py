"""Use case: Experimental evaluation of automated code review on a historical PR/MR."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from acr_system.application.dto.dto import PRReviewRequest
from acr_system.application.use_cases.process_pull_request import ProcessPullRequestUseCase
from acr_system.domain.entities.entities import DiffHunk, PullRequest, PullRequestDiscussionComment, ReviewComment
from acr_system.domain.interfaces.ports import EmbeddingStore, VCSRepository
from acr_system.experimental.metrics import (
    TextMatchMetrics,
    bleu_4,
    cosine_sim_matrix,
    exact_match,
    meteor_simplified,
    rouge_l_f1,
    safe_mean,
    try_bertscore_f1,
)


@dataclass
class EvaluationRequest:
    repository: str
    pr_number: int
    history_window_days: int = 365
    max_history_prs: int = 200
    skip_indexing: bool = False


@dataclass
class StageTiming:
    indexing_seconds: float
    review_seconds: float


@dataclass
class TokenCosts:
    embedding_index_tokens: int
    embedding_review_tokens: int
    llm_prompt_tokens: int
    llm_completion_tokens: int


@dataclass
class EvaluationResult:
    repository: str
    pr_number: int
    target_pr_created_at: Optional[str]
    indexed_prs: int
    skipped_prs: int
    timings: StageTiming
    token_costs: TokenCosts
    generated_comments: list[dict[str, Any]]
    reference_comments: list[dict[str, Any]]
    metrics_summary: dict[str, Any]


class EvaluatePullRequestUseCase:
    def __init__(
        self,
        vcs_repository: VCSRepository,
        embedding_store: EmbeddingStore,
        process_pr_use_case: ProcessPullRequestUseCase,
        llm_usage_stats,  # UsageStats
    ):
        self.vcs_repository = vcs_repository
        self.embedding_store = embedding_store
        self.process_pr_use_case = process_pr_use_case
        self.llm_usage_stats = llm_usage_stats

    async def execute(self, request: EvaluationRequest) -> EvaluationResult:
        # Fetch target PR (for created_at)
        target_pr = await self.vcs_repository.get_pull_request(request.repository, request.pr_number)
        target_created_at = getattr(target_pr, "created_at", None)

        # Index history within window
        indexed_count = 0
        skipped_count = 0

        window_days = int(request.history_window_days)
        window = timedelta(days=window_days)

        # Reset embedding stats if available
        if hasattr(self.embedding_store, "reset_stats"):
            self.embedding_store.reset_stats()  # type: ignore[attr-defined]

        t0 = time.perf_counter()

        if request.skip_indexing:
            indexing_seconds = 0.0
        else:
            if target_created_at is None:
                pr_numbers = await self.vcs_repository.list_merged_pull_requests(request.repository, limit=request.max_history_prs)
                candidates = [int(n) for n in pr_numbers if int(n) != int(request.pr_number)]
            else:
                pr_numbers = await self.vcs_repository.list_merged_pull_requests(request.repository, limit=request.max_history_prs)
                candidates = []
                for n in pr_numbers:
                    if int(n) == int(request.pr_number):
                        continue
                    try:
                        pr = await self.vcs_repository.get_pull_request(request.repository, int(n))
                    except Exception:
                        skipped_count += 1
                        continue

                    pr_created_at = getattr(pr, "created_at", None)
                    if pr_created_at is None:
                        skipped_count += 1
                        continue

                    if pr_created_at >= target_created_at:
                        skipped_count += 1
                        continue

                    if pr_created_at < (target_created_at - window):
                        skipped_count += 1
                        continue

                    candidates.append(int(n))

            semaphore = asyncio.Semaphore(5)

            async def _index_one(n: int) -> None:
                nonlocal indexed_count, skipped_count
                async with semaphore:
                    try:
                        pr = await self.vcs_repository.get_pull_request(request.repository, n)
                        hunks = await self.vcs_repository.get_diff_hunks(request.repository, n)
                        for h in hunks:
                            pr.add_diff_hunk(h)

                        discussion = await self.vcs_repository.get_pull_request_discussion_comments(request.repository, n)
                        for c in discussion:
                            pr.add_discussion_comment(c)

                        await self.embedding_store.index_review_history(pr)
                        indexed_count += 1
                    except Exception:
                        skipped_count += 1

            await asyncio.gather(*(_index_one(n) for n in candidates))
            indexing_seconds = time.perf_counter() - t0

        embedding_index_tokens = 0
        if hasattr(self.embedding_store, "stats"):
            embedding_index_tokens = int(getattr(self.embedding_store, "stats").get("embedding_tokens", 0))  # type: ignore[call-arg]

        # Review stage
        if hasattr(self.embedding_store, "reset_stats"):
            self.embedding_store.reset_stats()  # type: ignore[attr-defined]
        if hasattr(self.llm_usage_stats, "reset"):
            self.llm_usage_stats.reset()

        t1 = time.perf_counter()
        review_result = await self.process_pr_use_case.execute(
            PRReviewRequest(repository=request.repository, pr_number=request.pr_number)
        )
        review_seconds = time.perf_counter() - t1

        embedding_review_tokens = 0
        if hasattr(self.embedding_store, "stats"):
            embedding_review_tokens = int(getattr(self.embedding_store, "stats").get("embedding_tokens", 0))  # type: ignore[call-arg]

        llm_prompt_tokens = int(getattr(self.llm_usage_stats, "prompt_tokens", 0))
        llm_completion_tokens = int(getattr(self.llm_usage_stats, "completion_tokens", 0))

        # Reference comments = real discussion on target PR
        references = await self.vcs_repository.get_pull_request_discussion_comments(request.repository, request.pr_number)

        # Compute metrics
        metrics_summary, per_comment = await _compute_metrics(
            embedding_store=self.embedding_store,
            diff_hunks=await self.vcs_repository.get_diff_hunks(request.repository, request.pr_number),
            generated=review_result.comments if review_result.success else [],
            references=references,
        )

        return EvaluationResult(
            repository=request.repository,
            pr_number=request.pr_number,
            target_pr_created_at=target_created_at.isoformat() if target_created_at else None,
            indexed_prs=indexed_count,
            skipped_prs=skipped_count,
            timings=StageTiming(indexing_seconds=indexing_seconds, review_seconds=review_seconds),
            token_costs=TokenCosts(
                embedding_index_tokens=embedding_index_tokens,
                embedding_review_tokens=embedding_review_tokens,
                llm_prompt_tokens=llm_prompt_tokens,
                llm_completion_tokens=llm_completion_tokens,
            ),
            generated_comments=_serialize_review_comments(review_result.comments if review_result.success else []),
            reference_comments=_serialize_reference_comments(references),
            metrics_summary={
                **metrics_summary,
                "per_generated_comment": per_comment,
            },
        )


def _serialize_review_comments(comments: list[ReviewComment]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in comments:
        out.append(
            {
                "file_path": c.file_path.value,
                "line_number": c.line_number,
                "severity": c.severity.level,
                "message": c.message,
                "suggestion": c.suggestion,
                "source": str(getattr(c, "source", "")),
            }
        )
    return out


def _serialize_reference_comments(comments: list[PullRequestDiscussionComment]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in comments:
        out.append(
            {
                "comment_id": c.comment_id,
                "author": c.author,
                "created_at": c.created_at.isoformat(),
                "file_path": c.file_path.value if c.file_path else None,
                "line_number": c.line_number,
                "body": c.body,
                "in_reply_to_id": c.in_reply_to_id,
                "url": c.url,
            }
        )
    return out


async def _compute_metrics(
    embedding_store: EmbeddingStore,
    diff_hunks: list[DiffHunk],
    generated: list[ReviewComment],
    references: list[PullRequestDiscussionComment],
) -> tuple[dict[str, Any], list[TextMatchMetrics]]:
    ref_texts = [c.body for c in references]
    gen_texts = [c.message for c in generated]

    if not gen_texts:
        return {
            "generated_count": 0,
            "reference_count": len(ref_texts),
        }, []

    # Compute semantic similarity via sentence-transformers if available
    sim = None
    if ref_texts:
        try:
            model = getattr(embedding_store, "embedding_model", None)
            if model is not None:
                gen_vecs = model.encode(gen_texts)
                ref_vecs = model.encode(ref_texts)
                sim = cosine_sim_matrix(gen_vecs, ref_vecs)
        except Exception:
            sim = None

    per_comment: list[TextMatchMetrics] = []
    bleu_vals: list[float] = []
    rouge_vals: list[float] = []
    meteor_vals: list[float] = []
    bert_vals: list[float] = []
    em_vals: list[float] = []
    sem_vals: list[float] = []

    for i, gen in enumerate(gen_texts):
        if not ref_texts:
            per_comment.append(
                TextMatchMetrics(
                    reference_index=None,
                    semantic_similarity=None,
                    exact_match=None,
                    bleu4=None,
                    rougeL_f1=None,
                    meteor=None,
                    bertscore_f1=None,
                )
            )
            continue

        if sim is not None:
            best_j = int(sim[i].argmax())
            best_sim = float(sim[i, best_j])
        else:
            # Fallback: choose first
            best_j = 0
            best_sim = None

        ref = ref_texts[best_j]
        em = exact_match(gen, ref)
        b = bleu_4(gen, ref)
        r = rouge_l_f1(gen, ref)
        m = meteor_simplified(gen, ref)
        bs = try_bertscore_f1(gen, ref)

        per_comment.append(
            TextMatchMetrics(
                reference_index=best_j,
                semantic_similarity=best_sim,
                exact_match=em,
                bleu4=b,
                rougeL_f1=r,
                meteor=m,
                bertscore_f1=bs,
            )
        )

        bleu_vals.append(b)
        rouge_vals.append(r)
        meteor_vals.append(m)
        if bs is not None:
            bert_vals.append(bs)
        em_vals.append(1.0 if em else 0.0)
        if best_sim is not None:
            sem_vals.append(best_sim)

    changed_files = {h.file_path.value for h in diff_hunks}

    def in_any_hunk(file_path: str, line: Optional[int]) -> bool:
        if line is None:
            return False
        for h in diff_hunks:
            if h.file_path.value == file_path and h.is_line_in_hunk(line):
                return True
        return False

    gen_loc_file = [1.0 if c.file_path.value in changed_files else 0.0 for c in generated]
    gen_loc_line = [1.0 if in_any_hunk(c.file_path.value, c.line_number) else 0.0 for c in generated]

    ref_loc_file = [
        1.0 if (c.file_path and c.file_path.value in changed_files) else 0.0
        for c in references
    ]
    ref_loc_line = [
        1.0
        if (c.file_path and c.line_number and in_any_hunk(c.file_path.value, c.line_number))
        else 0.0
        for c in references
    ]

    summary: dict[str, Any] = {
        "generated_count": len(generated),
        "reference_count": len(references),
        "exact_match_rate": safe_mean(em_vals),
        "bleu4_mean": safe_mean(bleu_vals),
        "rougeL_f1_mean": safe_mean(rouge_vals),
        "meteor_simplified_mean": safe_mean(meteor_vals),
        "semantic_similarity_mean": safe_mean(sem_vals) if sem_vals else None,
        "bertscore_f1_mean": safe_mean(bert_vals) if bert_vals else None,
        "change_localization": {
            "generated_file_in_diff_rate": safe_mean(gen_loc_file),
            "generated_line_in_hunk_rate": safe_mean(gen_loc_line),
            "reference_file_in_diff_rate": safe_mean(ref_loc_file) if ref_loc_file else None,
            "reference_line_in_hunk_rate": safe_mean(ref_loc_line) if ref_loc_line else None,
        },
        "notes": {
            "meteor": "meteor_simplified is a lightweight proxy (no stemming/synonyms)",
            "bertscore": "bertscore is best-effort; None if dependency/model unavailable",
            "desiredness_score": "not computed (requires a language model perplexity setup and a target correction objective)",
            "correction_regression": "not computed (would require applying fixes and running tests/build)",
        },
    }

    return summary, per_comment
