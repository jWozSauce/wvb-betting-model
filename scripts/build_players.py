"""Build player participation / availability from raw pbp starter lines.

    python scripts/build_players.py --season 2026

Writes app_data/availability.parquet: one row per (team, player) with start
counts and whether they appeared in the team's most recent match. The app
uses it to flag missing core players ("⚕ key starter absent last match").
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STARTERS_RE = re.compile(r"starters:\s*(.+)$", re.I)


def clean_name(n: str) -> str:
    return re.sub(r"\s+", " ", n).strip(" .;,")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--raw", default="data/raw")
    args = ap.parse_args()

    games_dir = Path(args.raw) / str(args.season) / "games"
    # per team: {player: set of contest_ids started}, matches played, last match
    starts: dict[str, dict[str, set]] = {}
    team_matches: dict[str, set] = {}
    match_epoch: dict[int, int] = {}
    match_text: dict[tuple[str, int], str] = {}  # (team, contest) -> full text

    for path in sorted(games_dir.glob("*.json")):
        blob = json.loads(path.read_text())
        game, pbp = blob.get("game"), blob.get("pbp")
        if not game or not pbp or not pbp.get("periods"):
            continue
        # only regulation matches (mirror build_points)
        teams = {t["isHome"]: t for t in game["teams"]}
        sets_won = [int(teams.get(True, {}).get("score") or 0),
                    int(teams.get(False, {}).get("score") or 0)]
        if max(sets_won) != 3:
            continue
        cid = int(game["id"])
        match_epoch[cid] = int(game.get("startTimeEpoch") or 0)
        id2seo = {int(t["teamId"]): t["seoname"] for t in pbp["teams"]}
        texts: dict[str, list] = {seo: [] for seo in id2seo.values()}
        all_text = []
        for per in pbp["periods"]:
            for blk in per["playbyplayStats"]:
                seo = id2seo.get(int(blk["teamId"]))
                for play in blk["plays"]:
                    t = (play.get("playText") or "").strip()
                    if not t:
                        continue
                    all_text.append(t)
                    m = STARTERS_RE.search(t)
                    if m and seo:
                        for name in re.split(r"[;,]", m.group(1)):
                            name = clean_name(name)
                            if len(name) >= 4:
                                starts.setdefault(seo, {}).setdefault(
                                    name, []).append(
                                    (cid, per["periodNumber"]))
        for seo in id2seo.values():
            team_matches.setdefault(seo, set()).add(cid)
            match_text[(seo, cid)] = "\n".join(all_text)

    rows = []
    for seo, players in starts.items():
        cids = team_matches.get(seo, set())
        if not cids:
            continue
        last_cid = max(cids, key=lambda c: match_epoch.get(c, 0))
        last_txt = match_text.get((seo, last_cid), "")
        for player, started_sets in players.items():
            started_matches = {c for c, _ in started_sets}
            rows.append({
                "team": seo,
                "player": player,
                "sets_started": len(set(started_sets)),
                "matches_started": len(started_matches),
                "team_matches": len(cids),
                "started_last": last_cid in started_matches,
                "appeared_last": player in last_txt,
                "last_match_epoch": match_epoch.get(last_cid, 0),
            })
    df = pd.DataFrame(rows)
    out = Path("app_data") / "availability.parquet"
    df.to_parquet(out, index=False)
    core = df[(df.team_matches >= 3)
              & (df.matches_started / df.team_matches >= 0.5)]
    missing = core[~core.appeared_last]
    print(f"{len(df)} player rows for {df.team.nunique()} teams -> {out}")
    print(f"core players: {len(core)} | absent from last match: {len(missing)}")


if __name__ == "__main__":
    main()
