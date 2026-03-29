from __future__ import annotations

import re
from dataclasses import dataclass


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]", re.UNICODE)


def approx_token_count(text: str) -> int:
    """Approximate token count for cost estimation.

    This is *not* model-specific tokenization. It is a stable, cheap proxy that
    works without external dependencies.
    """
    if not text:
        return 0
    return len(_TOKEN_RE.findall(text))


@dataclass
class UsageStats:
    """Aggregated token usage (prompt/completion)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.prompt_tokens += int(prompt_tokens or 0)
        self.completion_tokens += int(completion_tokens or 0)

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
