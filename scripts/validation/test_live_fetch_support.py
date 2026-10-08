"""Q15 support capture: same Live API requests, downloadable raw per-book JSON."""
import copy
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import oddspapi
from evidence_runs import new_run
from validate_t2_ui import check, element, guards, new_app


ref = {
    "231": {
        "marketType": "moneyline",
        "period": "result",
        "outcomes": [
            {"outcomeId": 1, "outcomeName": "1"},
            {"outcomeId": 2, "outcomeName": "2"},
        ],
    }
}


def markets(home, away):
    return {
        "231": {
            "outcomes": {
                str(i): {"players": {"0": {"active": True, "priceAmerican": price}}}
                for i, price in enumerate([home, away], 1)
            }
        }
    }


fixture = {
    "fixtureId": "123",
    "statusId": 0,
    "startTime": "2026-10-07T23:00:00Z",
    "participant1Id": 1,
    "participant2Id": 2,
    "bookmakerOdds": {
        "draftkings": {"markets": markets(-120, 100)},
        "hardrockbet": {"markets": markets(-115, -105)},
    },
}


class Response:
    def __init__(self, book, status=200):
        self.status_code = status
        self.book = book

    def json(self):
        if self.status_code == 404:
            return {"code": "FIXTURE_NOT_FOUND"}
        current = copy.deepcopy(fixture)
        current["bookmakerOdds"] = {self.book: current["bookmakerOdds"][self.book]}
        return [current]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")


with ExitStack() as stack:
    guards(stack)
    stack.enter_context(patch.dict(os.environ, {
        "WVB_ENABLE_BOOK_SELECTION": "1",
        "WVB_ENABLE_LIVE_TEAM_MAP": "0",
    }))
    stack.enter_context(patch.object(oddspapi, "_markets_map", return_value=ref))
    stack.enter_context(patch.object(oddspapi, "_participants",
                                     return_value={"1": "Nebraska", "2": "Kansas"}))
    stack.enter_context(patch.object(oddspapi.time, "sleep"))
    request = stack.enter_context(patch.object(
        oddspapi.safe_http, "get",
        side_effect=lambda url, **kw: Response(kw["params"]["bookmaker"])))
    games, nreq, support = oddspapi.fetch_board(
        books=("draftkings", "hardrockbet"), key="offline", include_diagnostics=True)
    assert nreq == 2 and request.call_count == 2
    assert len(games) == 1 and support["decoded_fixture_ids"] == ["123"]
    assert [row["book"] for row in support["per_book"]] == ["draftkings", "hardrockbet"]
    assert all("apiKey" not in json.dumps(row) for row in support["per_book"])
    assert all(row["fixture_count"] == 1 and isinstance(row["payload"], list)
               for row in support["per_book"])

    fetch = stack.enter_context(patch("oddspapi.fetch_board",
                                      return_value=(games, 2, support)))
    stack.enter_context(patch("oddspapi.account", return_value={
        "requests_used": 26,
        "request_limit": 250,
    }))
    stack.enter_context(patch("vbstats.venues.slate_venues", return_value={}))
    app = new_app((ROOT / "streamlit_app.py").read_text())
    element(app.button, "Fetch odds & evaluate").click()
    check(app.run())
    assert fetch.call_count == 1
    assert fetch.call_args.kwargs["include_diagnostics"] is True
    assert app.session_state.live_fetch_support_json == support
    assert any(button.label == "Download OddsPapi support JSON"
               for button in app.download_button)

out = new_run(ROOT / "evidence" / "q15-20261007")
(out / "checks.json").write_text(json.dumps({
    "raw_per_book_payloads_captured": True,
    "credential_free": True,
    "same_requests_only": request.call_count,
    "ui_download_available": True,
    "real_paid_calls": 0,
    "real_sheet_writes": 0,
}, indent=2))
print("PASS Q15 live support JSON diagnostic")
print(out)
