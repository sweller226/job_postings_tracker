"""Recognize which countries a free-text location string refers to.

Only the US, Canada and the UK are recognized by name; everything else that can be
identified (a foreign country, ISO3 code or major city) is reported as "OTHER".
"""
from __future__ import annotations

import re

SUPPORTED = frozenset(("US", "CA", "UK"))
_ALIASES = {"USA": "US", "CAN": "CA", "CANADA": "CA", "GB": "UK", "GBR": "UK"}

_US_STATES = (
    "alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|"
    "hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|"
    "michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|"
    "new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|"
    "rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|"
    "west virginia|wisconsin|wyoming|district of columbia"
)
_US_CITIES = (
    "nyc|san francisco|bay area|silicon valley|seattle|boston|chicago|austin|denver|los angeles|"
    "san jose|san diego|atlanta|dallas|houston|miami|philadelphia|pittsburgh|palo alto|"
    "mountain view|menlo park|sunnyvale|cupertino|redmond|santa clara|san mateo|new york city"
)
_STATE_CODES = (
    "A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|"
    "S[CD]|T[NX]|UT|V[AT]|W[AIVY]"
)
_CA_PLACES = (
    "canada|ontario|british columbia|qu[eé]bec|alberta|manitoba|nova scotia|new brunswick|"
    "saskatchewan|toronto|vancouver|montr[eé]al|ottawa|waterloo|calgary|edmonton|markham|"
    "mississauga|kitchener|winnipeg|burnaby"
)
_UK_PLACES = (
    "uk|u\\.k\\.|united kingdom|great britain|england|scotland|wales|northern ireland|london|"
    "manchester|edinburgh|glasgow|oxford|bristol|belfast|leeds|cardiff|sheffield|nottingham|"
    "liverpool|newcastle"
)
_OTHER_PLACES = (
    # countries ("new mexico" and "northern ireland" are excluded by lookbehind below)
    "china|india|japan|korea|singapore|taiwan|hong kong|germany|france|netherlands|ireland|"
    "switzerland|spain|italy|poland|sweden|norway|denmark|finland|belgium|austria|portugal|"
    "czech republic|czechia|romania|hungary|greece|turkey|t[uü]rkiye|israel|united arab emirates|"
    "uae|saudi arabia|qatar|egypt|south africa|nigeria|kenya|australia|new zealand|brazil|"
    "mexico|argentina|chile|colombia|peru|costa rica|philippines|vietnam|thailand|malaysia|"
    "indonesia|pakistan|bangladesh|sri lanka|ukraine|serbia|croatia|bulgaria|estonia|latvia|"
    "lithuania|luxembourg|cayman islands|puerto rico|"
    # major cities, for locations that name no country
    "bangalore|bengaluru|hyderabad|pune|mumbai|chennai|gurgaon|gurugram|noida|delhi|beijing|"
    "shanghai|shenzhen|hangzhou|guangzhou|chengdu|yinchuan|tokyo|osaka|seoul|taipei|sydney|"
    "melbourne|berlin|munich|m[uü]nchen|frankfurt|hamburg|paris|amsterdam|dublin|z[uü]rich|"
    "geneva|madrid|barcelona|milan|rome|warsaw|krak[oó]w|prague|bucharest|budapest|stockholm|"
    "copenhagen|oslo|helsinki|lisbon|brussels|vienna|tel aviv|haifa|dubai|abu dhabi|riyadh|"
    "cairo|lagos|nairobi|johannesburg|cape town|s[aã]o paulo|buenos aires|bogot[aá]|manila|"
    "ho chi minh|hanoi|bangkok|kuala lumpur|jakarta|istanbul|athens"
)
_ISO3_OTHER = (
    "CHN|IND|JPN|KOR|SGP|TWN|HKG|DEU|FRA|NLD|IRL|CHE|ESP|ITA|POL|SWE|ISR|ARE|AUS|BRA|MEX|PHL|"
    "VNM|MYS|IDN|ROU|CZE|PRT|BEL|AUT|DNK|NOR|FIN|HUN|TUR|ZAF|ARG|COL|CRI|EGY|SAU|NZL"
)


def _words(alternation: str) -> str:
    return rf"(?<![a-z])(?:{alternation})(?![a-z])"


_PATTERNS = {
    "US": [
        re.compile(_words(r"usa|u\.s\.a?\.?|united states(?: of america)?|washington,? d\.?c\.?|"
                          + _US_STATES + "|" + _US_CITIES), re.I),
        # Case-sensitive codes: "Remote, US", "US-IA-CEDAR RAPIDS", "Atlanta GA", "Irvine, CA"
        re.compile(rf"(?<![A-Za-z])(?:US|{_STATE_CODES}|SF|LA)(?![A-Za-z])"),
    ],
    "CA": [
        re.compile(_words(_CA_PLACES), re.I),
        re.compile(r"(?<![A-Za-z])(?:CAN)(?![A-Za-z])|,\s*(?:ON|BC|QC|AB|MB|NS|NB|SK)(?![A-Za-z])"),
    ],
    "UK": [
        re.compile(_words(_UK_PLACES), re.I),
        re.compile(r"(?<![A-Za-z])(?:GBR?)(?![A-Za-z])"),
    ],
    "OTHER": [
        re.compile(r"(?<!new )(?<!northern )" + _words(_OTHER_PLACES), re.I),
        re.compile(rf"(?<![A-Za-z])(?:{_ISO3_OTHER})(?![A-Za-z])"),
    ],
}


def normalize_countries(codes) -> frozenset[str] | None:
    """Config value -> set of supported codes, or None to disable the filter."""
    if not codes:
        return None
    out = set()
    for code in codes:
        c = _ALIASES.get(str(code).strip().upper(), str(code).strip().upper())
        if c not in SUPPORTED:
            raise ValueError(f"countries: {code!r} is not supported (use {sorted(SUPPORTED)})")
        out.add(c)
    return frozenset(out)


def countries_in(location: str) -> set[str]:
    """Every country code recognized in a location string: "US", "CA", "UK" or "OTHER"."""
    return {code for code, pats in _PATTERNS.items() if any(p.search(location) for p in pats)}
