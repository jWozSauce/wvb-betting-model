"""Live venue lookup for upcoming games, via the NCAA schedule/game API.

Given (away_seo, home_seo) pairs from a parsed slate, finds the matching
contests on the NCAA schedule for the next few days and returns each game's
venue plus a true-home / neutral classification against the home team's
usual venue (app_data/home_venues.parquet, built by build_elo.py).
"""

from __future__ import annotations

import datetime as dt

from vbstats.ncaa import NCAAClient


def slate_venues(pairs, home_venue_map: dict, days_ahead: int = 2,
                 season: int | None = None, progress=lambda m: None) -> dict:
    """pairs: iterable of (away_seo, home_seo).

    Returns {(away, home): {"venue": str, "site": label}} where site is one
    of: "true home", "AWAY team's gym", "NEUTRAL?", "?" (unknown venue), or
    "not on NCAA sched".
    """
    today = dt.date.today()
    season = season or (today.year if today.month >= 6 else today.year - 1)
    client = NCAAClient(delay=0.25)
    wanted = {frozenset(p) for p in pairs}
    venue_owner = {v: t for t, v in home_venue_map.items()}

    contest_for = {}
    for d in range(days_ahead + 1):
        day = today + dt.timedelta(days=d)
        try:
            contests = client.contests(day, season)
        except Exception as e:
            progress(f"{day}: schedule fetch failed ({e})")
            continue
        for c in contests:
            key = frozenset(t["seoname"] for t in c["teams"])
            if key in wanted and key not in contest_for:
                contest_for[key] = c["contestId"]

    out = {}
    for away, home in pairs:
        key = frozenset((away, home))
        cid = contest_for.get(key)
        if cid is None:
            out[(away, home)] = {"venue": "", "site": "not on NCAA sched"}
            continue
        try:
            g = client.game(cid)
            loc = (g or {}).get("location") or {}
        except Exception:
            loc = {}
        venue = loc.get("venue")
        if not venue:
            out[(away, home)] = {"venue": "", "site": "?"}
            continue
        label = ", ".join(x for x in (venue, loc.get("city"),
                                      loc.get("stateUsps")) if x)
        owner = venue_owner.get(venue)  # whose usual home gym is this?
        if venue == home_venue_map.get(home):
            site = "true home"
        elif venue == home_venue_map.get(away):
            site = "AWAY team's gym"
        elif home in home_venue_map:
            site = f"neutral ({owner}'s gym)" if owner else "neutral (3rd site)"
        else:
            site = "?"
        out[(away, home)] = {"venue": label, "site": site}
    return out
