"""Backtest the model against real historical closing lines (OddsPapi).

Joins data/processed/odds_hist_2026.parquet (closing pregame prices from
DK/FD/BetOnline) to the season's results + pre-game Elo snapshots, prices
every market with the production model params, and simulates the deployed
strategy (market blend w=0.30, edge gate on the blended probability vs the
vig-included implied of the closing price).

2026 is genuinely out-of-sample: model params and Elo hyperparameters were
fit on 2021-2025 only.

Usage: python scripts/backtest_odds.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kelly  # noqa: E402
import paste_odds  # noqa: E402
from vbstats import model  # noqa: E402

W_MODEL = 0.30
ET = "America/New_York"


def main():
    odds = pd.read_parquet("data/processed/odds_hist_2026.parquet")
    odds = odds[odds.book != ""].copy()  # drop odds-less sweep sentinels
    res = pd.read_parquet("app_data/results_current.parquet")
    res = res[(res.home_sets == 3) | (res.away_sets == 3)].copy()
    res["date"] = (pd.to_datetime(res.start_epoch, unit="s", utc=True)
                   .dt.tz_convert(ET).dt.date)
    params = np.array(json.load(open("app_data/model_params.json"))["params"])
    ratings = pd.read_parquet("app_data/elo_current.parquet")
    fullnames = dict(zip(ratings.team, ratings.name_full))
    seos = ratings.team.tolist()

    # map book names -> seonames once per unique name
    name_map = {}
    for nm in pd.concat([odds.home_name, odds.away_name]).dropna().unique():
        m, s = paste_odds.match_team(nm, seos, fullnames=fullnames)
        name_map[nm] = m if (m and s >= 0.8) else None
    odds["home_seo"] = odds.home_name.map(name_map)
    odds["away_seo"] = odds.away_name.map(name_map)
    n_unmapped = odds.home_seo.isna().sum() + odds.away_seo.isna().sum()
    odds = odds.dropna(subset=["home_seo", "away_seo"])
    odds["date"] = (pd.to_datetime(odds.start_time, utc=True)
                    .dt.tz_convert(ET).dt.date)

    # index results by both orientations for the fixture join
    ridx = {}
    for r in res.itertuples():
        ridx.setdefault((r.home_seo, r.away_seo, r.date), (r, False))
        ridx.setdefault((r.away_seo, r.home_seo, r.date), (r, True))

    probs_cache = {}

    def probs6(r):
        if r.contest_id not in probs_cache:
            X = model.features(pd.DataFrame([{
                "home_serve_elo": r.home_serve_elo,
                "home_receive_elo": r.home_receive_elo,
                "home_conf_elo": r.home_conf_elo,
                "away_serve_elo": r.away_serve_elo,
                "away_receive_elo": r.away_receive_elo,
                "away_conf_elo": r.away_conf_elo,
                "is_neutral": bool(r.is_neutral)}]))
            probs_cache[r.contest_id] = model.set_score_probs(X, params)[0]
        return probs_cache[r.contest_id]

    rows, n_nores = [], 0
    for o in odds.itertuples():
        hit = None
        for dd in (0, 1, -1):
            hit = ridx.get((o.home_seo, o.away_seo,
                            o.date + pd.Timedelta(days=dd).to_pytimedelta()))
            if hit:
                break
        if not hit:
            n_nores += 1
            continue
        r, flipped = hit
        side = o.side
        if flipped and side in ("home", "away"):  # translate to results frame
            side = "away" if side == "home" else "home"
        point = o.point if o.point is not None and not pd.isna(o.point) \
            else ""
        p_model = paste_odds.price_market(probs6(r), o.market, side, point)
        if p_model is None:
            continue
        implied = 1.0 / o.close_dec
        won, push = settle(o.market, side, point,
                           int(r.home_sets), int(r.away_sets))
        rows.append({
            "date": o.date, "book": o.book, "market": o.market,
            "side": side, "point": point, "fixture": o.fixture_id,
            "matchup": f"{o.away_seo} @ {o.home_seo}",
            "close_dec": o.close_dec, "implied": implied,
            "p_model": p_model, "won": won, "push": push,
            "is_fav": implied > 0.5,
        })
    bt = pd.DataFrame(rows)

    # within-book devig anchor + blend, exactly like the app
    def pair_key(m):
        if m.market == "spread":
            return (m.fixture, m.book, "spread",
                    m.point if m.side == "home" else -m.point)
        return (m.fixture, m.book, m.market, m.point)

    bt["pk"] = [pair_key(m) for m in bt.itertuples()]
    dv = {}
    for pk, grp in bt.groupby("pk"):
        if len(grp) == 2:
            g = grp.iloc
            p1, p2 = kelly.vig_free_probs(dec_to_us(g[0].close_dec),
                                          dec_to_us(g[1].close_dec))
            dv[(pk, g[0].side)] = p1
            dv[(pk, g[1].side)] = p2
    bt["p_mkt"] = [dv.get((m.pk, m.side), m.implied)
                   for m in bt.itertuples()]
    bt["p_blend"] = [kelly.blend_prob(m.p_model, m.p_mkt, W_MODEL)
                     for m in bt.itertuples()]
    bt["edge_model"] = bt.p_model - bt.implied
    bt["edge_blend"] = bt.p_blend - bt.implied

    print(f"\n=== JOIN: {len(bt)} priced closing lines | "
          f"{bt.fixture.nunique()} fixtures | unmapped names {n_unmapped} | "
          f"no-result {n_nores}")
    print(bt.groupby(["book", "market"]).size().unstack(fill_value=0))

    # model vs market: logloss on the ml market (one row per fixture side=home)
    ml = bt[(bt.market == "ml") & (bt.side == "home")].drop_duplicates("fixture")
    if len(ml):
        y = ml.won.astype(float)
        for lbl, p in (("model", ml.p_model), ("market(devig)", ml.p_mkt),
                       ("blend w=0.30", ml.p_blend)):
            p = p.clip(1e-6, 1 - 1e-6)
            ll = -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
            acc = ((p > 0.5) == y).mean()
            print(f"\nML {lbl:14} logloss {ll:.4f}  acc {acc:.1%}  "
                  f"(n={len(ml)})")

    # strategy sim on blended edge at several gates, flat 1u stakes
    print("\n=== flat-stake ROI by edge gate (blend basis, dedup best "
          "line per bet across books)")
    key = ["fixture", "market", "side", "point"]
    best = bt.sort_values("close_dec", ascending=False).drop_duplicates(key)
    for basis in ("edge_blend", "edge_model"):
        print(f"\n  basis: {basis}")
        for gate in (0.02, 0.04, 0.06):
            b = best[best[basis] >= gate]
            if not len(b):
                print(f"   >= {gate:.0%}: no bets")
                continue
            pnl = np.where(b.push, 0.0,
                           np.where(b.won, b.close_dec - 1.0, -1.0))
            print(f"   >= {gate:.0%}: n={len(b):4d}  "
                  f"W-L {int(b.won.sum())}-{int((~b.won & ~b.push).sum())}  "
                  f"ROI {pnl.mean():+.1%}")
    for seg, mask in (("favs", best.is_fav), ("dogs", ~best.is_fav)):
        b = best[mask & (best.edge_blend >= 0.02)]
        if len(b):
            pnl = np.where(b.push, 0.0,
                           np.where(b.won, b.close_dec - 1.0, -1.0))
            print(f"  blend>=2% {seg}: n={len(b)}  ROI {pnl.mean():+.1%}")

    out = Path("data/processed/backtest_odds_2026.parquet")
    bt = bt.drop(columns=["pk"])
    bt["point"] = bt.point.astype(str)  # ml rows are "" — keep one dtype
    bt.to_parquet(out, index=False)
    print(f"\nrow-level results -> {out}")


def dec_to_us(dec):
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def settle(market, side, point, hs, as_):
    total = hs + as_
    if market == "ml":
        return ((hs if side == "home" else as_) == 3, False)
    if market == "spread":
        margin = (hs - as_) if side == "home" else (as_ - hs)
        adj = margin + float(point)
        return adj > 0, adj == 0
    if market == "total":
        diff = total - float(point)
        return (diff > 0 if side == "over" else diff < 0), diff == 0
    raise ValueError(market)


if __name__ == "__main__":
    main()
