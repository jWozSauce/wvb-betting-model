"""First-pass volleyball RAPM: two-phase ridge regression on set outcomes.

    python scripts/fit_rapm.py --train 2021 2022 2023 --test 2024

Observation = one (set, serving-team) phase: y = serving team's rally win
share in that set, weight = rallies. Design: +1 in the SERVE column of each
serving-team starter, -1 in the RECEIVE column of each receiving-team
starter, plus a home-serving indicator. Ridge shrinkage handles the heavy
lineup collinearity. Players are keyed (team, player); a transfer is two
entities in this first pass.

Validation: predict test-season match winners from summed starter
coefficients (set-1 starters), compare vs picking by pre-game team Elo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

D = Path("data/processed")


def load_season(season):
    m = pd.read_parquet(D / f"matches_{season}.parquet")
    p = pd.read_parquet(D / f"points_{season}.parquet")
    s = pd.read_parquet(D / f"set_starters_{season}.parquet")
    return m, p, s


def phase_table(matches, points, starters):
    """One row per (contest, set, serving_team): rallies, wins, lineups."""
    pts = points.dropna(subset=["server_id"]).copy()
    pts["server_id"] = pts.server_id.astype(int)
    pts["win"] = (pts.winner_id == pts.server_id).astype(int)
    g = (pts.groupby(["contest_id", "set", "server_id"])
         .agg(n=("win", "size"), w=("win", "sum")).reset_index())
    m = matches[["contest_id", "home_id", "away_id", "home_seo",
                 "away_seo"]].copy()
    g = g.merge(m, on="contest_id", how="inner")
    g["serve_home"] = g.server_id == g.home_id
    g["serve_seo"] = np.where(g.serve_home, g.home_seo, g.away_seo)
    g["recv_seo"] = np.where(g.serve_home, g.away_seo, g.home_seo)
    # starters lookup: (contest, set, team) -> tuple of players
    lu = (starters.groupby(["contest_id", "set", "team"]).player
          .apply(tuple).to_dict())
    g["serve_lineup"] = [lu.get(k) for k in
                         zip(g.contest_id, g["set"], g.serve_seo)]
    g["recv_lineup"] = [lu.get(k) for k in
                        zip(g.contest_id, g["set"], g.recv_seo)]
    g = g.dropna(subset=["serve_lineup", "recv_lineup"])
    # some feeds list 7-11 names on the starters line (rotation + liberos);
    # keep 5..12 and weight each player 6/len so a team-set always
    # contributes six bodies' worth of design mass
    g = g[g.serve_lineup.str.len().between(5, 12)
          & g.recv_lineup.str.len().between(5, 12)]
    return g


def build_design(g, player_ix=None):
    """Sparse X with 2 columns per (team, player): serve, receive."""
    if player_ix is None:
        players = sorted({(t, p) for lus, ts in
                          ((g.serve_lineup, g.serve_seo),
                           (g.recv_lineup, g.recv_seo))
                          for lu, t in zip(lus, ts) for p in lu})
        player_ix = {tp: i for i, tp in enumerate(players)}
    rows, cols, vals = [], [], []
    for r, (slu, sseo, rlu, rseo) in enumerate(
            zip(g.serve_lineup, g.serve_seo, g.recv_lineup, g.recv_seo)):
        w_s, w_r = 6.0 / len(slu), 6.0 / len(rlu)
        for p in slu:
            ix = player_ix.get((sseo, p))
            if ix is not None:
                rows.append(r); cols.append(2 * ix); vals.append(w_s)
        for p in rlu:
            ix = player_ix.get((rseo, p))
            if ix is not None:
                rows.append(r); cols.append(2 * ix + 1); vals.append(-w_r)
    n_col = 2 * len(player_ix) + 1
    home_col = n_col - 1
    for r, sh in enumerate(g.serve_home):
        rows.append(r); cols.append(home_col)
        vals.append(1.0 if sh else -1.0)
    X = sparse.csr_matrix((vals, (rows, cols)), shape=(len(g), n_col))
    return X, player_ix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, nargs="+", required=True)
    ap.add_argument("--test", type=int, default=None)
    ap.add_argument("--alphas", type=float, nargs="+",
                    default=[1000, 3000, 10000])
    ap.add_argument("--save-production", action="store_true",
                    help="fit once (first alpha) with recency weighting and "
                         "write app_data/rapm.parquet + rapm_meta.json")
    ap.add_argument("--recency", type=float, default=0.75,
                    help="per-year weight decay for older seasons")
    args = ap.parse_args()

    train_parts = []
    for s in args.train:
        m, p, st = load_season(s)
        t = phase_table(m, p, st)
        t["season"] = s
        train_parts.append(t)
    tr = pd.concat(train_parts, ignore_index=True)
    print(f"train: {len(tr)} phase-rows across {args.train}")

    X, player_ix = build_design(tr)
    y = (tr.w / tr.n).to_numpy()
    wgt = tr.n.to_numpy().astype(float)
    cur = max(args.train)
    wgt = wgt * (args.recency ** (cur - tr.season.to_numpy()))
    print(f"design: {X.shape[0]} rows x {X.shape[1]} cols "
          f"({len(player_ix)} player-team entities)")

    from sklearn.linear_model import Ridge

    if args.save_production:
        import json
        alpha = args.alphas[0]
        model = Ridge(alpha=alpha, solver="sparse_cg")
        model.fit(X, y, sample_weight=wgt)
        coefs = model.coef_
        rows = [{"team": t, "player": p,
                 "serve": coefs[2 * ix], "recv": coefs[2 * ix + 1]}
                for (t, p), ix in player_ix.items()]
        rapm = pd.DataFrame(rows)
        # current-season participation for lineup defaults in the app
        st_cur = pd.read_parquet(D / f"set_starters_{cur}.parquet")
        box_cur = pd.read_parquet(D / f"player_box_{cur}.parquet")
        sets_cur = (st_cur.groupby(["team", "player"]).size()
                    .rename("sets_started_cur").reset_index())
        last_cid = (st_cur.sort_values("start_epoch")
                    .groupby("team").contest_id.last())
        last_lineup = set()
        for team, cid in last_cid.items():
            sub = st_cur[(st_cur.team == team) & (st_cur.contest_id == cid)
                         & (st_cur["set"] == 1)]
            for p in sub.player:
                last_lineup.add((team, p))
        roster = (box_cur[["team", "player"]].drop_duplicates())
        roster = roster.merge(rapm, on=["team", "player"], how="left")
        roster = roster.merge(sets_cur, on=["team", "player"], how="left")
        roster["serve"] = roster.serve.fillna(0.0)
        roster["recv"] = roster.recv.fillna(0.0)
        roster["sets_started_cur"] = roster.sets_started_cur.fillna(0).astype(int)
        roster["in_last_lineup"] = [
            (t, p) in last_lineup for t, p in zip(roster.team, roster.player)]
        out = Path("app_data")
        roster.to_parquet(out / "rapm.parquet", index=False)
        json.dump({"intercept": float(model.intercept_),
                   "home_serve": float(coefs[-1]), "alpha": alpha,
                   "recency": args.recency, "seasons": args.train,
                   "current_season": cur},
                  open(out / "rapm_meta.json", "w"), indent=1)
        print(f"production RAPM: {len(rapm)} fitted entities, "
              f"{len(roster)} current-roster rows -> app_data/rapm.parquet | "
              f"intercept {model.intercept_:.4f} home {coefs[-1]:+.4f}")
        return

    # test-season data & lineups (set-1 starters as the match lineup)
    m_t, p_t, s_t = load_season(args.test)
    g_t = phase_table(m_t, p_t, s_t)
    elo = pd.read_parquet(D / "elo_matches.parquet")
    elo = elo[elo.season == args.test]

    for alpha in args.alphas:
        model = Ridge(alpha=alpha, solver="sparse_cg")
        model.fit(X, y, sample_weight=wgt)
        coefs = model.coef_
        base = model.intercept_

        def team_strength(t, lineup_serve, lineup_recv):
            w = 6.0 / len(lineup_serve)
            sv = sum(w * coefs[2 * player_ix[(t, p)]] for p in lineup_serve
                     if (t, p) in player_ix)
            # receive coefficients are positive-good (they enter the design
            # with -1 for the receiving side)
            rc = sum(w * coefs[2 * player_ix[(t, p)] + 1]
                     for p in lineup_recv if (t, p) in player_ix)
            cov = np.mean([(t, p) in player_ix for p in lineup_serve])
            return sv, rc, cov

        # per test match: predicted point share for home team
        preds = []
        first = g_t[g_t["set"] == 1]
        for cid, sub in first.groupby("contest_id"):
            home_row = sub[sub.serve_home]
            away_row = sub[~sub.serve_home]
            if not len(home_row) or not len(away_row):
                continue
            hr, ar = home_row.iloc[0], away_row.iloc[0]
            h_sv, h_rc, cov_h = team_strength(hr.serve_seo, hr.serve_lineup,
                                              hr.serve_lineup)
            a_sv, a_rc, cov_a = team_strength(ar.serve_seo, ar.serve_lineup,
                                              ar.serve_lineup)
            # home point share proxy: home serve win + home recv win rates
            home_adv = coefs[-1]  # fitted home-serving indicator
            p_home_serve = base + home_adv + h_sv - a_rc
            p_home_recv = 1 - (base - home_adv + a_sv - h_rc)
            share = (p_home_serve + p_home_recv) / 2
            preds.append({"contest_id": cid, "share": share,
                          "coverage": (cov_h + cov_a) / 2})
        pr = pd.DataFrame(preds).merge(
            elo[["contest_id", "home_win", "home_serve_elo",
                 "home_receive_elo", "home_conf_elo", "away_serve_elo",
                 "away_receive_elo", "away_conf_elo"]], on="contest_id")
        pr["elo_edge"] = (pr.home_serve_elo + pr.home_receive_elo
                          + 2 * pr.home_conf_elo - pr.away_serve_elo
                          - pr.away_receive_elo - 2 * pr.away_conf_elo)
        acc_rapm = ((pr.share > 0.5) == pr.home_win).mean()
        acc_elo = ((pr.elo_edge > 0) == pr.home_win).mean()
        hi = pr[pr.coverage >= 0.67]
        acc_hi = ((hi.share > 0.5) == hi.home_win).mean() if len(hi) else float("nan")
        acc_elo_hi = ((hi.elo_edge > 0) == hi.home_win).mean() if len(hi) else float("nan")
        print(f"alpha={alpha:>7.0f}: test matches {len(pr)} "
              f"(avg lineup coverage {pr.coverage.mean():.0%}) | "
              f"RAPM acc {acc_rapm:.1%} vs Elo {acc_elo:.1%} | "
              f"coverage>=2/3 (n={len(hi)}): RAPM {acc_hi:.1%} vs Elo {acc_elo_hi:.1%}")

        top = sorted(player_ix.items(), key=lambda kv: -(
            coefs[2 * kv[1]] + coefs[2 * kv[1] + 1]))[:10]
        if alpha == args.alphas[-1]:
            print("  top 10 (serve+recv impact, per rally):")
            for (t, p), ix in top:
                print(f"    {p} ({t}): serve {coefs[2*ix]:+.4f} "
                      f"recv {coefs[2*ix+1]:+.4f}")


if __name__ == "__main__":
    main()
