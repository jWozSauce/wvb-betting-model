"""Injury/lineup news scanner via Google News RSS (no API key needed).

There is no injury report in NCAA volleyball; the news lives in beat-writer
articles. Google News RSS reaches those with a per-team query. One request
per team; callers should cache.
"""

from __future__ import annotations

import re
import urllib.parse
from xml.etree import ElementTree

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
KEYWORDS = ('injury OR injured OR "out for" OR sidelined OR questionable '
            'OR "did not play" OR "return" OR illness OR surgery OR lineup')
INJURY_RE = re.compile(
    r"injur|out for|sidelined|question|did not play|return|illness|surgery|"
    r"boot|doubtful|miss(es|ed|ing)? (the )?(match|game|season)|"
    r"leaves? with|exits?|absen", re.I)

# seoname -> searchable school name; heuristic plus fixes for odd ones
SEARCH_NAMES = {
    "neb-omaha": "Omaha Mavericks",
    "southern-california": "USC Trojans",
    "ill-chicago": "UIC Flames",
    "texas-am": "Texas A&M",
    "miami-fl": "Miami Hurricanes",
    "ole-miss": "Ole Miss",
    "la-lafayette": "Louisiana Ragin Cajuns",
    "la-monroe": "ULM Warhawks",
    "fla-atlantic": "Florida Atlantic",
    "south-fla": "South Florida",
}


def search_name(seo: str) -> str:
    if seo in SEARCH_NAMES:
        return SEARCH_NAMES[seo]
    name = seo.replace("-", " ")
    name = re.sub(r"\bst$", "state", name)
    name = re.sub(r"^st\b", "saint", name)
    return name


def team_news(seo: str, days: int = 7, limit: int = 8) -> list[dict]:
    """Recent injury-ish headlines for one team. Each item: title, source,
    date, link, flagged (title matches injury keywords)."""
    q = f'"{search_name(seo)}" volleyball ({KEYWORDS}) when:{days}d'
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en")
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        root = ElementTree.fromstring(r.content)
    except Exception:
        return []
    out = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title") or "").strip()
        out.append({
            "team": seo,
            "title": title,
            "date": (it.findtext("pubDate") or "")[:16],
            "link": it.findtext("link") or "",
            "flagged": bool(INJURY_RE.search(title)),
        })
    return out
