"""Parse a pasted BetOnline-style volleyball board into games + markets.

The paste format from sportsbook pages is loose (one token per line, or
row-oriented), so the parser is a tolerant tokenizer:

- a line with 3+ letters that isn't a date/time/junk word starts a TEAM row
  (two consecutive team rows = one game, away listed first)
- tokens attached to the most recent team:
    spread  : signed .5 number with |x| <= 3.5 (e.g. -1.5), odds = next
              american-odds token
    total   : token like "o4.5" / "u4.5" / "O 4.5" / "Over 4.5", odds = next
              american-odds token
    moneyline: a bare american-odds token (+/-100 or more) not consumed above

Unparsed lines are returned for debugging so format quirks are visible.
"""

from __future__ import annotations

import difflib
import re

AMERICAN = re.compile(r"^[+-]\d{3,4}$")
SPREAD = re.compile(r"^[+-]\d(?:\.5)?$")
TOTAL = re.compile(r"^(?:[ouOU]|[Oo]ver|[Uu]nder)\s*(\d(?:\.5)?)$")
JUNK = re.compile(
    r"^(mon|tue|wed|thu|fri|sat|sun|am|pm|et|ct|final|live|bet|parlay|"
    r"spread|total|moneyline|money line|game|match|sets?|vs\.?|@|\d+|"
    r"today|tomorrow([, ].*)?|starts? in.*|all markets|game period|"
    r"ncaa.*|volleyball|\*|\d{1,2}:\d{2}(:\d{2})?\s*(am|pm)?|"
    r"\d{1,2}/\d{1,2}(/\d{2,4})?)$", re.I)
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ROTATION = re.compile(r"^\d{5,7}\s*-?\s*$")

# board section markers (BetOnline): keep only the women's NCAA block
SECTION_START = "NCAA - NCAA Women"
SECTION_END = "Quick links"


def _preprocess(text: str) -> str:
    low = text.lower()
    start = low.find(SECTION_START.lower())
    if start >= 0:
        end = low.find(SECTION_END.lower(), start)
        text = text[start:end if end > 0 else len(text)]
    text = MD_LINK.sub(r"\1", text)          # [label](url) -> label
    text = re.sub(r"^\s*\*\s*", "", text, flags=re.M)  # bullet markers
    return text


OU_POINT = re.compile(r"^[OUou]\s*(\d+(?:\.5)?)$")


def _parse_blocks(lines: list[str]) -> tuple[list[dict], list[str], int]:
    """Block layout (BetOnline innerText): rotation number line, team name,
    rotation, team, then market sections whose prices alternate away/home:

        938415 -            Spread          Moneyline
        South Carolina      +1.5  +128      +254
        938416 -            -1.5  -165      -350
        Michigan State
    """
    games, unparsed = [], []
    n_oddsless = 0
    cur_teams: list[str] = []
    raw: dict[str, list[str]] = {}
    mode = None
    expect_team = False

    def flush():
        nonlocal cur_teams, raw, mode, n_oddsless
        if len(cur_teams) == 2:
            markets = _assemble_markets(raw)
            if markets:
                games.append(dict(away=cur_teams[0], home=cur_teams[1],
                                  markets=markets))
            else:
                n_oddsless += 2
        cur_teams, raw, mode = [], {}, None

    for line in lines:
        if ROTATION.match(line):
            if len(cur_teams) >= 2:
                flush()
            expect_team, mode = True, None
            continue
        if expect_team:
            cur_teams.append(line)
            expect_team = False
            continue
        low = line.lower()
        if low in ("spread", "moneyline", "total", "totals"):
            mode = "total" if low.startswith("total") else low
            raw.setdefault(mode, [])
            continue
        if mode and (AMERICAN.match(line) or SPREAD.match(line)
                     or OU_POINT.match(line)):
            raw[mode].append(line)
            continue
        mode = None  # any other line (time header, junk) ends the section
    flush()
    return games, unparsed, n_oddsless


