"""Backfill historical NCAA W volleyball odds from OddsPapi.

/v4/historical-odds is always FREE (doesn't count against the request
quota) but has a 5-second per-call cooldown, so a full sweep of a season's
finished fixtures takes ~1-2 hours. Only the one /v4/fixtures enumeration
call is billable. Most fixtures 404 — US books only board featured games.

For every fixture that has a price trail, keeps each bookmaker/market/
outcome's OPENING and CLOSING pregame prices (closing = last update at or
before the scheduled start; post-start updates are live odds and excluded).

Usage:
    python scripts/backfill_odds.py                 # sweep current season
    python scripts/backfill_odds.py --from 2026-08-20 --to 2026-09-27

Writes/updates data/processed/odds_hist_2026.parquet, skipping fixtures
already present (resumable; safe to re-run to append fresh finals).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oddspapi  # noqa: E402

BOOKS = "draftkings,fanduel,betonline.ag"  # max 3 per call; pinnacle has
                                           # no NCAA W board
OUT = Path("data/processed/odds_hist_2026.parquet")
COOLDOWN = 5.2


def trail_rows(fixture: dict, hist: dict, mktmap: dict, names: dict):
    start = pd.Timestamp(fixture["startTime"])
    rows = []
    for bk, bo in (hist.get("bookmakers") or {}).items():
        for mid, m in (bo.get("markets") or {}).items():
            ref = mktmap.get(str(mid))
            if (not ref or ref.get("playerProp")
                    or ref.get("period") != "result"
                    or ref["marketType"] not in ("moneyline", "spreads",
                                                 "totals")):
                continue
            h = float(ref.get("handicap") or 0.0)
            oname = {str(o["outcomeId"]): o["outcomeName"]
                     for o in ref["outcomes"]}
            for oid, o in (m.get("outcomes") or {}).items():
                trail = (o.get("players") or {}).get("0") or []
                pre = [t for t in trail
                       if pd.Timestamp(t["createdAt"]) <= start
                       and t.get("price")]
                if not pre:
                    continue
                pre.sort(key=lambda t: t["createdAt"])
                name = str(oname.get(str(oid)))
                mtype = ref["marketType"]
                if mtype == "moneyline":
                    mk, side, point = "ml", \
                        "home" if name == "1" else "away", None
                elif mtype == "spreads":
                    mk = "spread"
                    side = "home" if name == "1" else "away"
                    point = h if name == "1" else -h
                else:
                    mk, side, point = "total", name.lower(), h
                    if side not in ("over", "under"):
                        continue
                rows.append({
                    "fixture_id": fixture["fixtureId"],
                    "start_time": fixture["startTime"],
                    "home_name": names.get(str(fixture["participant1Id"])),
                    "away_name": names.get(str(fixture["participant2Id"])),
                    "book": bk, "market": mk, "side": side, "point": point,
                    "open_dec": float(pre[0]["price"]),
                    "close_dec": float(pre[-1]["price"]),
                    "close_at": pre[-1]["createdAt"],
                    "n_moves": len(pre),
                })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", default="2026-08-20")
    ap.add_argument("--to", dest="date_to",
                    default=str(dt.date.today() + dt.timedelta(days=1)))
    args = ap.parse_args()

    key = oddspapi.api_key()
    mktmap = oddspapi._markets_map()
    names = oddspapi._participants()

    r = requests.get(f"{oddspapi.API}/fixtures",
                     params={"apiKey": key,
                             "tournamentId": oddspapi.TOURNAMENT_NCAAW,
                             "from": args.date_from, "to": args.date_to},
                     timeout=60)
    r.raise_for_status()
    fixtures = [f for f in r.json() if f.get("statusId") == 2]  # finished
    print(f"{len(fixtures)} finished fixtures "
          f"{args.date_from}..{args.date_to}")

    done = set()
    old = None
    if OUT.exists():
        old = pd.read_parquet(OUT)
        done = set(old.fixture_id)
        # fixtures swept before but odds-less were recorded as sentinel rows
        print(f"{len(done)} fixtures already swept")

    rows, sentinels, hits = [], [], 0
    todo = [f for f in fixtures if f["fixtureId"] not in done]
    est = len(todo) * COOLDOWN / 60
    print(f"{len(todo)} to sweep (~{est:.0f} min)")
    for i, f in enumerate(todo):
        time.sleep(COOLDOWN)
        try:
            h = requests.get(f"{oddspapi.API}/historical-odds",
                             params={"apiKey": key,
                                     "fixtureId": f["fixtureId"],
                                     "bookmakers": BOOKS}, timeout=60)
        except Exception as e:
            print(f"  {f['fixtureId']}: {e} — retry next run")
            continue
        if h.status_code == 429:
            print("  rate limited, extra wait")
            time.sleep(30)
            continue
        got = []
        if h.status_code == 200:
            got = trail_rows(f, h.json(), mktmap, names)
            if got:
                hits += 1
                rows.extend(got)
        # record the sweep either way so re-runs skip this fixture
        # (odds-less fixtures get one sentinel row with book="")
        if h.status_code in (200, 404) and not got:
            sentinels.append({
                "fixture_id": f["fixtureId"],
                "start_time": f["startTime"],
                "home_name": names.get(str(f["participant1Id"])),
                "away_name": names.get(str(f["participant2Id"])),
                "book": "", "market": "", "side": "", "point": None,
                "open_dec": None, "close_dec": None, "close_at": "",
                "n_moves": 0})
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(todo)} swept, {hits} with odds")
            _save(old, rows, sentinels)
    _save(old, rows, sentinels)
    print(f"done: {hits} fixtures with odds this run -> {OUT}")


def _save(old, rows, sentinels):
    frames = [d for d in (old, pd.DataFrame(rows + sentinels)) if d is not None
              and len(d)]
    if frames:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        pd.concat(frames, ignore_index=True).to_parquet(OUT, index=False)


if __name__ == "__main__":
    main()
