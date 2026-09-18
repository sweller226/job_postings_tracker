"""config.json loading and defaults."""
from __future__ import annotations

import json
from pathlib import Path

from .parsers import PARSERS

DEFAULT_FILTERS = {
    "include_inactive": False,
    "include_unstated": False,
    "section_exclude": r"(new.?grad|full.?time|phd|return offer)",
    "title_exclude": r"(new.?grad|university.?grad|entry.?level)",
    "title_include": None,
    "location_include": None,
}
DEFAULT_NOTIFICATIONS = {
    "max_individual": 12,
    "priority": 3,
    "ntfy_server": "https://ntfy.sh",
}


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["filters"] = {**DEFAULT_FILTERS, **cfg.get("filters", {})}
    cfg["notifications"] = {**DEFAULT_NOTIFICATIONS, **cfg.get("notifications", {})}
    cfg.setdefault("target", {"term": "summer", "year": 2027})
    cfg.setdefault("http", {})
    for src in cfg["sources"]:
        if src.get("type") not in PARSERS:
            raise ValueError(f"source {src.get('name')}: unknown type {src.get('type')!r}")
    return cfg
