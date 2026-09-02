"""Build point-level and match-level tables from raw game JSON.

Usage:
    python scripts/build_points.py --season 2024

Reads  data/raw/<season>/games/*.json
Writes data/processed/points_<season>.parquet   one row per rally
       data/processed/matches_<season>.parquet  one row per match (with venue)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vbstats.parse import parse_match


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()

    games_dir = Path(args.raw) / str(args.season) / "games"
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Team -> conference for this season, from the daily schedule files.
    conf_votes: dict[str, dict] = {}
    contests_dir = Path(args.raw) / str(args.season) / "contests"
    for path in contests_dir.glob("*.json"):
        for c in json.loads(path.read_text()):
            for t in c.get("teams", []):
                seo, conf = t.get("seoname"), t.get("conferenceSeo")
                if seo and conf:
                    votes = conf_votes.setdefault(seo, {})
                    votes[conf] = votes.get(conf, 0) + 1
    team_conf = {seo: max(v, key=v.get) for seo, v in conf_votes.items()}

    point_rows, match_rows = [], []
    n_no_pbp = 0
    recon_sets_ok = recon_sets_bad = 0

    for path in sorted(games_dir.glob("*.json")):
        blob = json.loads(path.read_text())
        game, pbp = blob.get("game"), blob.get("pbp")
        if not game:
            continue
        loc = game.get("location") or {}
        teams = {t["isHome"]: t for t in game["teams"]}
        home, away = teams.get(True, {}), teams.get(False, {})
        match = {
            "contest_id": int(game["id"]),
            "season": game.get("seasonYear"),
            "start_epoch": game.get("startTimeEpoch"),
            "home_id": int(home.get("teamId", 0)),
            "away_id": int(away.get("teamId", 0)),
            "home_seo": home.get("seoname"),
            "away_seo": away.get("seoname"),
            "home_conf": team_conf.get(home.get("seoname")),
            "away_conf": team_conf.get(away.get("seoname")),
            "home_sets": int(home.get("score") or 0),
            "away_sets": int(away.get("score") or 0),
            "winner_id": game.get("winner"),
            "is_championship": game.get("isChampionship"),
            "is_conf_tournament": game.get("isConferenceTournament"),
            "venue": loc.get("venue"),
            "venue_city": loc.get("city"),
            "venue_state": loc.get("stateUsps"),
            "has_pbp": bool(pbp and pbp.get("periods")),
        }
        match_rows.append(match)

        if not match["has_pbp"]:
            n_no_pbp += 1
            continue
        parsed = parse_match(pbp)
        for pt in parsed["points"]:
            pt["contest_id"] = parsed["contest_id"]
            point_rows.append(pt)

        # Validate reconstructed scores against the official linescores.
        recon = [p for p in parsed["points"] if p.get("score_reconstructed")]
        if recon and game.get("linescores"):
            finals = {}
            for pt in recon:
                finals[pt["set"]] = (pt["home_score"], pt["away_score"])
            for ls in game["linescores"]:
                if not (str(ls["home"]).isdigit() and str(ls["visit"]).isdigit()):
                    continue
                official = (int(ls["home"]), int(ls["visit"]))
                got = finals.get(int(ls["period"]))
                if got is None:
                    continue
                if got == official:
                    recon_sets_ok += 1
                else:
                    recon_sets_bad += 1

    matches = pd.DataFrame(match_rows)
    points = pd.DataFrame(point_rows)

    # Neutral-site flag: a game is neutral when its venue differs from the
    # home team's modal venue that season (or when it's a championship game).
    if not matches.empty:
        with_venue = matches.dropna(subset=["venue"])
        modal_venue = (
            with_venue.groupby(["home_id", "venue"]).size().rename("n").reset_index()
            .sort_values("n", ascending=False)
            .drop_duplicates("home_id")
            .set_index("home_id")["venue"]
        )
        matches["home_modal_venue"] = matches["home_id"].map(modal_venue)
        matches["is_neutral"] = (
            matches["is_championship"].fillna(False)
            | (
                matches["venue"].notna()
                & matches["home_modal_venue"].notna()
                & (matches["venue"] != matches["home_modal_venue"])
            )
        )

    m_path = out_dir / f"matches_{args.season}.parquet"
    p_path = out_dir / f"points_{args.season}.parquet"
    matches.to_parquet(m_path, index=False)
    points.to_parquet(p_path, index=False)

    if recon_sets_ok or recon_sets_bad:
        total = recon_sets_ok + recon_sets_bad
        print(f"reconstructed sets matching official linescores: "
              f"{recon_sets_ok}/{total} ({recon_sets_ok/total:.1%})")
    print(f"matches: {len(matches)} ({n_no_pbp} without pbp) -> {m_path}")
    print(f"points:  {len(points)} -> {p_path}")
    if not points.empty:
        known = points["server_id"].notna().mean()
        conflicts = points["serve_conflict"].mean()
        print(f"server resolved: {known:.1%} of points | anchor conflicts: {conflicts:.2%}")


if __name__ == "__main__":
    main()
