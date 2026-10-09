"""T18 grading guards: do not settle known future starts or same-date rematches."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import bet_log
from evidence_runs import new_run


class Sheet:
    def __init__(self, rows):
        self.rows = rows
        self.writes = []

    def get_all_records(self):
        return [dict(row) for row in self.rows]

    def batch_update(self, data, **kwargs):
        self.writes.append({"data": data, "kwargs": kwargs})
        for item in data:
            start = item["range"].split(":")[0]
            row = int("".join(ch for ch in start if ch.isdigit()))
            values = item["values"][0]
            self.rows[row - 2]["status"] = values[0]
            self.rows[row - 2]["profit"] = values[1]
            self.rows[row - 2]["graded_at"] = values[2]


def bet_row(**overrides):
    row = dict(
        logged_at="2026-10-09 8:40",
        game_date="2026-10-09",
        matchup="ga-southern @ appalachian-st",
        home_team="appalachian-st",
        away_team="ga-southern",
        bet="appalachian-st +1.5 sets",
        market="spread",
        side="home",
        point=1.5,
        odds=-115,
        stake=29.83,
        status="pending",
        profit="",
        graded_at="",
        game_time="6:00 PM",
    )
    row.update(overrides)
    return row


def results(*rows):
    return pd.DataFrame(rows)


old_result = dict(
    contest_id=1,
    date="2026-10-08",
    home_seo="appalachian-st",
    away_seo="ga-southern",
    home_sets=3,
    away_sets=1,
)
new_result = dict(
    contest_id=2,
    date="2026-10-09",
    home_seo="appalachian-st",
    away_seo="ga-southern",
    home_sets=0,
    away_sets=3,
)


checks = {}

sheet = Sheet([bet_row()])
with patch.object(bet_log, "_ws", return_value=sheet):
    graded, _ = bet_log.grade_pending(
        results(old_result),
        now=pd.Timestamp("2026-10-09 09:11", tz="America/New_York"))
assert graded == 0 and sheet.rows[0]["status"] == "pending" and not sheet.writes
checks["future_start_with_only_prior_result_stays_pending"] = True

sheet = Sheet([bet_row()])
with patch.object(bet_log, "_ws", return_value=sheet):
    graded, _ = bet_log.grade_pending(
        results(old_result, new_result),
        now=pd.Timestamp("2026-10-09 23:00", tz="America/New_York"))
assert graded == 1 and sheet.rows[0]["status"] == "lost"
checks["exact_date_final_grades_against_exact_date"] = True

sheet = Sheet([bet_row(game_date="2026-10-07", game_time="")])
with patch.object(bet_log, "_ws", return_value=sheet):
    graded, _ = bet_log.grade_pending(
        results(old_result),
        now=pd.Timestamp("2026-10-09 23:00", tz="America/New_York"))
assert graded == 1 and sheet.rows[0]["status"] == "won"
checks["legitimate_date_slop_without_same_day_fixture_still_grades"] = True

sheet = Sheet([bet_row(game_time="")])
with patch.object(bet_log, "_ws", return_value=sheet):
    graded, _ = bet_log.grade_pending(
        results(old_result),
        now=pd.Timestamp("2026-10-09 23:00", tz="America/New_York"),
        schedule_pairs={("2026-10-09", "appalachian-st", "ga-southern")})
assert graded == 0 and sheet.rows[0]["status"] == "pending" and not sheet.writes
checks["same_day_schedule_fixture_blocks_neighbor_result"] = True

out = new_run(ROOT / "evidence" / "t18-20261009")
(out / "grading-guards.json").write_text(json.dumps({
    **checks,
    "real_sheet_writes": 0,
}, indent=2))
print("PASS T18 grading guards")
print(out)
