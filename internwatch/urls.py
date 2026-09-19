"""Apply-URL canonicalization, ATS job keys (the dedupe key) and ATS link detection."""
from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = frozenset(p.lower() for p in """
    ref referrer source src gh_src jr_id ittk iis iisn feedId mobile needsRedirect
    jan1offset jun1offset width height bga no_int_redir nl fr lang selected_lang
    embed ats icims tags s career_ns from
""".split())


def canonicalize(url: str) -> str | None:
    """Normalize an apply URL so the same job listed by different repos collides.

    gh_jid and token are deliberately kept: they identify the job.
    """
    try:
        parts = urlsplit(html.unescape(url.strip()))
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parts.path.rstrip("/")
    query = sorted({
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() in TRACKING_PARAMS)
    })
    # Keep hash-routed paths (#/job/123) since some career sites use them; drop anchors.
    fragment = parts.fragment if parts.fragment.startswith(("/", "!/")) else ""
    return urlunsplit(("https", netloc, path, urlencode(query), fragment))


def url_id(canonical: str) -> str:
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


# (host suffix, key prefix, pattern over the path). All groups are joined into the key.
_PATH_KEYS = (
    ("greenhouse.io", "greenhouse", r"/jobs/(\d{5,})"),
    ("lever.co", "lever", r"^/[^/]+/([0-9a-f]{8}-[0-9a-f-]{27})"),
    ("ashbyhq.com", "ashby", r"^/[^/]+/([0-9a-f]{8}-[0-9a-f-]{27})"),
    ("smartrecruiters.com", "smartrecruiters", r"^/[^/]+/(\d{6,})"),
    ("amazon.jobs", "amazon", r"/jobs/(\d+)"),
    ("lifeattiktok.com", "tiktok", r"/search/(\d+)"),
    ("linkedin.com", "linkedin", r"/jobs/view/(?:[^/]*-)?(\d{6,})"),
    ("jobs.apple.com", "apple", r"/details/(\d[\w-]*)"),
    ("workable.com", "workable", r"/j/([0-9a-z]+)"),
    ("jobvite.com", "jobvite", r"^/([^/]+)/job/(\w+)"),
    ("icims.com", "icims", r"/jobs/(\d+)"),
)
# Workday puts the requisition ID after the last underscore of the title segment:
# ..._JR2026520976-1, ..._REQ-020109, ..._R031642
_WORKDAY_REQ_RE = re.compile(r"_((?:[a-z]{1,5}-?)?\d{3,}[\w.-]*)$", re.I)


def _workday_key(host: str, path: str) -> str | None:
    segs = [s for s in path.split("/") if s]
    if host.endswith(".myworkdaysite.com"):
        # wd5.myworkdaysite.com/[en-US/]recruiting/<tenant>/<site>/job/...
        lower = [s.lower() for s in segs]
        if "recruiting" not in lower or lower.index("recruiting") + 1 >= len(segs):
            return None
        tenant = segs[lower.index("recruiting") + 1]
    else:
        tenant = host.split(".")[0]  # <tenant>.wd5.myworkdayjobs.com
    for seg in reversed(segs):  # skip trailing /apply, /applyManually
        m = _WORKDAY_REQ_RE.search(seg)
        if m:
            return f"workday:{tenant}:{m.group(1)}"
    return None


def job_key(canonical: str) -> str | None:
    """The ATS's own identifier for a job, or None when the URL isn't from a known ATS.

    Boards link one job at different URLs: /apply and /application suffixes, locale
    segments, boards. vs job-boards. hosts, different Workday routes. The job ID inside
    those URLs is stable, so it's the better dedupe key.
    """
    parts = urlsplit(canonical)
    host, path = (parts.hostname or "").lower(), parts.path
    query = dict(parse_qsl(parts.query))
    key = None
    if query.get("gh_jid", "").isdigit():  # Greenhouse, including embeds on company sites
        key = f"greenhouse:{query['gh_jid']}"
    elif host.endswith((".myworkdayjobs.com", ".myworkdaysite.com")):
        key = _workday_key(host, path)
    else:
        for suffix, prefix, pattern in _PATH_KEYS:
            if host == suffix or host.endswith("." + suffix):
                if prefix == "greenhouse" and query.get("token", "").isdigit():
                    key = f"greenhouse:{query['token']}"  # boards.greenhouse.io/embed/job_app
                elif m := re.search(pattern, path, re.I):
                    tenant = [host.removesuffix(".icims.com")] if prefix == "icims" else []
                    key = ":".join([prefix, *tenant, *m.groups()])
                break
    return key.lower() if key else None


def dedupe_key(canonical: str) -> str:
    """What makes two postings "the same job": the ATS job ID, else the canonical URL."""
    return job_key(canonical) or canonical


ATS_HOST_SUBSTRINGS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "myworkdaysite.com",
    "icims.com", "smartrecruiters.com", "jobvite.com", "taleo.net", "successfactors.",
    "sapsf.", "oraclecloud.com", "workable.com", "breezy.hr", "rippling.com", "bamboohr.com",
    "paylocity.com", "eightfold.ai", "avature.net", "pinpointhq.com", "applytojob.com",
    "jibeapply.com", "hiringthing.com", "careerpuck.com", "workatastartup.com", "amazon.jobs",
    "lifeattiktok.com", "jobs.apple.com", "ultipro.com", "ukg.net", "workforcenow.adp.com",
    "dayforcehcm.com", "recruitee.com", "teamtailor.com", "personio.", "jobs.gem.com",
    "dover.com", "paycomonline.net", "trinethire.com", "comeet.com", "join.com",
    "wellfound.com", "metacareers.com", "joinbytedance.com", "zohorecruit.", "freshteam.com",
    "recruiterbox.com", "hire.withgoogle.com", "jazzhr.com", "phenompeople.com",
)
ATS_HOST_PREFIXES = ("jobs.", "careers.", "apply.", "recruiting.", "job-boards.", "boards.")
ATS_PATH_MARKERS = ("/careers", "/jobs", "/job/", "/openings", "/positions", "/apply")

# Any subdomain of these is rejected.
DENY_DOMAINS = (
    "github.com", "githubusercontent.com", "shields.io", "imgur.com", "cloudinary.com",
    "simplify.jobs", "pittcsc.org", "swelist.com",
)
# Social sites: rejected on the bare/www/m host only, so e.g. lifeattiktok.com survives.
SOCIAL_HOSTS = frozenset((
    "twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com", "youtu.be",
    "tiktok.com", "reddit.com", "discord.gg", "discord.com", "t.me", "medium.com",
    "bsky.app", "threads.net",
))


def _host_of(url: str) -> tuple[str, str, str] | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    return parts.scheme.lower(), host.removeprefix("www."), parts.path.lower()


def looks_like_ats(url: str) -> bool:
    parsed = _host_of(url)
    if not parsed:
        return False
    scheme, host, path = parsed
    if scheme not in ("http", "https"):
        return False  # also covers mailto:
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return path.startswith("/jobs/view")
    if any(host == d or host.endswith("." + d) for d in DENY_DOMAINS):
        return False
    if host.removeprefix("m.") in SOCIAL_HOSTS:
        return False
    if any(s in host for s in ATS_HOST_SUBSTRINGS):
        return True
    if host.startswith(ATS_HOST_PREFIXES) or host.endswith(".jobs"):
        return True
    return any(m in path for m in ATS_PATH_MARKERS)
