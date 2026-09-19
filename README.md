# Internship watcher

A GitHub Actions job that polls five community internship lists every 20 minutes and
pushes a phone notification for each Summer 2027 internship it hasn't seen before.
There's no server and no database: the list of already-seen postings lives in
[`state/seen.json`](state/seen.json) and the workflow commits it back to this repo.

| Source | Format | Notes |
|---|---|---|
| vanshb03/Summer2027-Internships | `listings.json` | `season` is term-only ("Summer"), so a missing year defaults to Summer 2027 |
| zshah101/Automated-List-Of-Summer-2027-and-Fall-2026… | `jobs.json` | Covers two cycles, so a "Not stated" season is dropped unless the title names the year |
| SimplifyJobs/Summer2027-Internships | README, HTML tables | `↳` rows inherit the company from the row above |
| speedyapply/2027-SWE-College-Jobs | README, pipe tables | Apply link is in the Posting column |
| LorenzoLaCorte/european-tech-internships-2026 | README, pipe tables | Mostly new-grad roles from the 2026 cycle. Expect 0 kept postings. |

## ⚠️ Use a public repo

A `*/20` cron runs about **72 times a day**. On a **private** repo, each run is billed
as at least one minute, so it will use up the 2,000 free Actions minutes per month in
well under a month. Actions minutes are free on **public** repos. Your secrets stay
private either way; only the code and `state/seen.json` (a list of public job links)
are visible.

Other GitHub scheduling behavior to expect:

- **Scheduled runs are often 5–30 minutes late**, and GitHub may skip some runs when
  its runners are busy. "Every 20 minutes" really means "a few times an hour."
- **GitHub disables scheduled workflows on a public repo after 60 days with no repo
  activity.** The bot's state commits usually keep the repo active, but in a slow
  season GitHub can still disable it and email you. To turn it back on, go to
  Actions → *Watch internship repos* → **Enable workflow**.

## Setup

1. **Create a public repo** and push these files to it.
2. **Pick a notification channel** and add its values as repository secrets
   (Settings → Secrets and variables → Actions → *New repository secret*). You can set
   up more than one channel; each notification goes to every channel that's configured.

   | Channel | Secrets |
   |---|---|
   | ntfy (recommended, free) | `NTFY_TOPIC`, optionally `NTFY_SERVER` and `NTFY_TOKEN` |
   | Pushover | `PUSHOVER_TOKEN`, `PUSHOVER_USER` |
   | Discord | `DISCORD_WEBHOOK_URL` |

3. **Check write permission.** The workflow asks for `contents: write`. If your
   account or organization defaults to read-only tokens, open Settings → Actions →
   General → *Workflow permissions* and select **Read and write permissions**.
4. **Seed the state.** Go to Actions → *Watch internship repos* → **Run workflow**.
   The first run with an empty state records every current posting (about 2,700)
   **without notifying you**. You can tick `seed_only` to make that explicit.
5. **Send a test notification.** Go to Actions → *Test notification* → **Run workflow**.
   - Your phone should get one `[TEST]` alert, formatted exactly like a real one.
     Tapping it opens that posting's apply link.
   - The run fails (red ✗) if no channel is configured or any channel rejects the
     message, and the log says why.
   - It never changes `state/seen.json`.

   You can do the same locally with `NTFY_TOPIC=… python watcher.py --test-notify`.
6. That's it. From then on, every scheduled run notifies you only about postings that
   are new since the last run.

> **Use repository secrets, not environment secrets.** Secrets stored in a GitHub
> *environment* are only given to jobs that name that environment, and these workflows
> don't. If the test says "no notification channels configured", that's usually why.

### The ntfy topic secret

On ntfy.sh, a topic name works like a password: **anyone who knows the name can read
your notifications and send to it.** Use a long random name, not `internships`:

```sh
python -c "import secrets; print('intern-' + secrets.token_urlsafe(18))"
```

