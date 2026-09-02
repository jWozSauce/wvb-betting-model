"""Client for NCAA.com's GraphQL data API (sdataprod.ncaa.com).

NCAA.com serves game data through persisted GraphQL queries. Each query is
addressed by an operation name (``meta`` param) plus a sha256 hash. The hashes
are embedded in page HTML under ``drupalSettings`` (``gqlShas`` on gamecenter
pages, ``shas`` on scoreboard pages) and change when NCAA redeploys the site,
so this client ships with known-good defaults and can re-scrape them on demand.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse

import requests

GQL_HOST = "https://sdataprod.ncaa.com/"
NCAA_HOST = "https://www.ncaa.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Known-good persisted query hashes as of 2026-08-30.
DEFAULT_SHAS = {
    "GetContests_web": "4bcb5e6432fa9da365c0c19af01b1f9015cc7eb5c21e7af2dba308784a166df7",
    "GetGamecenterGameById_web": "26d14df5714c5cd454c9032a1f8ebb1b1dc35173065ab858709b0fa84dd07b5f",
    "NCAA_GetGamecenterPbpGenericById_web": "57f922d56d60d88326b62202b3d88e8cd3cfb6687931bc0b5b3dfab089b84faa",
    "NCAA_GetGamecenterBoxscoreVolleyballById_web": "4320484382257c2a7ac3be318db2dee09a7fb74029448825c285d5dbdda365ae",
    "NCAA_GetGamecenterTeamStatsVolleyballById_web": "9b4d5dcdc81e3df6a8388700f2d54c43a4cf9680ee85eab5b89e4c0e17bedbb2",
    "NCAA_GetGamecenterScoringSummaryById_web": "fcd5729c72b0f72a4f659bf07e7b1da0fdce8f41ad286b0ddfe830adc7a45ca3",
}


class NCAAClient:
    def __init__(self, delay: float = 0.3, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.shas = dict(DEFAULT_SHAS)
        self.delay = delay
        self.timeout = timeout
        self._last_request = 0.0
        self._refreshed = False

    # ------------------------------------------------------------------ core

    def _throttle(self):
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _gql(self, meta: str, variables: dict) -> dict:
        self._throttle()
        params = {
            "meta": meta,
            "extensions": json.dumps(
                {"persistedQuery": {"version": 1, "sha256Hash": self.shas[meta]}},
                separators=(",", ":"),
            ),
            "variables": json.dumps(variables, separators=(",", ":")),
        }
        url = GQL_HOST + "?" + urllib.parse.urlencode(params)
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code == 400 and not self._refreshed:
            # Persisted-query hashes likely rotated with a site deploy.
            self.refresh_shas()
            self._refreshed = True
            return self._gql(meta, variables)
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload and not payload.get("data"):
            raise RuntimeError(f"GraphQL error for {meta}: {payload['errors']}")
        return payload["data"]

    def refresh_shas(self):
        """Re-scrape persisted-query hashes from ncaa.com page HTML."""
        # Gamecenter hashes live on any /game/<id> page; find one via the
        # scoreboard page, which also carries the GetContests hash.
        sb = self.session.get(
            NCAA_HOST + "/scoreboard/volleyball-women/d1", timeout=self.timeout
        )
        sb.raise_for_status()
        for m in re.finditer(r'"shas":({[^}]+})', sb.text):
            self.shas.update(json.loads(m.group(1)))
        game = re.search(r'"/game/(\d+)"|href="/game/(\d+)', sb.text)
        if game:
            gid = game.group(1) or game.group(2)
            gc = self.session.get(f"{NCAA_HOST}/game/{gid}", timeout=self.timeout)
            gc.raise_for_status()
            for m in re.finditer(r'"gqlShas":({[^}]+})', gc.text):
                self.shas.update(json.loads(m.group(1)))

    # ------------------------------------------------------------- endpoints

    def contests(self, date, season_year: int, division: int = 1,
                 sport: str = "WVB") -> list[dict]:
        """All contests for one calendar date. `date` is a datetime.date."""
        data = self._gql(
            "GetContests_web",
            {
                "sportCode": sport,
                "division": division,
                "seasonYear": season_year,
                "contestDate": date.strftime("%m/%d/%Y"),
            },
        )
        return data["contests"] or []

    def game(self, contest_id) -> dict | None:
        """Game details: linescores, venue/location, championship flags."""
        data = self._gql(
            "GetGamecenterGameById_web",
            {"id": str(contest_id), "week": None, "staticTestEnv": None},
        )
        contests = data["contests"]
        return contests[0] if contests else None

    def play_by_play(self, contest_id) -> dict | None:
        data = self._gql(
            "NCAA_GetGamecenterPbpGenericById_web",
            {"contestId": str(contest_id), "staticTestEnv": None},
        )
        return data["playbyplay"]

    def boxscore(self, contest_id) -> dict | None:
        data = self._gql(
            "NCAA_GetGamecenterBoxscoreVolleyballById_web",
            {"contestId": str(contest_id), "staticTestEnv": None},
        )
        return data["boxscore"]
