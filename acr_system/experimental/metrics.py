from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional


_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def exact_match(a: str, b: str) -> bool:
    def norm(x: str) -> str:
        return " ".join((x or "").strip().lower().split())

    return norm(a) == norm(b) and norm(a) != ""


def rouge_l_f1(candidate: str, reference: str) -> float:
    """ROUGE-L F1 using LCS over tokens."""
    cand = _tokens(candidate)
    ref = _tokens(reference)
    if not cand or not ref:
        return 0.0

    # LCS length (DP) - O(n*m) but comments are short.
    n, m = len(cand), len(ref)
    dp = [0] * (m + 1)
    for i in range(1, n + 1):
        prev = 0
        for j in range(1, m + 1):
            tmp = dp[j]
            if cand[i - 1] == ref[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = tmp

    lcs = dp[m]
    prec = lcs / n
    rec = lcs / m
    if prec + rec == 0:
        return 0.0
    return (2 * prec * rec) / (prec + rec)


def bleu_4(candidate: str, reference: str) -> float:
    """Simple BLEU-4 with add-1 smoothing on n-gram counts."""
    cand = _tokens(candidate)
    ref = _tokens(reference)
    if not cand or not ref:
        return 0.0

    def ngrams(seq: list[str], n: int) -> list[tuple[str, ...]]:
        return [tuple(seq[i : i + n]) for i in range(0, max(0, len(seq) - n + 1))]

    precisions = []
    for n in range(1, 5):
        c_ngrams = ngrams(cand, n)
        r_ngrams = ngrams(ref, n)
        if not c_ngrams:
            precisions.append(0.0)
            continue

        r_counts: dict[tuple[str, ...], int] = {}
        for g in r_ngrams:
            r_counts[g] = r_counts.get(g, 0) + 1

        match = 0
        c_counts: dict[tuple[str, ...], int] = {}
        for g in c_ngrams:
            c_counts[g] = c_counts.get(g, 0) + 1

        for g, c_cnt in c_counts.items():
            match += min(c_cnt, r_counts.get(g, 0))

        # add-1 smoothing
        precisions.append((match + 1) / (len(c_ngrams) + 1))

    # geometric mean
    geo = math.exp(sum(math.log(p) for p in precisions) / 4)

    # brevity penalty
    c_len = len(cand)
    r_len = len(ref)
    if c_len > r_len:
        bp = 1.0
    else:
        bp = math.exp(1 - (r_len / max(c_len, 1)))

    return float(bp * geo)


def meteor_simplified(candidate: str, reference: str) -> float:
    """Simplified METEOR: unigram F-mean without stemming/synonyms.

    This matches the spirit of METEOR but is intentionally lightweight.
    """
    cand = _tokens(candidate)
    ref = _tokens(reference)
    if not cand or not ref:
        return 0.0

    ref_counts: dict[str, int] = {}
    for t in ref:
        ref_counts[t] = ref_counts.get(t, 0) + 1

    match = 0
    for t in cand:
        if ref_counts.get(t, 0) > 0:
            match += 1
            ref_counts[t] -= 1

    prec = match / len(cand)
    rec = match / len(ref)
    if prec + rec == 0:
        return 0.0

    # common METEOR weighting: Fmean = (10PR) / (R + 9P)
    return float((10 * prec * rec) / (rec + 9 * prec))


@dataclass
class TextMatchMetrics:
    reference_index: Optional[int]
    semantic_similarity: Optional[float]
    exact_match: Optional[bool]
    bleu4: Optional[float]
    rougeL_f1: Optional[float]
    meteor: Optional[float]
    bertscore_f1: Optional[float]


def try_bertscore_f1(candidate: str, reference: str) -> Optional[float]:
    """Best-effort BERTScore F1.

    Returns None if dependency/model is unavailable.
    """
    try:
        from bert_score import score  # type: ignore

        P, R, F1 = score([candidate], [reference], lang="en", verbose=False)
        return float(F1[0].item())
    except Exception:
        return None


def safe_mean(values: list[float]) -> Optional[float]:
    vals = [v for v in values if v is not None and not math.isnan(v)]  # type: ignore
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def cosine_sim_matrix(a, b) -> Any:
    """Cosine similarity between two 2D arrays (numpy-like)."""
    import numpy as np

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return a_norm @ b_norm.T
