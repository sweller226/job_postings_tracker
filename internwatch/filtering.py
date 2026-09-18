"""Apply activity, section, season, title and location filters to one source."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .config import DEFAULT_FILTERS
from .season import classify_season
from .urls import canonicalize, url_id

def _compile(pattern):
    return re.compile(pattern, re.I) if pattern else None


def filter_items(src: dict, items: list[dict], cfg: dict) -> tuple[list[dict], Counter, dict]:
    filters = {**cfg["filters"], **{k: src[k] for k in DEFAULT_FILTERS if k in src}}
    term, year = cfg["target"]["term"], cfg["target"]["year"]
    section_ex = _compile(filters["section_exclude"])
    title_ex = _compile(filters["title_exclude"])
    title_in = _compile(filters["title_include"])
    loc_in = _compile(filters["location_include"])

    kept, drops, examples, seen_here = [], Counter(), defaultdict(list), set()

    def drop(reason, item):
        drops[reason] += 1
        if len(examples[reason]) < 3:
            examples[reason].append(item)

    for item in items:
        canonical = canonicalize(item["url"]) if item["url"] else None
        if not canonical:
            drop("bad url", item)
            continue
        if not item["active"] and not filters["include_inactive"]:
            drop("inactive", item)
            continue
        if section_ex and item["section"] and section_ex.search(item["section"]):
            drop("section", item)
            continue
        verdict = classify_season(item, term, year)
        if verdict == "unknown":
            if src.get("default_season"):
                verdict = classify_season({"season": src["default_season"]}, term, year)
            elif filters["include_unstated"]:
                verdict = "match"
            else:
                drop("unstated", item)
                continue
        if verdict != "match":
            drop("season", item)
            continue
        # Title filters only apply when the title was actually recovered.
        if item["title"] and title_ex and title_ex.search(item["title"]):
            drop("title", item)
            continue
        if item["title"] and title_in and not title_in.search(item["title"]):
            drop("title", item)
            continue
        if item["location"] and loc_in and not loc_in.search(item["location"]):
            drop("location", item)
            continue
        uid = url_id(canonical)
        if uid in seen_here:
            drop("dup", item)
            continue
        seen_here.add(uid)
        kept.append({**item, "id": uid, "canonical": canonical, "source": src["name"]})
    return kept, drops, examples
