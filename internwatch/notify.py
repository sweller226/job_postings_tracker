"""Build notifications and deliver them via ntfy."""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlsplit

import requests


def ntfy_configured() -> bool:
    return bool(os.environ.get("NTFY_TOPIC"))


def _post(session, url, **kwargs) -> requests.Response:
    """POST with a small retry for 429/5xx, honoring Retry-After."""
    for attempt in range(3):
        r = session.post(url, timeout=20, **kwargs)
        if r.status_code != 429 and r.status_code < 500:
            break
        try:
            wait = float(r.headers.get("Retry-After", 2 * (attempt + 1)))
        except ValueError:
            wait = 2 * (attempt + 1)
        time.sleep(min(wait, 10))
    r.raise_for_status()
    return r


def send_ntfy(session, note, ncfg):
    server = (os.environ.get("NTFY_SERVER") or ncfg["ntfy_server"]).rstrip("/")
    payload = {"topic": os.environ["NTFY_TOPIC"], "title": note["title"],
               "message": note["message"][:4000], "priority": note["priority"],
               "tags": ["briefcase"]}
    if note.get("url"):
        payload["click"] = note["url"]
    headers = {}
    if os.environ.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['NTFY_TOKEN']}"
    # JSON body to the server root: unicode-safe, unlike X-Title headers.
    _post(session, server + "/", json=payload, headers=headers)


def build_notifications(items, cfg, sources_by_name) -> list[dict]:
    ncfg = cfg["notifications"]
    cap = int(ncfg["max_individual"])
    prio = int(ncfg["priority"])
    label = f"{cfg['target']['term'].title()} {cfg['target']['year']}"
    notes = []
    for it in items[:cap]:
        title = " — ".join(x for x in (it["company"], it["title"]) if x)
        if not title:
            title = f"New {label} posting ({urlsplit(it['canonical']).hostname})"
        lines = [x for x in (it["location"], f"via {it['source']}", it["url"]) if x]
        notes.append({"title": title[:200], "message": "\n".join(lines),
                      "url": it["url"], "priority": prio})
    # Overflow: one summary per board, so a notification never mixes boards.
    by_source: dict[str, list[dict]] = {}
    for it in items[cap:]:
        by_source.setdefault(it["source"], []).append(it)
    for source, rest in by_source.items():
        home = sources_by_name.get(source, {}).get("home")
        shown = [f"• {' — '.join(x for x in (it['company'], it['title']) if x) or it['url']}"
                 for it in rest[:20]]
        if len(rest) > 20:
            shown.append(f"…and {len(rest) - 20} more")
        header = f"From {home.removeprefix('https://')}:" if home else f"From {source}:"
        notes.append({"title": f"+{len(rest)} more new {label} postings from {source}",
                      "message": "\n".join([header, *shown]), "url": home, "priority": prio})
    return notes


def send_test(session, cfg, example: dict | None) -> Exception | None:
    """Send one test notification, returning None on success or the error.

    `example` is a state/seen.json entry; the test is rendered exactly like a real alert
    for it (so tapping it exercises the apply link), with a [TEST] marker.
    """
    if example:
        item = {"company": example.get("company", ""), "title": example.get("title", ""),
                "location": "", "source": example.get("source", ""),
                "url": example["url"], "canonical": example["url"]}
        note = build_notifications([item], cfg, {})[0]
    else:
        note = {"title": "Internship watcher", "message": "", "url": None,
                "priority": int(cfg["notifications"]["priority"])}
    note["title"] = f"[TEST] {note['title']}"[:200]
    note["message"] = ("Test from the internship watcher: notifications are working.\n\n"
                       + note["message"]).strip()
    try:
        send_ntfy(session, note, cfg["notifications"])
        return None
    except Exception as e:
        return e


def deliver(session, notes, cfg) -> tuple[int, int]:
    """Send every note via ntfy. Returns (successes, failures)."""
    ok = failed = 0
    for note in notes:
        try:
            send_ntfy(session, note, cfg["notifications"])
            ok += 1
        except Exception as e:
            failed += 1
            print(f"  ntfy send failed: {e}", file=sys.stderr)
        time.sleep(0.5)
    return ok, failed
