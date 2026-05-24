"""Shared JSON extraction utilities for LLM adapters."""
from __future__ import annotations

import json
import re
from typing import Optional


def extract_json_object(text: str) -> Optional[str]:
    """Extract the first valid top-level JSON object from arbitrary LLM output.

    Handles:
    - Markdown code fences (```json ... ```)
    - Template placeholders like {word} that appear before the real JSON
    - Nested objects (depth-counting, not fragile rfind)
    """
    # 1. Try stripping markdown code fences first
    fence = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", text)
    if fence:
        candidate = fence.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # 2. Walk every '{' and skip ones that look like template placeholders.
    #    A real JSON object key starts with '"' or '}' after optional whitespace.
    for m in re.finditer(r"\{", text):
        start = m.start()
        lookahead = text[start + 1 : start + 20].lstrip()
        if not lookahead or lookahead[0] not in ('"', "}"):
            continue

        # Depth-count to find the matching '}'
        depth = 0
        in_string = False
        escape = False
        end = -1
        for i, ch in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end == -1:
            continue

        candidate = text[start:end]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue

    return None
