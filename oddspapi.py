"""Live NCAA W volleyball odds from OddsPapi (api.oddspapi.io).

Free tier: 250 requests/month. One /odds-by-tournaments call per bookmaker
per fetch counts as ONE request no matter how many fixtures come back;
/v4/account (quota usage) and /v4/historical-odds are always free.

Decoding uses the static market reference (app_data/oddspapi_markets_vb.json,
sportId 23): marketId 231 = match winner, "Set Handicap" markets carry the
line in their `handicap` field (one marketId per line), "Over Under" totals
likewise. Outcome "1" belongs to participant1, which OddsPapi lists as the
HOME team (verified against the NCAA schedule 2026-09-26); the app's venue
lookup still cross-checks and flags home mismatches.

fetch_board() returns games shaped exactly like paste_odds.parse_board's,
so the Best bets tab prices them with the same code path. Each market is
the BEST price across the requested books (line shopping, book recorded),
plus a pre-computed devig anchor (mkt_prob) from the highest-priority book
quoting both sides — Pinnacle first, since it's the sharp book.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import kelly
import safe_http

API = "https://api.oddspapi.io/v4"
TOURNAMENT_NCAAW = "43847"
SPORT_ID = 23
# Legacy rollback set; T15 defaults follow the planner coverage ruling.
LEGACY_BOOKS = ("pinnacle", "draftkings", "fanduel", "betonline.ag")
BOOKS = ("sbobet", "draftkings", "hardrockbet", "1xbet", "bwin")
# Non-default sharp books retain priority when the owner explicitly tests them.
ANCHOR_ONLY_BOOKS = frozenset({"1xbet", "bwin", "unibet", "sbobet", "bcgame", "cloudbet"})
ANCHOR_PRIORITY = ("pinnacle", "pinnacle+5", "pinnacle+30", "sbobet", "draftkings", "hardrockbet", "1xbet", "bwin")


def available_books():
    """Read a supplied provider catalog without making a billable catalog call.

    Until the planner supplies that artifact, show the known existing/default
    books only and explicitly report that the catalog is incomplete.
    """
    path = HERE / "app_data" / "oddspapi_bookmakers.json"
    if not path.exists():
        return tuple(dict.fromkeys((*BOOKS, *LEGACY_BOOKS))), False
    raw = json.loads(path.read_text())
    if (not isinstance(raw, list) or not raw or
            any(not isinstance(row, dict) or not isinstance(row.get("slug"), str)
                or not row["slug"].strip() for row in raw)):
        raise ValueError("Invalid bookmaker catalog")
    slugs = set(row["slug"] for row in raw)
    if not set(BOOKS) <= slugs:
        raise ValueError("Bookmaker catalog is missing a default book")
    return tuple(sorted(slugs)), True


def order_books(selected):
    """Stable anchor priority, independent of multiselect click order."""
    chosen = set(selected)
    return tuple(b for b in ANCHOR_PRIORITY if b in chosen) + tuple(
        sorted(chosen - set(ANCHOR_PRIORITY)))

def default_books():
    return BOOKS if os.environ.get("WVB_ENABLE_BOOK_SELECTION", "0") == "1" else LEGACY_BOOKS

HERE = Path(__file__).resolve().parent
LOCAL_KEY = HERE / "oddspapi_key.txt"  # gitignored
ET = ZoneInfo("America/New_York")


def api_key() -> str:
    try:
        import streamlit as st
        if "ODDSPAPI_KEY" in st.secrets:
            return st.secrets["ODDSPAPI_KEY"]
    except Exception:
        pass
    if LOCAL_KEY.exists():
        return LOCAL_KEY.read_text().strip()
    raise RuntimeError("No OddsPapi key: add ODDSPAPI_KEY to Streamlit "
                       "secrets or keep oddspapi_key.txt beside the app.")


def _markets_map() -> dict:
    raw = json.loads(
        (HERE / "app_data" / "oddspapi_markets_vb.json").read_text())
    return {str(m["marketId"]): m for m in raw}


def _participants() -> dict:
    return json.loads(
        (HERE / "app_data" / "oddspapi_participants_vb.json").read_text())


def _decode_book(markets_json: dict, mktmap: dict) -> list[dict]:
    """One bookmaker's markets blob -> flat [{market, side, point, odds,
    dec}] in the app's encoding (side home/away/over/under, point = picked
    side's line). Integer lines are dropped (the pricer can't push)."""
    rows = []
    for mid, m in (markets_json or {}).items():
        ref = mktmap.get(str(mid))
        if not ref or ref.get("playerProp") or ref.get("period") != "result":
            continue
        mtype = ref["marketType"]
        if mtype not in ("moneyline", "spreads", "totals"):
            continue
        h = float(ref.get("handicap") or 0.0)
        if mtype in ("spreads", "totals") and h == int(h):
            continue
        oname = {str(o["outcomeId"]): o["outcomeName"]
                 for o in ref["outcomes"]}
        for oid, o in (m.get("outcomes") or {}).items():
            pl = (o.get("players") or {}).get("0") or {}
            if not pl.get("active") or not pl.get("priceAmerican"):
                continue
            try:
                odds = int(str(pl["priceAmerican"]).replace("+", ""))
            except ValueError:
                continue
            name = str(oname.get(str(oid)))
            if mtype == "moneyline":
                mk, side, point = "ml", "home" if name == "1" else "away", ""
            elif mtype == "spreads":
                mk = "spread"
                side = "home" if name == "1" else "away"
                point = h if name == "1" else -h
            else:
                mk, side, point = "total", name.lower(), h
                if side not in ("over", "under"):
                    continue
            rows.append(dict(
                market=mk, side=side, point=point, odds=odds,
                dec=float(pl.get("price")
                          or kelly.american_to_decimal(odds))))
    return rows


def _pair_key(mk: str, side: str, point):
    """Complement-pair identity for devig: both sides of one line."""
    if mk == "spread":
        return ("spread", point if side == "home" else -point)
    return (mk, point)


def fetch_board(books=None, key: str | None = None, timeout: int = 60):
    """One API request per book. Returns (games, n_requests) with games in
    paste_odds.parse_board shape + extras: each market has book / mkt_prob /
    devig_book, each game has date (ET) alongside time."""
    books = default_books() if books is None else tuple(dict.fromkeys(books))
    if not books:
        return [], 0
    key = key or api_key()
    mktmap, names = _markets_map(), _participants()
    fixtures: dict = {}
    for i, bk in enumerate(books):
        if i:
            time.sleep(1.1)  # endpoint has a ~1s per-call cooldown
        r = safe_http.get(f"{API}/odds-by-tournaments",
                         params={"apiKey": key,
                                 "tournamentIds": TOURNAMENT_NCAAW,
                                 "bookmaker": bk, "oddsFormat": "american"},
                         timeout=timeout)
        if r.status_code == 404:  # FIXTURE_NOT_FOUND: book has no board now
            continue
        r.raise_for_status()
        for f in r.json():
            fx = fixtures.setdefault(f["fixtureId"],
                                     {"meta": f, "books": {}})
            bo = (f.get("bookmakerOdds") or {}).get(bk)
            if bo and not bo.get("suspended"):
                fx["books"][bk] = _decode_book(bo.get("markets"), mktmap)

    games = []
    for fx in fixtures.values():
        f = fx["meta"]
        if f.get("statusId") != 0:  # live or finished — not bettable pregame
            continue
        start = dt.datetime.fromisoformat(
            f["startTime"].replace("Z", "+00:00")).astimezone(ET)
        home = names.get(str(f["participant1Id"]), str(f["participant1Id"]))
        away = names.get(str(f["participant2Id"]), str(f["participant2Id"]))

        best: dict = {}  # (market, side, point) -> best-priced row
        for bk in books:
            if bk in ANCHOR_ONLY_BOOKS:
                continue  # information-only books cannot supply actionable bet prices
            for row in fx["books"].get(bk, []):
                k = (row["market"], row["side"], row["point"])
                if k not in best or row["dec"] > best[k]["dec"]:
                    best[k] = {**row, "book": bk}
        # devig anchor per line: first book (priority order) with both sides
        anchors: dict = {}
        for bk in books:
            sides: dict = {}
            for row in fx["books"].get(bk, []):
                sides.setdefault(
                    _pair_key(row["market"], row["side"], row["point"]),
                    {})[row["side"]] = row["odds"]
            for pk, two in sides.items():
                if len(two) == 2 and pk not in anchors:
                    (s1, o1), (s2, o2) = two.items()
                    p1, p2 = kelly.vig_free_probs(o1, o2)
                    anchors[pk] = {s1: p1, s2: p2, "book": bk}
        markets = []
        for (mk, side, point), b in sorted(best.items(), key=str):
            dv = anchors.get(_pair_key(mk, side, point))
            markets.append(dict(
                market=mk, side=side, point=point, odds=b["odds"],
                book=b["book"],
                mkt_prob=round(dv[side], 4) if dv else None,
                devig_book=dv["book"] if dv else ""))
        if markets:
            games.append(dict(
                away=away, home=home, markets=markets,
                fixture_id=str(f["fixtureId"]),
                home_participant_id=str(f["participant1Id"]),
                away_participant_id=str(f["participant2Id"]),
                time=start.strftime("%I:%M %p").lstrip("0"),
                date=str(start.date()), _start=start))
    games.sort(key=lambda g: g.pop("_start"))
    for i, g in enumerate(games):
        g["board_pos"] = i + 1
    return games, len(books)


def account(key: str | None = None) -> dict:
    """Quota usage — free endpoint, never counts against the limit."""
    r = safe_http.get(f"{API}/account", params={"apiKey": key or api_key()},
                     timeout=30)
    r.raise_for_status()
    return r.json()
