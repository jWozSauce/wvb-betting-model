"""Bayesian set-score model on top of pre-game Elo ratings.

One model prices every market. Per-set home win probability:

    p_set = sigmoid(b0 + b1*serve_edge/100 + b2*receive_edge/100 + b3*home)

where serve_edge = (home serve + home conf) - (away receive + away conf) and
receive_edge = (home receive + home conf) - (away serve + away conf).

Sets 1-4 are treated as iid with probability p; the deciding 5th set (played
to 15, higher variance) uses p5 = 0.5 + lam * (p - 0.5), with lam learned.
Best-of-5 combinatorics then give the six set-score outcomes:

    P(3-0) = p^3                     P(0-3) = q^3
    P(3-1) = 3 p^3 q                 P(1-3) = 3 p q^3
    P(3-2) = 6 p^2 q^2 p5            P(2-3) = 6 p^2 q^2 (1 - p5)

Every market is a sum over these: moneyline = P(3-0)+P(3-1)+P(3-2);
-1.5 sets = P(3-0)+P(3-1); -2.5 sets = P(3-0); under 3.5 total sets =
P(3-0)+P(0-3); under 4.5 adds P(3-1)+P(1-3).

Fitting is MAP with N(0, 2.5^2) priors on betas, N(1, 0.5^2) on lam, plus a
Laplace (inverse-Hessian) posterior covariance for parameter uncertainty.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize

OUTCOMES = [(3, 0), (3, 1), (3, 2), (2, 3), (1, 3), (0, 3)]
# params: [b0, b_serve, b_receive, b_home, lam, log_sigma]
# sigma is a latent per-match strength shock: p = sigmoid(eta + sigma*z),
# z ~ N(0,1) integrated out by Gauss-Hermite quadrature. It captures the
# fact that the Elo edge measures true strength with error, which fattens
# the sweep outcomes relative to iid-binomial sets.
PRIOR_SD = np.array([2.5, 2.5, 2.5, 2.5, 0.5, 1.0])
PRIOR_MEAN = np.array([0.0, 0.0, 0.0, 0.0, 1.0, -1.0])
_GH_NODES, _GH_WEIGHTS = np.polynomial.hermite.hermgauss(21)


def features(df: pd.DataFrame) -> np.ndarray:
    """Feature matrix [1, serve_edge/100, receive_edge/100, home] per match."""
    serve_edge = (
        df.home_serve_elo + df.home_conf_elo - df.away_receive_elo - df.away_conf_elo
    )
    receive_edge = (
        df.home_receive_elo + df.home_conf_elo - df.away_serve_elo - df.away_conf_elo
    )
    home = (~df.is_neutral).astype(float)
    return np.column_stack(
        [np.ones(len(df)), serve_edge / 100.0, receive_edge / 100.0, home]
    )


def outcome_index(df: pd.DataFrame) -> np.ndarray:
    """Map (home_sets, away_sets) to 0..5; -1 for invalid scorelines."""
    lookup = {oc: i for i, oc in enumerate(OUTCOMES)}
    return np.array(
        [lookup.get((h, a), -1) for h, a in zip(df.home_sets, df.away_sets)]
    )


def set_score_probs(X: np.ndarray, params: np.ndarray) -> np.ndarray:
    """(n, 6) matrix of set-score probabilities, latent shock integrated out."""
    betas, lam, sigma = params[:4], params[4], np.exp(params[5])
    eta = X @ betas
    # (n, K) per-quadrature-node set-win probability
    p = 1.0 / (1.0 + np.exp(-(eta[:, None] + sigma * np.sqrt(2) * _GH_NODES[None, :])))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    q = 1.0 - p
    p5 = np.clip(0.5 + lam * (p - 0.5), 1e-9, 1 - 1e-9)
    per_node = np.stack(
        [
            p**3,
            3 * p**3 * q,
            6 * p**2 * q**2 * p5,
            6 * p**2 * q**2 * (1 - p5),
            3 * p * q**3,
            q**3,
        ],
        axis=-1,
    )  # (n, K, 6)
    w = _GH_WEIGHTS / np.sqrt(np.pi)
    return np.einsum("nko,k->no", per_node, w)


def markets(probs: np.ndarray) -> dict[str, np.ndarray]:
    """Market probabilities (home perspective) from the 6-outcome matrix."""
    return {
        "home_ml": probs[:, 0] + probs[:, 1] + probs[:, 2],
        "home_minus_1_5": probs[:, 0] + probs[:, 1],
        "home_minus_2_5": probs[:, 0],
        "away_minus_1_5": probs[:, 5] + probs[:, 4],
        "away_minus_2_5": probs[:, 5],
        "under_3_5_sets": probs[:, 0] + probs[:, 5],
        "under_4_5_sets": probs[:, 0] + probs[:, 5] + probs[:, 1] + probs[:, 4],
        "exactly_5_sets": probs[:, 2] + probs[:, 3],
    }


def neg_log_posterior(params, X, y_idx):
    probs = set_score_probs(X, params)
    ll = np.log(probs[np.arange(len(y_idx)), y_idx]).sum()
    lp = -0.5 * (((params - PRIOR_MEAN) / PRIOR_SD) ** 2).sum()
    return -(ll + lp)


def fit(X: np.ndarray, y_idx: np.ndarray) -> dict:
    x0 = PRIOR_MEAN.copy()
    res = minimize(neg_log_posterior, x0, args=(X, y_idx), method="Nelder-Mead",
                   options={"maxiter": 5000, "xatol": 1e-8, "fatol": 1e-8})
    res = minimize(neg_log_posterior, res.x, args=(X, y_idx), method="BFGS")
    # Laplace covariance from numerical Hessian
    eps = 1e-4
    n = len(res.x)
    H = np.zeros((n, n))
    f0 = neg_log_posterior(res.x, X, y_idx)
    for i in range(n):
        for j in range(i, n):
            ei = np.eye(n)[i] * eps
            ej = np.eye(n)[j] * eps
            H[i, j] = H[j, i] = (
                neg_log_posterior(res.x + ei + ej, X, y_idx)
                - neg_log_posterior(res.x + ei, X, y_idx)
                - neg_log_posterior(res.x + ej, X, y_idx)
                + f0
            ) / eps**2
    cov = np.linalg.inv(H)
    return {"params": res.x, "cov": cov, "neg_log_post": res.fun}


def save(fitted: dict, path):
    json.dump(
        {
            "param_names": ["intercept", "serve_edge", "receive_edge", "home",
                            "lam", "log_sigma"],
            "params": fitted["params"].tolist(),
            "cov": fitted["cov"].tolist(),
            "param_sd": np.sqrt(np.diag(fitted["cov"])).tolist(),
        },
        open(path, "w"),
        indent=1,
    )


def load(path) -> np.ndarray:
    return np.array(json.load(open(path))["params"])
