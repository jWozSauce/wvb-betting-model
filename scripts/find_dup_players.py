"""Flag potential duplicate players for MANUAL review — changes nothing.

The starter feeds are inconsistent about capitalization ("Emma McDermott" /
"Emma Mcdermott"), so the RAPM tables can carry one athlete as two players,
splitting their sets and diluting their coefficients. This scans
app_data/rapm.parquet for same-team candidate pairs:

  near-certain : names identical once case/punctuation are ignored
  possible     : very similar names (ratio >= 0.90) — review carefully,
                 twins/siblings on one roster are common in volleyball

Usage: python scripts/find_dup_players.py
Writes data/processed/dup_players_review.csv (report only; no data edits).
"""

from __future__ import annotations

import difflib
import re
import sys
from itertools import combinations
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", str(name).lower())


def main():
    df = pd.read_parquet("app_data/rapm.parquet")
    rows = []
    for team, grp in df.groupby("team"):
        players = grp.to_dict("records")
        for a, b in combinations(players, 2):
            na, nb = norm(a["player"]), norm(b["player"])
            if not na or not nb:
                continue
            if na == nb:
                tier = "near-certain"
                score = 1.0
            else:
                score = difflib.SequenceMatcher(None, na, nb).ratio()
                if score < 0.90:
                    continue
                tier = "possible"
            rows.append({
                "tier": tier, "team": team,
                "player_a": a["player"], "player_b": b["player"],
                "pos_a": a.get("position"), "pos_b": b.get("position"),
                "sets_a": a.get("sets_started_cur"),
                "sets_b": b.get("sets_started_cur"),
                "sets_merged": (a.get("sets_started_cur") or 0)
                + (b.get("sets_started_cur") or 0),
                "similarity": round(score, 3),
            })
    rep = pd.DataFrame(rows).sort_values(
        ["tier", "team", "player_a"]).reset_index(drop=True)
    out = Path("data/processed/dup_players_review.csv")
    rep.to_csv(out, index=False)

    for tier in ("near-certain", "possible"):
        sub = rep[rep.tier == tier]
        print(f"\n=== {tier}: {len(sub)} pairs")
        if len(sub):
            print(sub.drop(columns="tier").to_string(index=False))
    print(f"\nreport -> {out}  (review only — nothing was merged)")


if __name__ == "__main__":
    main()
