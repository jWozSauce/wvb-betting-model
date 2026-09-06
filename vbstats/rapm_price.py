"""Price a match from player-level (RAPM) rally probabilities.

Given the two phase probabilities
    p1 = P(home wins a rally | home serving)
    p2 = P(home wins a rally | away serving)
compute exact set-win probability by dynamic programming over volleyball
scoring (race to `target`, win by two, rally winner serves next; the deuce
loop is solved as a fixed point), then build the six set-score outcomes with
the fitted 5th-set (to 15) probability and the set-score model's latent
overdispersion sigma.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

_GH_NODES, _GH_WEIGHTS = np.polynomial.hermite.hermgauss(21)


def set_win_prob(p1: float, p2: float, target: int = 25) -> float:
    """P(home wins the set), averaged over who serves first."""
    p1 = min(max(p1, 0.02), 0.98)
    p2 = min(max(p2, 0.02), 0.98)

    # deuce fixed point: states AH (home ad, home serving), AA (away ad,
    # away serving), D_H / D_A (level, home/away serving)
    d_h = d_a = 0.5
    for _ in range(200):
        ah = p1 + (1 - p1) * d_a
        aa = p2 * d_h
        d_h_new = p1 * ah + (1 - p1) * aa
        d_a_new = p2 * ah + (1 - p2) * aa
        if abs(d_h_new - d_h) + abs(d_a_new - d_a) < 1e-12:
            d_h, d_a = d_h_new, d_a_new
            break
        d_h, d_a = d_h_new, d_a_new

    @lru_cache(maxsize=None)
    def f(h: int, a: int, home_serving: bool) -> float:
        if h >= target and h - a >= 2:
            return 1.0
        if a >= target and a - h >= 2:
            return 0.0
        if h == target - 1 and a == target - 1:
            return d_h if home_serving else d_a
        p = p1 if home_serving else p2
        return p * f(h + 1, a, True) + (1 - p) * f(h, a + 1, False)

    return 0.5 * (f(0, 0, True) + f(0, 0, False))


def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return float(np.log(p / (1 - p)))


def set_score_probs6(p1: float, p2: float, sigma: float) -> np.ndarray:
    """Six-outcome distribution [3-0, 3-1, 3-2, 2-3, 1-3, 0-3].

    Sets 1-4 use the 25-point DP probability; set 5 uses the true 15-point
    DP probability (no lambda shrink needed — the DP prices the shorter set
    exactly). sigma is the latent per-match strength shock from the fitted
    set-score model, applied on the set-win logit as usual.
    """
    eta25 = _logit(set_win_prob(p1, p2, 25))
    eta15 = _logit(set_win_prob(p1, p2, 15))
    z = np.sqrt(2) * sigma * _GH_NODES
    p = 1 / (1 + np.exp(-(eta25 + z)))
    p5 = 1 / (1 + np.exp(-(eta15 + z)))
    q = 1 - p
    per_node = np.stack([
        p**3, 3 * p**3 * q, 6 * p**2 * q**2 * p5,
        6 * p**2 * q**2 * (1 - p5), 3 * p * q**3, q**3], axis=-1)
    w = _GH_WEIGHTS / np.sqrt(np.pi)
    return per_node.T @ w


def lineup_strength(rapm_rows, selected, weight_key=None):
    """(serve_sum, recv_sum, coverage) for a selected lineup, weighted 6/n."""
    rows = [r for r in rapm_rows if r["player"] in selected]
    if not rows:
        return 0.0, 0.0, 0.0
    w = 6.0 / len(rows)
    sv = w * sum(r["serve"] for r in rows)
    rc = w * sum(r["recv"] for r in rows)
    fitted = sum(1 for r in rows if r["serve"] or r["recv"])
    return sv, rc, fitted / len(rows)
