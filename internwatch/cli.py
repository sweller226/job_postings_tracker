"""Watch community internship repos and notify when an unseen posting appears.

State lives in state/seen.json and is committed back by the GitHub workflow.

Environment:
  DRY_RUN=1      fetch, parse, filter, diff and print; send nothing, write nothing
  SEED_ONLY=1    record every current posting as seen without notifying
  VERBOSE=1      print a few example postings for every drop reason
  NTFY_TOPIC, NTFY_SERVER (default https://ntfy.sh), NTFY_TOKEN
  PUSHOVER_TOKEN, PUSHOVER_USER
  DISCORD_WEBHOOK_URL
  WATCHER_CONFIG, WATCHER_STATE   override the config / state file paths
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import load_config
from .filtering import filter_items
from .notify import build_notifications, configured_channels, deliver
from .parsers import PARSERS
from .state import load_state, save_state
from .urls import dedupe_key

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "internship-watcher/1.0 (+https://github.com/features/actions)"


def fetch(session, url: str, timeout: float, retries: int) -> str:
    last = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except requests.RequestException as e:
            last = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except AttributeError:
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", default=_flag("DRY_RUN"))
    ap.add_argument("--seed-only", action="store_true", default=_flag("SEED_ONLY"))
    ap.add_argument("--verbose", action="store_true", default=_flag("VERBOSE"))
    ap.add_argument("--config", type=Path,
                    default=Path(os.environ.get("WATCHER_CONFIG") or ROOT / "config.json"))
    ap.add_argument("--state", type=Path,
                    default=Path(os.environ.get("WATCHER_STATE") or ROOT / "state" / "seen.json"))
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    try:
        state = load_state(args.state)
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read state file {args.state}: {e}", file=sys.stderr)
        return 1

    term, year = cfg["target"]["term"], cfg["target"]["year"]
    mode = "DRY RUN" if args.dry_run else "SEED ONLY" if args.seed_only else "live"
    print(f"Target: {term.title()} {year} | mode: {mode} | "
          f"{len(state['seen'])} postings already in state")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    timeout = float(cfg["http"].get("timeout", 30))
    retries = int(cfg["http"].get("retries", 2))

    per_source, ok_sources, failed_sources = [], [], []
    for src in cfg["sources"]:
        if src.get("enabled") is False:
            continue
        name = src["name"]
        try:
            body = fetch(session, src["url"], timeout, retries)
            raw = PARSERS[src["type"]](src, body)
            if not raw:
                raise ValueError("parsed 0 postings (bad fetch or format change?)")
            kept, drops, examples = filter_items(src, raw, cfg)
        except Exception as e:
            print(f"{name:<14} FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            failed_sources.append(name)
            continue
        ok_sources.append(name)
        per_source.append((src, kept))
        why = ", ".join(f"{n} {r}" for r, n in drops.most_common()) or "none"
        print(f"{name:<14} {len(raw):>5} parsed -> {len(kept):>5} kept (dropped: {why})")
        if args.verbose:
            for reason, exs in examples.items():
                for ex in exs:
                    print(f"    [{reason}] {ex['company'] or '?'} | {ex['title'] or '?'} | "
                          f"{ex['season'] or ex['section'] or '-'} | {ex['url'][:90]}")

    if not ok_sources:
        print("ERROR: every source failed; state left untouched.", file=sys.stderr)
        return 1

    # Global dedupe on the ATS job key: first source in config order to list a job owns it.
    unique, owned, overlap = [], set(), Counter()
    for src, kept in per_source:
        for it in kept:
            if it["key"] in owned:
                overlap[src["name"]] += 1
                continue
            owned.add(it["key"])
            unique.append(it)
    total_kept = sum(len(k) for _, k in per_source)
    print(f"{'TOTAL':<14} {total_kept:>5} kept -> {len(unique):>5} unique after global dedupe"
          + (f" (overlap: {', '.join(f'{n} {s}' for s, n in overlap.items())})" if overlap else ""))
    if failed_sources:
        print(f"Failed sources this run: {', '.join(failed_sources)}")

    seen, seeded = state["seen"], state["sources"]
    first_run = not seen
    # Keys are derived from each entry's stored canonical URL rather than saved, so
    # improvements to job_key() apply to postings recorded before them.
    seen_keys = {dedupe_key(e["url"]) for e in seen.values() if e.get("url")}
    new = [it for it in unique if it["id"] not in seen and it["key"] not in seen_keys]
    if args.seed_only or first_run:
        to_notify = []
    else:
        # A source's first successful fetch is recorded silently too (e.g. newly added source).
        to_notify = [it for it in new if it["source"] in seeded]
    silent = len(new) - len(to_notify)
    reason = (" (first run: seeding silently)" if first_run
              else " (seed-only)" if args.seed_only else "")
    print(f"New: {len(new)} | to notify: {len(to_notify)} | recorded silently: {silent}{reason}")

    sources_by_name = {s["name"]: s for s in cfg["sources"]}
    notes = build_notifications(to_notify, cfg, sources_by_name)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and not args.dry_run:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"**{len(new)} new**, {len(to_notify)} notified, "
                     f"{len(unique)} unique postings tracked this run.\n")

    if args.dry_run:
        for it in new[:25]:
            print(f"  + [{it['source']}] {it['company'] or '?'} — {it['title'] or '?'} "
                  f"({it['location'] or '?'})  {it['canonical']}")
        if len(new) > 25:
            print(f"  … {len(new) - 25} more")
        print(f"Would send {len(notes)} notification(s) to: "
              f"{', '.join(configured_channels()) or '(no channels configured)'}")
        print("DRY RUN: nothing sent, nothing written.")
        return 0

    if notes:
        channels = configured_channels()
        if not channels:
            print("No notification channels configured; recording postings without sending.")
        else:
            ok, failed = deliver(session, notes, cfg)
            print(f"Sent {len(notes)} notification(s) via {', '.join(channels)}: "
                  f"{ok} delivered, {failed} failed")
            if ok == 0:
                print("ERROR: every delivery failed; not marking postings as seen so the "
                      "next run retries.", file=sys.stderr)
                return 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    changed = False
    for it in new:
        seen[it["id"]] = {"first_seen": today, "source": it["source"],
                          "company": it["company"][:80], "title": it["title"][:120],
                          "url": it["canonical"]}
        changed = True
    for name in ok_sources:
        if name not in seeded:
            seeded[name] = {"seeded_at": today}
            changed = True
    if changed:
        state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_state(args.state, state)
        print(f"State saved: {len(seen)} postings tracked.")
    else:
        print("No state changes.")
    return 0
