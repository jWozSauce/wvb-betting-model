"""Offline boundary checks for the schedule source. Run with unittest discovery."""
import unittest
from unittest.mock import patch
import datetime as dt

import pandas as pd

from schedule_pricing import partition_schedule, classify_venue, fetch_slate, VENUE_MODES


def contest(cid, home="h", away="a"):
    return {"contestId": cid, "hasStartTime": True, "startTimeEpoch": 100,
            "teams": [{"seoname": home, "isHome": True},
                      {"seoname": away, "isHome": False}]}


class ScheduleTests(unittest.TestCase):
    def test_cross_division_dedup_and_reconciled_exclusions(self):
        c = contest(1)
        bad = contest(3)
        bad["teams"][1]["isHome"] = True
        result = partition_schedule({1: {"contests": [c, contest(2, away="unrated"), bad]},
                                     2: {"contests": [c]}, 3: {"contests": []}}, {"h", "a"})
        self.assertEqual((result["fetched"], result["raw_count"], result["duplicates"]), (3, 4, 1))
        self.assertEqual(len(result["priced"]), 1)
        self.assertEqual(len(result["unpriced"]), 2)
        self.assertIn("unrated team", result["unpriced"][0]["reason"])
        self.assertIn("home label", result["unpriced"][1]["reason"])

    def test_missing_id_and_conflicting_duplicate_fail_closed(self):
        with self.assertRaises(ValueError):
            partition_schedule({1: {"contests": [contest(None)]}}, {"h", "a"})
        with self.assertRaises(ValueError):
            partition_schedule({1: {"contests": [contest(1), contest(1, away="b")]}}, {"h", "a"})

    def test_home_away_host_third_party_and_unknown(self):
        row = {"home": "h", "away": "a"}
        hv, owners = {"h": "H", "a": "A"}, {"B": "b"}
        for venue, site, mode, home in [
            ("H", "true home", VENUE_MODES[0], "h"),
            ("A", "AWAY team's gym — host shown as home", VENUE_MODES[0], "a"),
            ("B", "neutral (b's gym)", VENUE_MODES[2], "h"),
            ("C", "neutral (3rd site)", VENUE_MODES[2], "h"),
            (None, "venue ?", VENUE_MODES[0], "h")]:
            actual = classify_venue(row, {"venue": venue}, hv, owners)
            self.assertEqual((actual["site"], actual["venue_mode"], actual["home"]), (site, mode, home))
            self.assertEqual(actual["ncaa_home"], "h")
        self.assertEqual(row, {"home": "h", "away": "a"})

    def test_only_rated_games_get_venue_lookups(self):
        with patch('schedule_pricing.schedule_response', return_value={"contests": [contest(1), contest(2, away="x")]}), \
             patch('schedule_pricing.game_response', return_value={"game": {"location": {}}}) as lookup:
            result = fetch_slate(dt.date(2026,10,2), pd.DataFrame({"team": ["a","h"]}),
                                pd.DataFrame({"team": ["h"], "home_venue": ["H"]}))
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(len(result["priced"]) + len(result["unpriced"]), result["fetched"])

    def test_failed_venue_request_does_not_become_unknown(self):
        with patch('schedule_pricing.schedule_response', return_value={"contests": [contest(1)]}), \
             patch('schedule_pricing.game_response', side_effect=RuntimeError("failed fetch")):
            with self.assertRaisesRegex(RuntimeError, "failed fetch"):
                fetch_slate(dt.date(2026,10,2), pd.DataFrame({"team": ["a","h"]}),
                            pd.DataFrame({"team": ["h"], "home_venue": ["H"]}))


if __name__ == '__main__':
    unittest.main()
