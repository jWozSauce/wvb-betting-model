"""Build RAPM ingredient tables from raw games (pbp + boxscores).

    python scripts/build_rapm_tables.py --season 2024

Writes to data/processed/:
  set_starters_<season>.parquet   one row per (contest, set, team, player)
                                  from pbp starter lines
  player_box_<season>.parquet     one row per (contest, team, player) with
                                  the full volleyball boxscore stat line
                                  (requires backfill.py --boxscores)
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

BOX_FIELDS = ["position", "number", "gamesPlayed", "points", "kills",
              "attackErrors", "attackAttempts", "assists", "setErrors",
              "setAttempts", "serviceAces", "serviceErrors", "serveAttempts",
              "digs", "receptionAttempts", "receptionErrors", "blockSolos",
              "blockAssists", "blockingErrors", "ballHandlingErrors",
              "starter", "participated"]


def clean_name(n: str) -> str:
    return re.sub(r"\s+", " ", n).strip(" .;,")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--raw", default="data/raw")
    args = ap.parse_args()

    games_dir = Path(args.raw) / str(args.season) / "games"
    starter_rows, box_rows = [], []
    n_games = n_with_box = 0

    for path in sorted(games_dir.glob("*.json")):
        blob = json.loads(path.read_text())
        game, pbp = blob.get("game"), blob.get("pbp")
        if not game:
            continue
        teams = {t["isHome"]: t for t in game["teams"]}
        if max(int(teams.get(True, {}).get("score") or 0),
               int(teams.get(False, {}).get("score") or 0)) != 3:
            continue  # regulation matches only
        cid = int(game["id"])
        epoch = int(game.get("startTimeEpoch") or 0)
        n_games += 1

        # roster per team from the boxscore: canonical names + normalized
        # variants ("firstlast" and "lastfirst") for format-proof matching
        # of starter lines (feeds vary: "First Last; ...", "Last, First, ...",
        # duplicated lines — substring roster matching sidesteps all of it)
        box = blob.get("boxscore")
        roster: dict[str, list] = {}
        if box and box.get("teamBoxscore"):
            id2seo_r = {int(t["teamId"]): t["seoname"]
                        for t in box.get("teams", [])}
            for tb in box["teamBoxscore"]:
                seo = id2seo_r.get(int(tb["teamId"]))
                for p in tb.get("playerStats") or []:
                    fn = re.sub(r"[^a-z]", "", str(p.get("firstName", "")).lower())
                    ln = re.sub(r"[^a-z]", "", str(p.get("lastName", "")).lower())
                    if seo and (fn or ln):
                        roster.setdefault(seo, []).append(
                            (clean_name(f"{p.get('firstName','')} "
                                        f"{p.get('lastName','')}"),
                             fn + ln, ln + fn))

        if pbp and pbp.get("periods"):
            id2seo = {int(t["teamId"]): t["seoname"] for t in pbp["teams"]}
            for per in pbp["periods"]:
                seen: set = set()
                for blk in per["playbyplayStats"]:
                    seo = id2seo.get(int(blk["teamId"]))
                    for play in blk["plays"]:
                        m = STARTERS_RE.search(play.get("playText") or "")
                        if not (m and seo and seo in roster):
                            continue
                        line = re.sub(r"[^a-z]", "", m.group(1).lower())
                        for canon, fl, lf in roster[seo]:
                            if (fl and fl in line) or (lf and lf in line):
                                key = (seo, per["periodNumber"], canon)
                                if key not in seen:
                                    seen.add(key)
                                    starter_rows.append({
                                        "contest_id": cid,
                                        "start_epoch": epoch,
                                        "set": per["periodNumber"],
                                        "team": seo,
                                        "player": canon,
                                    })

        if box and box.get("teamBoxscore"):
            n_with_box += 1
            id2seo_b = {int(t["teamId"]): t["seoname"]
                        for t in box.get("teams", [])}
            for tb in box["teamBoxscore"]:
                seo = id2seo_b.get(int(tb["teamId"]))
                for p in tb.get("playerStats") or []:
                    row = {
                        "contest_id": cid,
                        "start_epoch": epoch,
                        "team": seo,
                        "player": clean_name(f"{p.get('firstName','')} "
                                             f"{p.get('lastName','')}"),
                    }
                    for f in BOX_FIELDS:
                        row[f] = p.get(f)
                    box_rows.append(row)

    out = Path("data/processed")
    starters = pd.DataFrame(starter_rows).drop_duplicates()
    starters.to_parquet(out / f"set_starters_{args.season}.parquet",
                        index=False)
    boxes = pd.DataFrame(box_rows)
    boxes.to_parquet(out / f"player_box_{args.season}.parquet", index=False)
    print(f"{args.season}: {n_games} regulation games | "
          f"{len(starters)} starter rows | boxscores in {n_with_box} games "
          f"({len(boxes)} player-match stat lines)")


if __name__ == "__main__":
    main()