def _assemble_markets(raw: dict) -> list[dict]:
    markets = []
    sp = raw.get("spread", [])
    pairs, i = [], 0
    while i + 1 < len(sp):
        if SPREAD.match(sp[i]) and AMERICAN.match(sp[i + 1]):
            pairs.append((float(sp[i]), int(sp[i + 1])))
            i += 2
        else:
            i += 1
    for side, pair in zip(("away", "home"), pairs):
        markets.append(dict(market="spread", side=side, point=pair[0],
                            odds=pair[1]))
    ml = [t for t in raw.get("moneyline", []) if AMERICAN.match(t)]
    for side, odds in zip(("away", "home"), ml):
        markets.append(dict(market="ml", side=side, point="", odds=int(odds)))
    tot = raw.get("total", [])
    i = 0
    while i < len(tot):
        m = OU_POINT.match(tot[i])
        if m and i + 1 < len(tot) and AMERICAN.match(tot[i + 1]):
            markets.append(dict(
                market="total",
                side="over" if tot[i][0].lower() == "o" else "under",
                point=float(m.group(1)), odds=int(tot[i + 1])))
            i += 2
        else:
            i += 1
    return markets


def parse_board(text: str) -> tuple[list[dict], list[str]]:
    """Returns (games, unparsed_lines). Each game:
    {away, home, markets: [ {market, side, point, odds} ]}, side home/away,
    spread point is the picked side's number, total side over/under."""
    pre = _preprocess(text)
    lines = [l.strip() for l in pre.splitlines() if l.strip()]
    if any(ROTATION.match(l) for l in lines):
        return _parse_blocks(lines)

    tokens = []
    for raw in pre.splitlines():
        line = raw.strip()
        if not line or ROTATION.match(line):
            continue
        # split row-oriented lines into tokens but keep multiword names whole
        parts = re.split(r"\s{2,}|\t", line)
        for p in parts:
            p = p.strip()
            if p and not ROTATION.match(p):
                tokens.append(p)

    teams, unparsed = [], []  # teams: list of dicts in order encountered
    awaiting_ou = None  # 'o'/'u' seen on its own line, number comes next

    def attach_odds(t, odds):
        pend = t.pop("pending", None)
        if pend is None:
            t.setdefault("ml", odds)  # first ML wins; strays don't overwrite
        elif pend[0] == "spread":
            t.setdefault("spread", (pend[1], odds))
        else:
            t.setdefault("totals", []).append((pend[2], pend[1], odds))

    for tok in tokens:
        low = tok.lower()
        if low in ("o", "u", "over", "under"):
            awaiting_ou = low[0]
            continue
        if awaiting_ou and re.match(r"^\d(?:\.5)?$", tok):
            if teams:
                teams[-1]["pending"] = ("total", float(tok), awaiting_ou)
            awaiting_ou = None
            continue
        awaiting_ou = None
        m_total = TOTAL.match(tok.replace(" ", ""))
        if m_total:
            if teams:
                teams[-1]["pending"] = ("total", float(m_total.group(1)),
                                        tok.lstrip()[0].lower())
            continue
        if SPREAD.match(tok):
            if teams:
                teams[-1]["pending"] = ("spread", float(tok), None)
            continue
        if AMERICAN.match(tok):
            if teams:
                attach_odds(teams[-1], int(tok))
            continue
        # inline "Team -1.5 -115 o4.5 -110 +180" rows: peel name then re-feed
        m_inline = re.match(r"^([A-Za-z][A-Za-z .&''()-]{2,}?)\s+([+-]\d.*)$",
                            tok)
        if m_inline and not JUNK.match(m_inline.group(1)):
            teams.append({"name": m_inline.group(1).strip()})
            for sub_tok in m_inline.group(2).split():
                if SPREAD.match(sub_tok):
                    teams[-1]["pending"] = ("spread", float(sub_tok), None)
                elif TOTAL.match(sub_tok):
                    mt = TOTAL.match(sub_tok)
                    teams[-1]["pending"] = ("total", float(mt.group(1)),
                                            sub_tok[0].lower())
                elif AMERICAN.match(sub_tok):
                    attach_odds(teams[-1], int(sub_tok))
            continue
        if re.search(r"[A-Za-z]{3,}", tok) and not JUNK.match(tok):
            teams.append({"name": tok})
            continue
        unparsed.append(tok)

    games = []
    # pair consecutive team rows that actually carry odds
    priced = [t for t in teams
              if any(k in t for k in ("ml", "spread", "totals"))]
    n_oddsless = len(teams) - len(priced)
    for i in range(0, len(priced) - 1, 2):
        away, home = priced[i], priced[i + 1]
        markets = []
        for side, t in (("away", away), ("home", home)):
            if "ml" in t:
                markets.append(dict(market="ml", side=side, point="",
                                    odds=t["ml"]))
            if "spread" in t:
                markets.append(dict(market="spread", side=side,
                                    point=t["spread"][0], odds=t["spread"][1]))
            for ou, point, odds in t.get("totals", []):
                markets.append(dict(market="total",
                                    side="over" if ou == "o" else "under",
                                    point=point, odds=odds))
        games.append(dict(away=away["name"], home=home["name"],
                          markets=markets))
    return games, unparsed, n_oddsless


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


