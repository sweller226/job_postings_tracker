"""state/seen.json: the record of every posting already seen."""
from __future__ import annotations

import json
import os
from pathlib import Path

def load_state(path: Path) -> dict:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {"version": 1, "seen": {}, "sources": {}}
    state = json.loads(path.read_text(encoding="utf-8"))  # corrupt state -> hard failure
    state.setdefault("seen", {})
    state.setdefault("sources", {})
    return state


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