1. Install the ntfy app ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   / [iOS](https://apps.apple.com/app/ntfy/id1625396347)) and subscribe to that topic.
2. Save the same string as the `NTFY_TOPIC` repository secret.
3. If you self-host ntfy or use access tokens, also set `NTFY_SERVER`
   (for example `https://ntfy.example.com`) and `NTFY_TOKEN`.

Each notification is sent as JSON to the server root, so company names with accents
or emoji display correctly. Tapping a notification opens the apply link.

### How many notifications to expect

- **Each run sends at most 13:** up to `max_individual` (12) individual alerts, plus
  one "+N more" summary.
- **Typical volume:**
  - In mid-September 2026 these lists added about **74** new postings a day after
    filtering and dedupe, with a peak of about 150.
  - They arrive in batches across the day's ~72 runs, so expect roughly **50–100
    alerts a day** in peak season and far fewer later.
- **ntfy.sh free tier:** **250 messages a day** per IP address, plus a burst limit of
  60 requests that refills at one per 5 seconds.
  - Normal use stays well under that.
  - The theoretical worst case is 72 runs × 13 = 936.
  - If the limit is already hit when a run starts, every delivery fails. That run's
    postings aren't marked as seen, so a later run retries them.
  - If the limit is hit partway through a run, the alerts sent before it still arrive,
    but the rest of that run's alerts are skipped.
  - To get fewer alerts, lower `max_individual`, or narrow the filters with
    `title_include` / `location_include`.
- **Other channels:**
  - Pushover allows 10,000 messages a month per app.
  - Discord webhooks have no daily cap, but they are rate-limited per request, which
    `notify.py` handles by retrying.

## How "new" is decided

- Every apply URL is **canonicalized**:
  - tracking parameters are stripped (`utm_*`, `ref`, `source`, `gh_src`, `iis`,
    `mobile`, …); `gh_jid` and `token` are kept because they identify the job
  - the host is lowercased and `www.` is dropped
  - trailing slashes are removed
  - the remaining query parameters are sorted
  - the scheme is forced to `https`
- Boards often link **the same job at different URLs**, for example:
  - `…/apply` or `…/application` suffixes
  - `boards.` vs `job-boards.greenhouse.io`
  - Workday locale segments and different Workday routes

  So a posting is identified by its **job key**: the tracking system's own job ID,
  pulled out of the URL.

  | System | Job key |
  |---|---|
  | Greenhouse | `greenhouse:<id>` |
  | Lever / Ashby | `lever:<uuid>` / `ashby:<uuid>` |
  | Workday | `workday:<tenant>:<requisition>` |
  | iCIMS | `icims:<tenant>:<id>` |

  SmartRecruiters, Amazon, TikTok, LinkedIn, Workable, Apple and Jobvite links get
  keys the same way. A link from any other site uses its canonical URL as the key.
- A posting is **new** if neither its URL ID (`sha1(canonical_url)[:16]`, the key in
  `state/seen.json`) nor its job key has been seen before. Job keys for recorded
  postings are recomputed from their stored `url` on every run. That way, an
  improvement to `job_key()` also covers postings recorded before it, without a state
  migration.
- Dedupe is **global** and happens *after* filtering. When several repos list the same
  job, the first source in `config.json` order that keeps it owns it, and you get one
  notification. If one board's copy is filtered out (for example because of a wrong
  location), another board's copy can still get through.
- A run sends at most `max_individual` (default 12) individual notifications. Anything
  beyond that goes into a single "+N more new Summer 2027 postings" summary, because
  these repos sometimes add 50+ roles at once.

### Safety rails

- **Empty state → silent seed.** The first run never notifies.
- **A newly added source → silent seed.** The first successful fetch of a source that
  isn't in the state yet is recorded without notifying, so adding a source to
  `config.json` doesn't flood you.
- **One source fails:** it's logged, and the run continues with the others.
- **Every source fails:** the run exits non-zero and leaves the state untouched, so a
  bad fetch can't make old postings look new later.
- **Every notification fails** (for example, ntfy is down): the run exits non-zero and
  doesn't save the new postings, so the next run tries again.
- **Corrupt `seen.json`:** the run exits non-zero instead of overwriting it.
- **Format change in a README table:** the parser pulls apply links out of the raw
  text and only then fills in company, title, and location from the table row. If a
  table layout changes, you get less informative notifications, but the run doesn't
  crash.

## Filter knobs (`config.json`)

```jsonc
"target":  { "term": "summer", "year": 2027 },
"filters": {
  "include_inactive": false,   // keep postings a source marks closed (active / is_open false)
  "include_unstated": false,   // keep postings with no season info when the source has no default_season
  "section_exclude":  "(new.?grad|full.?time|phd|return offer)",  // matched against the README heading above the row
  "title_exclude":    "(new.?grad|university.?grad|entry.?level)",
  "title_include":    null,    // e.g. "(software|swe|backend|ml|data)" to keep only matching titles
  "location_include": null,    // e.g. "(remote|new york|ny|san francisco|sf)"
  "countries": ["US", "CA", "UK"]  // null to allow every country
}
```

- All regexes are case-insensitive.
- Title filters are skipped for any posting whose title couldn't be recovered, and
  `location_include` is skipped for any posting with no location. A posting is never
  dropped just because data is missing.
