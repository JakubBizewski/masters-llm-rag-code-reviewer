from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

# Fields that are transient / too large for the JSON report.
_EXCLUDED_FIELDS = {"codebase_snapshot"}


def write_json_report(path: str, payload: Any) -> None:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def default(o: Any):
        if is_dataclass(o):
            d = asdict(o)
            for key in _EXCLUDED_FIELDS:
                d.pop(key, None)
            return d
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)

    data = asdict(payload) if is_dataclass(payload) else payload
    if isinstance(data, dict):
        for key in _EXCLUDED_FIELDS:
            data.pop(key, None)

    report_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=default),
        encoding="utf-8",
    )
