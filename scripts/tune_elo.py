"""Tune Elo hyperparameters (k, carryover, conf_weight) on held-out log-loss.

Protocol: run the multi-season chain for a parameter combo, fit a 2-parameter
logistic map P(home win) = sigmoid(a + b * elo_edge) on TRAIN seasons, then
score log-loss on VAL seasons. Coordinate descent over each parameter grid.

    python scripts/tune_elo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEASONS = [2021, 2022, 2023, 2024, 2025]
TRAIN_SEASONS = {2021, 2022, 2023}
VAL_SEASONS = {2024, 2025}
BASELINE = 1500.0
DATA = Path("data/processed")


def load_compact():
    """Per-season list of matches with numpy point arrays, in chrono order."""
    seasons = []
    for season in SEASONS:
        matches = pd.read_parquet(DATA / f"matches_{season}.parquet")
        points = pd.read_parquet(DATA / f"points_{season}.parquet")
        points = points.dropna(subset=["server_id"])
        pts = {
            cid: (g["server_id"].to_numpy(np.int64),
                  g["winner_id"].to_numpy(np.int64))
            for cid, g in points.groupby("contest_id", sort=False)
        }
        matches = matches.sort_values(["start_epoch", "contest_id"])
        rows = []
        for m in matches.itertuples():
            servers, winners = pts.get(m.contest_id, (None, None))
            rows.append(
                (
                    int(m.home_id), int(m.away_id),
                    m.home_conf, m.away_conf,
                    bool(m.home_sets > m.away_sets),
                    servers, winners,
                )
            )
        seasons.append((season, rows))
        print(f"loaded {season}: {len(rows)} matches")
    return seasons


def run_chain(seasons, k, carryover, conf_weight):
    """Fast chain; returns (season, edge, home_win, min_games) per match."""
    serve, recv, conf, games = {}, {}, {}, {}
    out = []
    for si, (season, rows) in enumerate(seasons):
        if si > 0:
            for d in (serve, recv):
                for t in d:
                    d[t] = BASELINE + carryover * (d[t] - BASELINE)
            for c in conf:
                conf[c] = carryover * conf[c]
            games = {t: 0 for t in games}
        for home, away, h_conf, a_conf, home_win, servers, winners in rows:
            h_conf_elo = conf.get(h_conf, 0.0) if h_conf else 0.0
            a_conf_elo = conf.get(a_conf, 0.0) if a_conf else 0.0
            edge = (
                serve.get(home, BASELINE) + recv.get(home, BASELINE) + 2 * h_conf_elo
                - serve.get(away, BASELINE) - recv.get(away, BASELINE) - 2 * a_conf_elo
            )
            out.append(
                (season, edge, home_win, min(games.get(home, 0), games.get(away, 0)))
            )
            if servers is not None:
                cross = bool(h_conf and a_conf and h_conf != a_conf)
                cw = conf_weight if cross else 0.0
                for server, winner in zip(servers, winners):
                    receiver = away if server == home else home
                    s_conf, r_conf = (h_conf, a_conf) if server == home else (a_conf, h_conf)
                    s_elo = serve.get(server, BASELINE)
                    r_elo = recv.get(receiver, BASELINE)
                    bonus = (conf.get(s_conf, 0.0) if s_conf else 0.0) - (
                        conf.get(r_conf, 0.0) if r_conf else 0.0
                    )
                    exp = 1.0 / (1.0 + 10 ** ((r_elo - s_elo - bonus) / 400.0))
                    delta = k * ((1.0 if winner == server else 0.0) - exp)
                    serve[server] = s_elo + (1 - cw) * delta
                    recv[receiver] = r_elo - (1 - cw) * delta
                    if cw:
                        conf[s_conf] = conf.get(s_conf, 0.0) + cw * delta
                        conf[r_conf] = conf.get(r_conf, 0.0) - cw * delta
            games[home] = games.get(home, 0) + 1
            games[away] = games.get(away, 0) + 1
    return np.array(out, dtype=[("season", "i4"), ("edge", "f8"),
                                ("home_win", "?"), ("min_games", "i4")])


def fit_logistic(x, y, iters=50):
    """Newton-Raphson for sigmoid(a + b*x); returns (a, b)."""
    X = np.column_stack([np.ones_like(x), x])
    w = np.zeros(2)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-X @ w))
        g = X.T @ (y - p)
        H = (X * (p * (1 - p))[:, None]).T @ X
        step = np.linalg.solve(H + 1e-9 * np.eye(2), g)
        w += step
        if np.abs(step).max() < 1e-10:
            break
    return w


def evaluate(res):
    train = res[np.isin(res["season"], list(TRAIN_SEASONS))]
    val = res[np.isin(res["season"], list(VAL_SEASONS))]
    w = fit_logistic(train["edge"], train["home_win"].astype(float))
    p = 1.0 / (1.0 + np.exp(-(w[0] + w[1] * val["edge"])))
    p = np.clip(p, 1e-12, 1 - 1e-12)
    y = val["home_win"].astype(float)
    ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    acc = np.mean((p > 0.5) == val["home_win"])
    return ll, acc


def main():
    seasons = load_compact()

    # sanity: fast chain must agree with the reference implementation
    from vbstats.elo import run_elo

    ref_m = pd.read_parquet(DATA / "matches_2021.parquet")
    ref_p = pd.read_parquet(DATA / "points_2021.parquet")
    table, _ = run_elo(ref_m, ref_p, k=1.0, conf_weight=0.2)
    ref_edge = ((table.home_serve_elo + table.home_receive_elo + 2 * table.home_conf_elo)
                - (table.away_serve_elo + table.away_receive_elo + 2 * table.away_conf_elo))
    fast = run_chain(seasons[:1], k=1.0, carryover=0.75, conf_weight=0.2)
    diff = np.abs(np.sort(ref_edge.to_numpy()) - np.sort(fast["edge"])).max()
    print(f"fast-vs-reference max edge diff: {diff:.2e}")
    assert diff < 1e-6, "fast chain diverges from vbstats.elo.run_elo"

    params = {"k": 1.0, "carryover": 0.75, "conf_weight": 0.2}
    grids = {
        "k": [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0],
        "carryover": [0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0],
        "conf_weight": [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4],
    }
    cache = {}

    def score(p):
        key = tuple(sorted(p.items()))
        if key not in cache:
            t0 = time.time()
            res = run_chain(seasons, **p)
            ll, acc = evaluate(res)
            cache[key] = (ll, acc)
            print(f"  {p} -> logloss {ll:.5f}  acc {acc:.1%}  ({time.time()-t0:.0f}s)")
        return cache[key]

    best_ll, _ = score(params)
    for sweep in range(3):
        print(f"--- pass {sweep + 1} ---")
        improved = False
        for name, grid in grids.items():
            results = []
            for v in grid:
                trial = {**params, name: v}
                ll, acc = score(trial)
                results.append((ll, v))
            ll, v = min(results)
            if ll < best_ll - 1e-6:
                best_ll = ll
                params[name] = v
                improved = True
            print(f"best {name}: {params[name]} (logloss {best_ll:.5f})")
        if not improved:
            break

    print("\n=== BEST ===")
    print(json.dumps({**params, "val_logloss": best_ll}, indent=1))
    Path("data/processed/elo_tuning.json").write_text(
        json.dumps({**params, "val_logloss": best_ll}, indent=1)
    )


if __name__ == "__main__":
    main()
