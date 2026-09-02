"""Download NCAA WVB contests + play-by-play for a season to data/raw/.

Usage:
    python scripts/backfill.py --season 2024                # whole season
    python scripts/backfill.py --season 2026 --limit 10     # smoke test
    python scripts/backfill.py --season 2024 --start 09/01 --end 09/07

Layout (resumable — already-downloaded games are skipped):
    data/raw/<season>/contests/<YYYY-MM-DD>.json   daily schedule+results
    data/raw/<season>/games/<contest_id>.json      {"game": ..., "pbp": ...}
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vbstats.ncaa import NCAAClient

# D1 women's volleyball runs late August through the December championship.
SEASON_WINDOW = ("08/15", "12/31")


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True, help="e.g. 2024")
    ap.add_argument("--start", help="MM/DD (default 08/15)")
    ap.add_argument("--end", help="MM/DD (default 12/31)")
    ap.add_argument("--limit", type=int, help="stop after N games (smoke test)")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--division", type=int, default=1)
    ap.add_argument("--boxscores", action="store_true",
                    help="also fetch player boxscores (adds one request per "
                         "game; backfills into existing game files too)")
    args = ap.parse_args()

    start_md = args.start or SEASON_WINDOW[0]
    end_md = args.end or SEASON_WINDOW[1]
    start = dt.datetime.strptime(f"{start_md}/{args.season}", "%m/%d/%Y").date()
    end = dt.datetime.strptime(f"{end_md}/{args.season}", "%m/%d/%Y").date()
    end = min(end, dt.date.today())

    root = Path(args.out) / str(args.season)
    contests_dir = root / "contests"
    games_dir = root / "games"
    contests_dir.mkdir(parents=True, exist_ok=True)
    games_dir.mkdir(parents=True, exist_ok=True)

    client = NCAAClient()
    n_games = n_skipped = n_errors = 0

    for day in daterange(start, end):
        day_path = contests_dir / f"{day.isoformat()}.json"
        # Use the cached daily file only once every game in it is final —
        # a file fetched while games were pending must be refreshed.
        contests = None
        if day_path.exists():
            cached = json.loads(day_path.read_text())
            if all(c.get("gameState") == "F" for c in cached):
                contests = cached
        if contests is None:
            try:
                contests = client.contests(day, args.season, args.division)
            except Exception as e:
                print(f"{day} contests FAILED: {e}", flush=True)
                n_errors += 1
                continue
            day_path.write_text(json.dumps(contests))

        finals = [c for c in contests if c.get("gameState") == "F"]
        if contests:
            print(f"{day}: {len(contests)} contests, {len(finals)} final", flush=True)

        for c in finals:
            cid = c["contestId"]
            game_path = games_dir / f"{cid}.json"
            if game_path.exists():
                if not args.boxscores:
                    n_skipped += 1
                    continue
                blob = json.loads(game_path.read_text())
                if "boxscore" in blob:
                    n_skipped += 1
                    continue
                try:  # backfill boxscore into an existing game file
                    blob["boxscore"] = client.boxscore(cid)
                    game_path.write_text(json.dumps(blob))
                    n_games += 1
                except Exception as e:
                    print(f"  boxscore {cid} FAILED: {e}", flush=True)
                    n_errors += 1
                continue
            try:
                game = client.game(cid)
                pbp = client.play_by_play(cid) if (game or {}).get("hasPbp") else None
                blob = {"game": game, "pbp": pbp}
                if args.boxscores and (game or {}).get("hasBoxscore"):
                    blob["boxscore"] = client.boxscore(cid)
                game_path.write_text(json.dumps(blob))
                n_games += 1
            except Exception as e:
                print(f"  game {cid} FAILED: {e}", flush=True)
                n_errors += 1
            if args.limit and n_games >= args.limit:
                print(f"limit {args.limit} reached")
                print(f"downloaded={n_games} skipped={n_skipped} errors={n_errors}")
                return

    print(f"done: downloaded={n_games} skipped={n_skipped} errors={n_errors}")


if __name__ == "__main__":
    main()