- `countries` keeps a posting if **any** of its locations is in an allowed country.
  So "London, UK; Singapore" passes, and "Dublin, Ireland" doesn't.
  - Supported codes are `US`, `CA` and `UK` (`GB` is accepted as an alias).
  - Locations are matched on state and province codes and names, country names, and
    major cities.
  - Locations whose country can't be recognized, like a bare "Remote", are kept.
  - Postings removed here show up as the `country` drop reason.
  - speedyapply sometimes geocodes wrongly (for example "Bellevue, Australia" for
    Bellevue, WA). Such jobs still get through when another board lists the real
    location.
- Any filter key can also be set on a single source to override the global value.
  For example, `"section_exclude": null` on one source turns section filtering off for
  just that source.
- Each source has a `default_season`. It's `"Summer 2027"` for the single-cycle repos
  (vanshb03, SimplifyJobs, speedyapply) and `null` for zshah101 and euro-tech.

### Season classification

`classify_season()` looks at the season field, title, URL, README section, and
location, and returns `match`, `reject`, or `unknown`:

1. **Term + year pairs**, in either order: "Summer 2027", "2027 Summer",
   "Summer-2027", "Summer '27", or "Summer/Fall 2027" (the year applies to every term
   in the list). If any pair is Summer 2027, it's a **match**, even alongside other
   pairs ("Winter 2027 – Summer 2027"). If there are only other pairs, it's a
   **reject**.
2. It collects **every year mentioned**, including the `'26` form ("June '26 – Dec '26").
3. **Term-only season field** (vanshb03):
   - reject if the term isn't summer
   - reject if another year appears anywhere
   - match if 2027 appears
   - otherwise unknown
4. **Right year, wrong half:** if 2027 appears, an off-season month is named
   (January–April or September–December), and "summer" never appears, it's a reject.
   This catches "Co-op: January – June 2027".
5. **Otherwise:** match if 2027 appears, reject if only other years appear, and
   unknown if there's no year.

An `unknown` result falls back to the source's `default_season`. If there isn't one,
the posting is dropped unless `include_unstated` is `true`.

**If you loosen a filter**, the next run will see hundreds of postings that were
previously filtered out and report them as new. They're capped at 12 individual
notifications plus one summary. To avoid even that, run the workflow once with
`seed_only` checked after changing the filters.

## Running locally

```sh
pip install -r requirements.txt
DRY_RUN=1 python watcher.py              # fetch, filter, diff, and print; no sends, no writes
DRY_RUN=1 VERBOSE=1 python watcher.py    # also show example postings for each drop reason
SEED_ONLY=1 python watcher.py            # mark everything as seen without notifying
```

Each source prints a line explaining what was filtered:

```
vanshb03         471 parsed ->   216 kept (dropped: 155 season, 100 inactive)
zshah101        1341 parsed ->   585 kept (dropped: 414 inactive, 299 unstated, 43 season)
```

Drop reasons:

| Reason | Meaning |
|---|---|
| `season` | Classified as another cycle |
| `unstated` | No season info and no source default |
| `inactive` | The source marks the posting closed |
| `section` / `title` / `location` | Removed by the matching regex filter |
| `country` | Every recognized location is outside `countries` |
| `dup` | The same URL appears twice in one source |
| `bad url` | The link isn't a usable http(s) URL |

Other environment variables: `WATCHER_CONFIG` and `WATCHER_STATE` override the config
and state file paths.

## Code layout

`watcher.py` is only the entry point. The code lives in [`internwatch/`](internwatch/):

| Module | Responsibility |
|---|---|
| [`cli.py`](internwatch/cli.py) | Runs each pass: fetch, filter, global dedupe, diff against state, notify, save |
| [`parsers.py`](internwatch/parsers.py) | JSON feeds and README link extraction with table-row enrichment |
| [`season.py`](internwatch/season.py) | `classify_season()` |
| [`filtering.py`](internwatch/filtering.py) | Per-source filters and drop-reason counts |
| [`urls.py`](internwatch/urls.py) | URL canonicalization, ATS job keys (the dedupe key), ATS allow/deny lists |
| [`location.py`](internwatch/location.py) | Recognizes US / Canada / UK / other countries in location text |
| [`notify.py`](internwatch/notify.py) | ntfy, Pushover, and Discord senders, plus the individual-ping cap and summary |
| [`config.py`](internwatch/config.py) | `config.json` loading and default filter/notification settings |
| [`state.py`](internwatch/state.py) | Reads `state/seen.json` and writes it atomically |
