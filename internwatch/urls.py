"""Apply-URL canonicalization (the dedupe key) and ATS link detection for READMEs."""
from __future__ import annotations

import hashlib
import html
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
