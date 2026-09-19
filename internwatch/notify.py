"""Build notifications and deliver them via ntfy, Pushover and Discord."""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlsplit

import requests

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


def send_pushover(session, note, ncfg):
    data = {"token": os.environ["PUSHOVER_TOKEN"], "user": os.environ["PUSHOVER_USER"],
            "title": note["title"][:250], "message": note["message"][:1024],
            "priority": max(-2, min(1, note["priority"] - 3))}
    if note.get("url"):
        data.update(url=note["url"][:512], url_title="Apply")
    _post(session, "https://api.pushover.net/1/messages.json", data=data)


def send_discord(session, note, ncfg):
    embed = {"title": note["title"][:256], "description": note["message"][:4000]}
    if note.get("url"):
        embed["url"] = note["url"]
    _post(session, os.environ["DISCORD_WEBHOOK_URL"], json={"embeds": [embed]})


CHANNELS = {
    "ntfy": (("NTFY_TOPIC",), send_ntfy),
    "pushover": (("PUSHOVER_TOKEN", "PUSHOVER_USER"), send_pushover),
    "discord": (("DISCORD_WEBHOOK_URL",), send_discord),
}


def configured_channels() -> list[str]:
    return [name for name, (env, _) in CHANNELS.items() if all(os.environ.get(e) for e in env)]


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
    rest = items[cap:]
    if rest:
        shown = [f"• {' — '.join(x for x in (it['company'], it['title']) if x) or it['url']}"
                 for it in rest[:20]]
        if len(rest) > 20:
            shown.append(f"…and {len(rest) - 20} more")
        srcs = {it["source"] for it in rest}
        home = sources_by_name[srcs.pop()].get("home") if len(srcs) == 1 else None
        notes.append({"title": f"+{len(rest)} more new {label} postings",
                      "message": "\n".join(shown), "url": home, "priority": prio})
    return notes


def send_test(session, cfg, example: dict | None) -> dict[str, Exception | None]:
    """Send one test notification to every configured channel.

    `example` is a state/seen.json entry; the test is rendered exactly like a real alert
    for it (so tapping it exercises the apply link), with a [TEST] marker.
    Returns {channel: None on success, else the error}.
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
    results = {}
    for name in configured_channels():
        try:
            CHANNELS[name][1](session, note, cfg["notifications"])
            results[name] = None
        except Exception as e:
            results[name] = e
    return results


def deliver(session, notes, cfg) -> tuple[int, int]:
    """Send every note to every configured channel. Returns (successes, failures)."""
    ok = failed = 0
    for note in notes:
        for name in configured_channels():
            try:
                CHANNELS[name][1](session, note, cfg["notifications"])
                ok += 1
            except Exception as e:
                failed += 1
                print(f"  notify via {name} failed: {e}", file=sys.stderr)
        time.sleep(0.5)
    return ok, failed
