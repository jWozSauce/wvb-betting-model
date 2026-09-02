"""Serve/receive Elo ratings computed point-by-point from the rally table.

Each team carries two ratings, both starting at ``BASELINE``:

- serve Elo: strength when serving
- receive Elo: strength when receiving

A rally is a contest between the server's serve-Elo and the receiver's
receive-Elo. Expected server point-win probability follows the standard
logistic curve (400-point scale); both ratings update zero-sum with a small
per-point K. Because serving wins ~43% of rallies, serve ratings settle below
receive ratings league-wide — the *differences between teams* are what carry
information, so downstream models should use rating differences or include an
intercept.

Matches are processed in chronological order. Ratings are snapshotted BEFORE
a match's points are applied, so every output row contains only pre-game
information next to that game's outcome — safe for regression training.
"""

from __future__ import annotations

import pandas as pd

BASELINE = 1500.0


class TeamRatings:
    def __init__(self, baseline: float = BASELINE):
        self.baseline = baseline
        self.serve: dict[int, float] = {}
        self.receive: dict[int, float] = {}
        self.games: dict[int, int] = {}
        # Conference anchor: offset (centered on 0) added to every member
        # team's effective serve AND receive rating. Only cross-conference
        # points move it, so it tracks how the conference as a whole fares
        # against the rest of the country.
        self.conf: dict[str, float] = {}

    def get(self, team_id: int) -> tuple[float, float]:
        return (
            self.serve.get(team_id, self.baseline),
            self.receive.get(team_id, self.baseline),
        )

    def conf_elo(self, conf: str | None) -> float:
        return self.conf.get(conf, 0.0) if conf else 0.0

    def regress_to_mean(self, carryover: float):
        """Between seasons: shrink every rating toward the baseline."""
        for d in (self.serve, self.receive):
            for t in d:
                d[t] = self.baseline + carryover * (d[t] - self.baseline)
        # Conference membership shifts with realignment, but strength is
        # sticky; shrink toward 0 with the same factor.
        for c in self.conf:
            self.conf[c] = carryover * self.conf[c]
        self.games = {t: 0 for t in self.games}


def expected_serve_win(serve_elo: float, receive_elo: float,
                       serve_bonus: float = 0.0) -> float:
    return 1.0 / (1.0 + 10 ** ((receive_elo - serve_elo - serve_bonus) / 400.0))


def run_elo(
    matches: pd.DataFrame,
    points: pd.DataFrame,
    k: float = 1.0,
    home_adv: float = 0.0,
    conf_weight: float = 0.0,
    ratings: TeamRatings | None = None,
) -> tuple[pd.DataFrame, TeamRatings]:
    """Process matches chronologically; return per-match snapshot table.

    matches/points are the outputs of build_points.py (any number of seasons
    concatenated). ``ratings`` carries state across calls for multi-season
    runs. ``home_adv`` is an Elo bonus added to the home team's acting rating
    on non-neutral courts (0 = let the regression handle venue instead).

    ``conf_weight`` enables the two-tier conference anchor: a team's
    effective rating is team elo + conference elo. On cross-conference
    points, that share of the update moves the conference ratings (zero-sum
    between the two conferences) and the rest moves the team ratings; on
    in-conference points the offsets cancel and teams take the full update.
    """
    if ratings is None:
        ratings = TeamRatings()

    matches = matches.sort_values(["start_epoch", "contest_id"]).reset_index(drop=True)
    pts_by_game = dict(tuple(points.groupby("contest_id", sort=False)))

    rows = []
    for m in matches.itertuples():
        home, away = int(m.home_id), int(m.away_id)
        neutral = bool(getattr(m, "is_neutral", False))
        h_conf = getattr(m, "home_conf", None)
        a_conf = getattr(m, "away_conf", None)
        cross_conf = bool(h_conf and a_conf and h_conf != a_conf)
        h_serve, h_recv = ratings.get(home)
        a_serve, a_recv = ratings.get(away)
        h_conf_elo = ratings.conf_elo(h_conf)
        a_conf_elo = ratings.conf_elo(a_conf)

        game_pts = pts_by_game.get(m.contest_id)
        outcome = _match_outcome(m, game_pts, home, away)

        rows.append(
            {
                "contest_id": m.contest_id,
                "season": m.season,
                "start_epoch": m.start_epoch,
                "home_id": home,
                "away_id": away,
                "home_seo": m.home_seo,
                "away_seo": m.away_seo,
                "is_neutral": neutral,
                "is_championship": bool(m.is_championship),
                "is_conf_tournament": bool(m.is_conf_tournament),
                "venue": m.venue,
                "home_conf": h_conf,
                "away_conf": a_conf,
                # pre-game ratings (frozen before this match is applied)
                "home_serve_elo": h_serve,
                "home_receive_elo": h_recv,
                "away_serve_elo": a_serve,
                "away_receive_elo": a_recv,
                "home_conf_elo": h_conf_elo,
                "away_conf_elo": a_conf_elo,
                "home_games_played": ratings.games.get(home, 0),
                "away_games_played": ratings.games.get(away, 0),
                **outcome,
            }
        )

        # ---- apply this match's points to the ratings
        if game_pts is not None:
            h_bonus = home_adv if not neutral else 0.0
            conf_w = conf_weight if cross_conf else 0.0
            for p in game_pts.itertuples():
                if pd.isna(p.server_id):
                    continue
                server = int(p.server_id)
                receiver = away if server == home else home
                server_is_home = server == home
                s_elo = ratings.serve.get(server, ratings.baseline)
                r_elo = ratings.receive.get(receiver, ratings.baseline)
                s_conf, r_conf = (h_conf, a_conf) if server_is_home else (a_conf, h_conf)
                bonus = h_bonus if server_is_home else -h_bonus
                bonus += ratings.conf_elo(s_conf) - ratings.conf_elo(r_conf)
                exp = expected_serve_win(s_elo, r_elo, serve_bonus=bonus)
                actual = 1.0 if int(p.winner_id) == server else 0.0
                delta = k * (actual - exp)
                ratings.serve[server] = s_elo + (1 - conf_w) * delta
                ratings.receive[receiver] = r_elo - (1 - conf_w) * delta
                if conf_w:
                    ratings.conf[s_conf] = ratings.conf_elo(s_conf) + conf_w * delta
                    ratings.conf[r_conf] = ratings.conf_elo(r_conf) - conf_w * delta
        ratings.games[home] = ratings.games.get(home, 0) + 1
        ratings.games[away] = ratings.games.get(away, 0) + 1

    return pd.DataFrame(rows), ratings


def _match_outcome(m, game_pts, home: int, away: int) -> dict:
    out = {
        "home_sets": m.home_sets,
        "away_sets": m.away_sets,
        "home_win": m.home_sets > m.away_sets,
        "has_pbp": game_pts is not None,
        "n_points": 0,
        "home_points_won": None,
        "away_points_won": None,
        "home_serve_win_rate": None,
        "away_serve_win_rate": None,
    }
    if game_pts is None:
        return out
    out["n_points"] = len(game_pts)
    out["home_points_won"] = int((game_pts["winner_id"] == home).sum())
    out["away_points_won"] = int((game_pts["winner_id"] == away).sum())
    served = game_pts.dropna(subset=["server_id"])
    for side, team in (("home", home), ("away", away)):
        mask = served["server_id"].astype(int) == team
        if mask.any():
            out[f"{side}_serve_win_rate"] = float(
                (served.loc[mask, "winner_id"] == team).mean()
            )
    return out
