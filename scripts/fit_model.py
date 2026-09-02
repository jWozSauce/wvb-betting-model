"""Fit the Bayesian set-score model and validate every market on 2024-2025.

    python scripts/fit_model.py

Writes data/processed/model_params.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vbstats import model

TRAIN = {2021, 2022, 2023}
VAL = {2024, 2025}


def logloss(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


def calibration(p, y, bins=10):
    df = pd.DataFrame({"p": p, "y": y})
    df["bin"] = pd.qcut(df.p, bins, duplicates="drop")
    g = df.groupby("bin", observed=True).agg(pred=("p", "mean"), obs=("y", "mean"),
                                             n=("y", "size"))
    return g


def main():
    e = pd.read_parquet("data/processed/elo_matches.parquet")
    valid = model.outcome_index(e) >= 0
    print(f"matches: {len(e)}, valid best-of-5 scorelines: {valid.sum()}")
    e = e[valid].reset_index(drop=True)

    train = e[e.season.isin(TRAIN)]
    val = e[e.season.isin(VAL)]
    Xt, yt = model.features(train), model.outcome_index(train)
    Xv, yv = model.features(val), model.outcome_index(val)

    fitted = model.fit(Xt, yt)
    model.save(fitted, "data/processed/model_params.json")
    Path("app_data").mkdir(exist_ok=True)
    model.save(fitted, "app_data/model_params.json")
    names = ["intercept", "serve_edge/100", "receive_edge/100", "home", "lam", "log_sigma"]
    sds = np.sqrt(np.diag(fitted["cov"]))
    print("\nposterior (MAP +/- sd):")
    for n, v, s in zip(names, fitted["params"], sds):
        print(f"  {n:>16}: {v:+.4f} +/- {s:.4f}")

    probs_v = model.set_score_probs(Xv, fitted["params"])
    mk = model.markets(probs_v)
    home_win = np.isin(yv, [0, 1, 2]).astype(float)
    cover_15 = np.isin(yv, [0, 1]).astype(float)
    cover_25 = (yv == 0).astype(float)
    five_sets = np.isin(yv, [2, 3]).astype(float)
    under_35 = np.isin(yv, [0, 5]).astype(float)

    print("\nvalidation (2024-2025), log-loss / accuracy:")
    for label, p, y in [
        ("moneyline (home win)", mk["home_ml"], home_win),
        ("home -1.5 sets", mk["home_minus_1_5"], cover_15),
        ("home -2.5 sets", mk["home_minus_2_5"], cover_25),
        ("under 3.5 total sets", mk["under_3_5_sets"], under_35),
        ("match goes 5 sets", mk["exactly_5_sets"], five_sets),
    ]:
        print(f"  {label:>22}: {logloss(p, y):.5f} / {np.mean((p > 0.5) == y):.1%}"
              f"  (base rate {y.mean():.1%})")

    print("\nmoneyline calibration (val):")
    print(calibration(mk["home_ml"], home_win).round(3).to_string())
    print("\n5-set probability calibration (val):")
    print(calibration(mk["exactly_5_sets"], five_sets, bins=5).round(3).to_string())

    # multinomial check: predicted vs observed set-score distribution
    print("\nset-score distribution (val): predicted% vs observed%")
    pred = probs_v.mean(axis=0) * 100
    obs = np.bincount(yv, minlength=6) / len(yv) * 100
    for oc, pr, ob in zip(model.OUTCOMES, pred, obs):
        print(f"  {oc[0]}-{oc[1]}: {pr:5.1f} vs {ob:5.1f}")


if __name__ == "__main__":
    main()
