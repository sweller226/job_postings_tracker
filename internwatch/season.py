"""Classify a posting as matching the target term/year, rejecting it, or unknown."""
from __future__ import annotations

import html
import re
from urllib.parse import unquote

_TERM = r"(?<![a-z])(summer|fall|autumn|winter|spring)(?![a-z])"
_YEAR = r"(?:(?<![a-z0-9])20(\d\d)(?![a-z0-9])|(?<![a-z0-9])['’‘](\d\d)(?![a-z0-9]))"
_SEP = r"[\s\-_/,.:()]*"
_TERM_NC = r"(?<![a-z])(?:summer|fall|autumn|winter|spring)(?![a-z])"
# "Summer/Fall 2027" -> the year applies to every term in the list.
TERM_LIST_YEAR_RE = re.compile(
    rf"({_TERM_NC}(?:\s*(?:/|&|\+|-|,|\band\b|\bor\b)\s*{_TERM_NC})+){_SEP}{_YEAR}"
)
TERM_YEAR_RE = re.compile(_TERM + _SEP + _YEAR)
YEAR_TERM_RE = re.compile(_YEAR + _SEP + _TERM)
TERM_RE = re.compile(_TERM)
YEAR_RE = re.compile(_YEAR)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# Start months that mean "right year, wrong half of it" for the target term.
OFF_SEASON_MONTHS = {
    "summer": re.compile(
        r"(?<![a-z])(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|sep(t(ember)?)?"
        r"|oct(ober)?|nov(ember)?|dec(ember)?)(?![a-z])"
    ),
}
NO_SEASON = frozenset(("", "null", "none", "not stated", "n/a", "unknown", "tbd"))


def _norm_term(t: str) -> str:
    t = t.lower().strip()
    return "fall" if t == "autumn" else t


def _season_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in NO_SEASON else text


def _url_text(url: str | None) -> str:
    # UUIDs in ATS URLs can contain "-2026-" by chance; don't let them look like years.
    # Some feeds carry HTML entities in URLs ("June-&apos;26"), so unescape those too.
    text = html.unescape(unquote((url or "").replace("+", " ")))
    return UUID_RE.sub(" ", text.lower())


def classify_season(item: dict, term: str = "summer", year: int | str = 2027) -> str:
    """Return "match", "reject" or "unknown" for the target term/year."""
    term = _norm_term(term)
    yy = f"{int(year) % 100:02d}"
    season = _season_text(item.get("season"))
    seasons = [s for s in (_season_text(s) for s in item.get("seasons") or []) if s]
    fields = [season, " ; ".join(seasons), item.get("title"), _url_text(item.get("url")),
              item.get("section"), item.get("location")]
    hay = " | ".join(f for f in fields if f).lower()

    # 1. explicit term+year pairs, either order
    pairs = {(_norm_term(m.group(1)), m.group(2) or m.group(3)) for m in TERM_YEAR_RE.finditer(hay)}
    pairs |= {(_norm_term(m.group(3)), m.group(1) or m.group(2)) for m in YEAR_TERM_RE.finditer(hay)}
    for m in TERM_LIST_YEAR_RE.finditer(hay):
        pairs |= {(_norm_term(t), m.group(2) or m.group(3)) for t in TERM_RE.findall(m.group(1))}
    if (term, yy) in pairs:
        return "match"
    if pairs:
        return "reject"

    # 2. every year mentioned, including '26 style
    years = {m.group(1) or m.group(2) for m in YEAR_RE.finditer(hay)}

    # 3. term-only season field ("Summer", "Spring/Summer")
    if season and not re.search(r"\d", season) and TERM_RE.search(season.lower()):
        if term not in {_norm_term(t) for t in TERM_RE.findall(season.lower())}:
            return "reject"
        if years - {yy}:
            return "reject"
        return "match" if yy in years else "unknown"

    # 4. right year, but an off-season start month and never the term itself
    months = OFF_SEASON_MONTHS.get(term)
    if yy in years and months and months.search(hay) and not re.search(
        rf"(?<![a-z]){term}(?![a-z])", hay
    ):
        return "reject"

    # 5. fall back to bare years
    if yy in years:
        return "match"
    if years:
        return "reject"
    return "unknown"
