"""Parse NCAA play-by-play JSON into a point-level table.

The feed groups plays into blocks keyed by ``teamId`` — the team credited with
the point. Scored rallies are rows where home/visitor score advances; lineup,
substitution, timeout, and challenge lines carry no score.

Serving team reconstruction (rally scoring): the winner of a point serves the
next one, so within a set every server is determined by the set's FIRST
server. That first server is resolved from:

- the first point being a ``Service ace`` (winner served) or ``Service
  error`` (loser served), else
- serve-first alternation between sets 1-4 when a neighboring set resolved
  (set 5 uses a fresh coin toss, so it only resolves from itself).

Aces / service errors on later points also imply who served; those are used as
consistency checks (``serve_conflict``) rather than trusted blindly.
"""

from __future__ import annotations

import re

ACE_RE = re.compile(r"^service ace", re.I)
SERVICE_ERROR_RE = re.compile(r"^service error", re.I)

# Some feeds (e.g. Big Ten 2023) include play text but no running score. A
# rally-terminal play awards the point to its block's teamId; everything else
# (starters, subs, timeouts, challenges) is bookkeeping.
TERMINAL_RE = re.compile(
    r"^(kill|attack error|service error|service ace|ball handling error"
    r"|bad set|block error)", re.I
)
BOOKKEEPING_RE = re.compile(
    r"(starters:|subs:|sub:|timeout|challenge|end of|reviewed|replay"
    r"|match delay|libero)", re.I
)


def parse_match(pbp: dict) -> dict:
    """Turn one playbyplay payload into match metadata + point rows."""
    home_id = next(int(t["teamId"]) for t in pbp["teams"] if t["isHome"])
    away_id = next(int(t["teamId"]) for t in pbp["teams"] if not t["isHome"])

    def other(team_id):
        return away_id if team_id == home_id else home_id

    sets = [_extract_points(period, home_id, away_id)
            for period in (pbp["periods"] or [])]

    # First server per set: direct anchor on point 1, else alternation.
    first_servers = [
        pts[0]["anchor_server"] if pts else None for pts in sets
    ]
    resolved = {i: s for i, s in enumerate(first_servers[:4]) if s is not None}
    if resolved:
        j, s = next(iter(resolved.items()))
        for i in range(min(4, len(first_servers))):
            if first_servers[i] is None:
                first_servers[i] = s if (i - j) % 2 == 0 else other(s)

    rows = []
    for set_idx, points in enumerate(sets):
        server = first_servers[set_idx]
        for i, pt in enumerate(points):
            anchor = pt.pop("anchor_server")
            pt["server_id"] = server
            pt["serve_conflict"] = (
                anchor is not None and server is not None and anchor != server
            )
            pt["point_num"] = i + 1
            server = pt["winner_id"]  # winner serves next rally
            rows.append(pt)

    return {
        "contest_id": pbp["contestId"],
        "home_id": home_id,
        "away_id": away_id,
        "teams": pbp["teams"],
        "points": rows,
    }


def _extract_points(period: dict, home_id: int, away_id: int) -> list[dict]:
    has_scores = any(
        p["homeScore"] is not None
        for blk in period["playbyplayStats"]
        for p in blk["plays"]
    )
    if has_scores:
        return _extract_scored(period, home_id, away_id)
    return _extract_scoreless(period, home_id, away_id)


def _anchor(text: str, winner: int, home_id: int, away_id: int):
    if ACE_RE.match(text):
        return winner
    if SERVICE_ERROR_RE.match(text):
        return away_id if winner == home_id else home_id
    return None


def _extract_scored(period: dict, home_id: int, away_id: int) -> list[dict]:
    points = []
    prev_total = 0
    for block in period["playbyplayStats"]:
        winner = int(block["teamId"])
        for play in block["plays"]:
            h, a = play["homeScore"], play["visitorScore"]
            if h is None or a is None:
                continue
            if h + a != prev_total + 1:
                continue  # score correction / duplicate, not a new rally
            text = play["playText"] or ""
            points.append(
                {
                    "set": period["periodNumber"],
                    "winner_id": winner,
                    "home_score": h,
                    "away_score": a,
                    "anchor_server": _anchor(text, winner, home_id, away_id),
                    "play_text": text,
                    "clock": play["clock"],
                    "score_reconstructed": False,
                }
            )
            prev_total = h + a
    return points


def _extract_scoreless(period: dict, home_id: int, away_id: int) -> list[dict]:
    """Rebuild the score by counting rally-terminal plays per block team.

    These feeds contain duplicated plays (same team/text/clock repeated);
    two distinct rallies can't end at the same second, so exact tuples are
    deduplicated whenever a clock is present.
    """
    points = []
    h = a = 0
    seen: set = set()
    for block in period["playbyplayStats"]:
        winner = int(block["teamId"])
        for play in block["plays"]:
            text = (play["playText"] or "").strip()
            if not TERMINAL_RE.match(text):
                continue
            key = (winner, text, play["clock"])
            if play["clock"] and key in seen:
                continue
            seen.add(key)
            if winner == home_id:
                h += 1
            else:
                a += 1
            points.append(
                {
                    "set": period["periodNumber"],
                    "winner_id": winner,
                    "home_score": h,
                    "away_score": a,
                    "anchor_server": _anchor(text, winner, home_id, away_id),
                    "play_text": text,
                    "clock": play["clock"],
                    "score_reconstructed": True,
                }
            )
    return points
