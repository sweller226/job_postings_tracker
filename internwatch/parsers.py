"""Turn a fetched source body into raw posting dicts (JSON feeds and README tables)."""
from __future__ import annotations

import bisect
import html
import json
import re
import sys

from .urls import looks_like_ats

def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_text(v) for v in value if _text(v))
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_json_source(src: dict, body: str) -> list[dict]:
    data = json.loads(body)
    rows = list(data.values()) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("expected a JSON array or object of postings")
    f = src.get("fields", {})
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        active = True
        for key in (f.get("active"), f.get("visible")):
            if key and row.get(key) is False:
                active = False
        seasons = row.get(f["seasons"]) if f.get("seasons") else None
        items.append({
            "url": _text(row.get(f.get("url", "url"))),
            "company": _text(row.get(f.get("company", "company"))),
            "title": _text(row.get(f.get("title", "title"))),
            "location": _text(row.get(f.get("location", "location"))),
            "season": _text(row.get(f.get("season", "season"))),
            "seasons": [_text(s) for s in seasons] if isinstance(seasons, list) else [],
            "section": "",
            "active": active,
        })
    return items


LINK_RE = re.compile(
    r"""href\s*=\s*["']([^"']+)["']"""        # <a href="...">
    r"""|\]\(\s*<?(https?://[^\s)>]+)>?"""    # [text](url)
    r"""|<(https?://[^\s>]+)>""",             # <https://autolink>
    re.I,
)
# Markdown headings only: READMEs use HTML <h2>/<h3> for banners and ads mid-table.
HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t#]*$", re.M)
TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
TD_RE = re.compile(r"<(t[dh])\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
PIPE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
CARRY_MARKERS = frozenset(("↳", "↳"))


def clean_cell(raw: str) -> str:
    s = re.sub(r"<summary\b.*?</summary>", " ", raw, flags=re.I | re.S)  # "5 locations"
    s = re.sub(r"<\s*/?\s*br\s*/?\s*>", ", ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)           # markdown images
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)        # markdown links -> text
    s = html.unescape(s).replace("**", "").replace("__", "").replace("\\|", "|")
    s = re.sub(r"\s*,(\s*,)+", ",", re.sub(r"\s+", " ", s))
    return s.strip(" ,").removeprefix("🔥").strip()


class _Row:
    __slots__ = ("start", "end", "cells", "header", "company", "title", "location")

    def __init__(self, start, end, cells, header):
        self.start, self.end, self.cells, self.header = start, end, cells, header
        self.company = self.title = self.location = ""


def _table_rows(text: str) -> list[_Row]:
    rows = []
    for m in TR_RE.finditer(text):
        base = m.start(1)
        cells, header = [], False
        for c in TD_RE.finditer(m.group(1)):
            header |= c.group(1).lower() == "th"
            cells.append((base + c.start(), base + c.end(), c.group(2)))
        rows.append(_Row(m.start(), m.end(), cells, header))

    lines = text.splitlines(keepends=True)
    offset = 0
    for i, line in enumerate(lines):
        body = line.rstrip("\r\n")
        stripped = body.strip()
        if stripped.startswith("|") and not PIPE_SEP_RE.match(stripped):
            pipes = [p.start() for p in UNESCAPED_PIPE_RE.finditer(body)]
            bounds = list(zip(pipes, pipes[1:]))
            if pipes and body[pipes[-1] + 1:].strip():
                bounds.append((pipes[-1], len(body)))
            cells = [(offset + a + 1, offset + b, body[a + 1:b]) for a, b in bounds]
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            rows.append(_Row(offset, offset + len(body), cells, bool(PIPE_SEP_RE.match(nxt))))
        offset += len(line)

    rows.sort(key=lambda r: r.start)
    last_company = ""
    for r in rows:
        if r.header:
            last_company = ""
            continue
        vals = [clean_cell(c[2]) for c in r.cells]
        if len(vals) >= 3:
            company = vals[0]
            if company in CARRY_MARKERS or company.startswith("↳"):
                company = last_company
            elif company:
                last_company = company
            r.company, r.title, r.location = company, vals[1], vals[2]
    return rows


def parse_readme_source(src: dict, text: str) -> list[dict]:
    """Link extraction first, table enrichment second, so format drift degrades gracefully."""
    headings = []
    for m in HEADING_RE.finditer(text):
        label = clean_cell(m.group(1))
        if label:
            headings.append((m.start(), label))
    heading_pos = [h[0] for h in headings]

    try:
        rows = _table_rows(text)
    except Exception as e:  # never let table parsing kill the source
        print(f"  warning: table parsing failed ({e}); using bare links", file=sys.stderr)
        rows = []
    row_starts = [r.start for r in rows]

    items = []
    for m in LINK_RE.finditer(text):
        url = html.unescape(next(g for g in m.groups() if g)).strip()
        if not looks_like_ats(url):
            continue
        pos = m.start()
        h = bisect.bisect_right(heading_pos, pos) - 1
        item = {"url": url, "company": "", "title": "", "location": "", "season": "",
                "seasons": [], "section": headings[h][1] if h >= 0 else "", "active": True}
        r = bisect.bisect_right(row_starts, pos) - 1
        if r >= 0 and rows[r].start <= pos < rows[r].end and not rows[r].header:
            row = rows[r]
            cell = next((i for i, c in enumerate(row.cells) if c[0] <= pos < c[1]), None)
            if cell == 0 and len(row.cells) >= 4:
                continue  # company-name cell links to a homepage, not a job
            item.update(company=row.company, title=row.title, location=row.location)
        items.append(item)
    return items


PARSERS = {"json": parse_json_source, "readme": parse_readme_source}
