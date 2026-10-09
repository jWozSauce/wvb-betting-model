"""Read-only T18 sweep for settled rows that may have used an ineligible result."""
import argparse
import json
import os
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import app_config
import bet_log
from evidence_runs import new_run


def parse_et(value):
    if value in (None, ""):
        return None
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        return ts.tz_localize("America/New_York")
    return ts.tz_convert("America/New_York")


def row_grade(row, result, flipped):
    if result is None:
        return None
    try:
        hs, aw = ((int(result.away_sets), int(result.home_sets)) if flipped
                  else (int(result.home_sets), int(result.away_sets)))
        won, push = bet_log._settle(
            str(row["market"]), str(row["side"]).lower(), row["point"], hs, aw)
        odds = float(row["odds"])
        stake = float(row["stake"] or 0)
    except (KeyError, ValueError, TypeError):
        return None
    profit = 0.0 if push else (
        stake * (odds / 100 if odds > 0 else 100 / -odds) if won else -stake)
    return {
        "status": "push" if push else ("won" if won else "lost"),
        "profit": round(profit, 2),
        "contest_id": int(result.contest_id) if "contest_id" in result else None,
        "result_date": str(result.date),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id-file", required=True)
    ap.add_argument("--out", default=str(ROOT / "evidence" / "t18-20261009"))
    args = ap.parse_args()
    sid_path = Path(args.sheet_id_file)
    app_config._sheet_id = lambda: sid_path.read_text().strip()
    bet_log.SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    results = pd.read_parquet(ROOT / "app_data" / "results_current.parquet")
    results["date"] = (pd.to_datetime(results.start_epoch, unit="s", utc=True)
                       .dt.tz_convert("America/New_York").dt.date)
    evidence = new_run(args.out)
    private = []
    counts = {}
    raw_schedule_available = (ROOT / "data" / "raw").exists()

    ss = bet_log._client().open_by_key(app_config._sheet_id())
    for worksheet in (bet_log.WORKSHEET, bet_log.PAPER_WORKSHEET):
        rows = ss.worksheet(worksheet).get_all_records()
        counts[worksheet] = {
            "rows": len(rows),
            "settled_rows": 0,
            "flags": 0,
            "before_start_flags": 0,
            "date_slop_same_day_fixture_flags": 0,
            "unusable": 0,
        }
        for sheet_row, row in enumerate(rows, 2):
            status = str(row.get("status", "")).lower()
            if status not in {"won", "lost", "push"}:
                continue
            counts[worksheet]["settled_rows"] += 1
            reasons = []
            start = bet_log._game_start_et(row.get("game_date"), row.get("game_time"))
            graded_at = parse_et(row.get("graded_at"))
            if start is not None and graded_at is not None and graded_at < start:
                reasons.append("graded_before_logged_start")
                counts[worksheet]["before_start_flags"] += 1
            result, flipped = bet_log._find_result_safe(
                results, row.get("home_team"), row.get("away_team"), str(row.get("game_date")))
            grade = row_grade(row, result, flipped)
            if grade is None:
                counts[worksheet]["unusable"] += 1
            else:
                try:
                    result_day = pd.Timestamp(grade["result_date"]).normalize()
                    bet_day = pd.Timestamp(row.get("game_date")).normalize()
                except (ValueError, TypeError):
                    result_day = bet_day = None
                if result_day is not None and result_day != bet_day:
                    if bet_log._same_day_fixture_exists(
                            results, row.get("home_team"), row.get("away_team"),
                            row.get("game_date")):
                        reasons.append("neighbor_result_but_same_day_fixture_exists")
                        counts[worksheet]["date_slop_same_day_fixture_flags"] += 1
            if reasons:
                counts[worksheet]["flags"] += 1
                private.append({
                    "worksheet": worksheet,
                    "sheet_row": sheet_row,
                    "logged_at": row.get("logged_at"),
                    "game_date": row.get("game_date"),
                    "game_time": row.get("game_time"),
                    "matchup": row.get("matchup"),
                    "bet": row.get("bet"),
                    "status": row.get("status"),
                    "profit": row.get("profit"),
                    "graded_at": row.get("graded_at"),
                    "inferred_grade": grade,
                    "reasons": reasons,
                })

    private_path = Path("/tmp") / "wvb-t18-sweep-private-rows.json"
    private_path.write_text(json.dumps(private, indent=2, default=str))
    summary = {
        "worksheets": counts,
        "flagged_rows": len(private),
        "private_row_report": str(private_path),
        "raw_schedule_cache_available": raw_schedule_available,
        "writes": 0,
    }
    (evidence / "sweep-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