# book school names whose NCAA seoname isn't fuzzy-findable
ALIASES = {
    "omaha": "neb-omaha",
    "uconn": "connecticut",
    "usc": "southern-california",
    "olemiss": "ole-miss",
    "miami": "miami-fl",
    "miamioh": "miami-oh",
    "appstate": "appalachian-st",
    "umass": "massachusetts",
    "pitt": "pittsburgh",
    "saintmarys": "saint-marys-ca",
    "stjohns": "st-johns-ny",
    "hawaii": "hawaii",
    "fau": "fla-atlantic",
    "fiu": "fiu",
    "utep": "utep",
    "byu": "byu",
    "lsu": "lsu",
    "tcu": "tcu",
    "smu": "smu",
    "ucf": "ucf",
}


def match_team(name: str, seonames: list[str]) -> tuple[str | None, float]:
    """Fuzzy-match a book team name (school + mascot) to a seoname."""
    n = _norm(name)
    for alias, seo in ALIASES.items():
        if n.startswith(alias) and seo in seonames:
            return seo, 1.0
    best, score = None, 0.0
    for seo in seonames:
        s = _norm(seo)
        r = difflib.SequenceMatcher(None, s, n).ratio()
        if s and n.startswith(s):  # 'nebraska' prefix of 'nebraskacornhuskers'
            r = max(r, 0.5 + 0.5 * len(s) / len(n))
        words = _norm("".join(name.split()[:2]))
        r = max(r, difflib.SequenceMatcher(None, s, words).ratio())
        if r > score:
            best, score = seo, r
    return (best, score) if score >= 0.62 else (None, score)


def price_market(probs6, market: str, side: str, point) -> float | None:
    """Model probability of a market from the home-perspective 6-outcome
    distribution [3-0, 3-1, 3-2, 2-3, 1-3, 0-3]. Returns None for lines we
    don't price (integer lines that can push)."""
    p30, p31, p32, p23, p13, p03 = probs6
    margins = {3: p30, 2: p31, 1: p32, -1: p23, -2: p13, -3: p03}
    totals = {3: p30 + p03, 4: p31 + p13, 5: p32 + p23}
    if market == "ml":
        home_win = p30 + p31 + p32
        return home_win if side == "home" else 1 - home_win
    if market == "spread":
        if float(point) == int(float(point)):
            return None  # integer line -> pushes; not priced in v1
        sign = 1 if side == "home" else -1
        return sum(pr for m, pr in margins.items()
                   if sign * m + float(point) > 0)
    if market == "total":
        if float(point) == int(float(point)):
            return None
        over = sum(pr for t, pr in totals.items() if t > float(point))
        return over if side == "over" else 1 - over
    return None
