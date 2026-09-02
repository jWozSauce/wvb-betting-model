"""Run serve/receive Elo across one or more seasons.

Usage:
    python scripts/build_elo.py --seasons 2021 2022 2023 2024 2025
    python scripts/build_elo.py --seasons 2025 --k 1.5 --carryover 0.75

Reads  data/processed/{matches,points}_<season>.parquet
Writes data/processed/elo_matches.parquet   one row per match, pre-game elos
       data/processed/elo_final.parquet     final ratings after last season
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vbstats.elo import TeamRatings, run_elo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, nargs="+", required=True)
    ap.add_argument("--k", type=float, default=1.0, help="per-point K factor")
    ap.add_argument("--home-adv", type=float, default=0.0,
                    help="Elo bonus for home team on non-neutral courts")
    ap.add_argument("--conf-weight", type=float, default=0.1,
                    help="share of cross-conference updates moving the "
                         "conference anchor (0 = plain single-tier elo)")
    ap.add_argument("--carryover", type=float, default=0.8,
                    help="between-season regression toward baseline (1=keep)")
    ap.add_argument("--dir", default="data/processed")
    args = ap.parse_args()

    d = Path(args.dir)
    ratings = TeamRatings()
    tables = []
    for i, season in enumerate(sorted(args.seasons)):
        matches = pd.read_parquet(d / f"matches_{season}.parquet")
        points = pd.read_parquet(d / f"points_{season}.parquet")
        if i > 0:
            ratings.regress_to_mean(args.carryover)
        table, ratings = run_elo(
            matches, points, k=args.k, home_adv=args.home_adv,
            conf_weight=args.conf_weight, ratings=ratings,
        )
        tables.append(table)
        print(f"{season}: {len(table)} matches processed")

    out = pd.concat(tables, ignore_index=True)
    out.to_parquet(d / "elo_matches.parquet", index=False)

    final = pd.DataFrame(
        {
            "team_id": list(ratings.serve),
            "serve_elo": [ratings.serve[t] for t in ratings.serve],
            "receive_elo": [ratings.receive.get(t) for t in ratings.serve],
            "games": [ratings.games.get(t, 0) for t in ratings.serve],
        }
    ).sort_values("serve_elo", ascending=False)
    final.to_parquet(d / "elo_final.parquet", index=False)

    print(f"wrote {len(out)} rows -> {d / 'elo_matches.parquet'}")
    print(f"final ratings for {len(final)} teams -> {d / 'elo_final.parquet'}")

    # ---- app export: current ratings for teams active in the last 2 seasons
    # (latest-season info wins, so conference realignment is reflected)
    last = out[out.season >= out.season.max() - 1].sort_values("season")
    names, confs = {}, {}
    for side in ("home", "away"):
        for r in last[[f"{side}_id", f"{side}_seo", f"{side}_conf"]].itertuples(index=False):
            tid, seo, conf = r
            names[tid] = seo
            if conf:
                confs[tid] = conf
    current = final[final.team_id.isin(names)].copy()
    current["team"] = current.team_id.map(names)
    current["conf"] = current.team_id.map(confs)
    current["conf_elo"] = current.conf.map(ratings.conf).fillna(0.0)
    current = current.sort_values("team")
    app_dir = Path("app_data")
    app_dir.mkdir(exist_ok=True)
    current.to_parquet(app_dir / "elo_current.parquet", index=False)
    print(f"current ratings for {len(current)} active teams -> "
          f"{app_dir / 'elo_current.parquet'}")

    # Current-season results for the app's Results tab.
    cur_season = int(out.season.max())
    season_rows = out[out.season == cur_season]
    season_rows.to_parquet(app_dir / "results_current.parquet", index=False)
    print(f"{len(season_rows)} current-season results -> "
          f"{app_dir / 'results_current.parquet'}")


if __name__ == "__main__":
    main()
