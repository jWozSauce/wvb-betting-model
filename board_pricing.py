"""Shared sportsbook card evaluation, cached per game; no network or logging."""
import numpy as np
import pandas as pd
import streamlit as st
import kelly
import paste_odds
from vbstats import model, player_metrics


@st.cache_data(show_spinner=False, max_entries=4096)
def evaluate_game(g, h_match, a_match, match_conf, h, a, venue_mode,
                  params, param_draws, context, vi, absents_map,
                  absence_annotations, repairs, conservative_q=20):
    neutral_b = venue_mode != "Home court"
    tossup_b = venue_mode.startswith("True toss-up")
    conservative = context["basis"] == "p20"
    w_model, bankroll = context["w_model"], context["bankroll"]
    kfrac, edge_cap = context["kelly_frac"], context["edge_cap"]
    value_req, CONSERVATIVE_Q = context["min_edge"], conservative_q
    card_rows = []
    Xg = model.features(pd.DataFrame([{
        "home_serve_elo": h.serve_elo,
        "home_receive_elo": h.receive_elo, "home_conf_elo": h.conf_elo,
        "away_serve_elo": a.serve_elo,
        "away_receive_elo": a.receive_elo, "away_conf_elo": a.conf_elo,
        "is_neutral": neutral_b,
    }]))
    Xgf = model.features(pd.DataFrame([{
        "home_serve_elo": a.serve_elo,
        "home_receive_elo": a.receive_elo, "home_conf_elo": a.conf_elo,
        "away_serve_elo": h.serve_elo,
        "away_receive_elo": h.receive_elo, "away_conf_elo": h.conf_elo,
        "is_neutral": neutral_b,
    }]))

    def probs6_b(pv):
        p = model.set_score_probs(Xg, pv)[0]
        if tossup_b:
            p = 0.5 * (p + model.set_score_probs(Xgf, pv)[0][::-1])
        return p

    probs_pt = probs6_b(params)
    draws_g = np.stack([probs6_b(d) for d in param_draws])
    mkt_devigs = paste_odds.market_devig(g["markets"])
    for mkt_i, mkt in enumerate(g["markets"]):
        p = paste_odds.price_market(probs_pt, mkt["market"],
                                    mkt["side"], mkt["point"])
        if p is None:
            continue
        p_draws = np.array([
            paste_odds.price_market(dp, mkt["market"], mkt["side"],
                                    mkt["point"]) for dp in draws_g])
        p_lo = float(np.percentile(p_draws, CONSERVATIVE_Q))
        implied = kelly.american_to_prob(mkt["odds"])
        # market blend: shrink model toward the de-vigged book price
        # (WPO); unpaired markets shrink toward the vig-included
        # implied instead (more conservative)
        # API markets carry their own devig anchor (sharpest book
        # quoting both sides); pasted boards pair complements here
        p_mkt = mkt.get("mkt_prob") or mkt_devigs[mkt_i]
        mkt_paired = p_mkt is not None
        if not mkt_paired:
            p_mkt = implied
        p_blend = kelly.blend_prob(p, p_mkt, w_model)
        p_lo_blend = kelly.blend_prob(p_lo, p_mkt, w_model)
        p_basis = p_lo_blend if conservative else p_blend
        edge = p_basis - implied
        stake_ = (kelly.kelly_stake(bankroll, kfrac, mkt["odds"],
                                    p_basis, edge_cap)
                  if edge >= value_req else 0.0)
        side_team = (h_match if mkt["side"] == "home" else
                     a_match if mkt["side"] == "away" else mkt["side"])
        bet_label_ = (f"{side_team} ML" if mkt["market"] == "ml" else
                      f"{side_team} {mkt['point']:+g} sets"
                      if mkt["market"] == "spread" else
                      f"{mkt['side'].title()} {mkt['point']:g} sets")
        absent_note = "; ".join(
            f"{t}: {', '.join(player_metrics.annotate(t, n.split(' (')[0], absence_annotations) if repairs else n.split(' (')[0] for n in absents_map[t])}"
            for t in (a_match, h_match) if t in absents_map)
        # betting AGAINST a shorthanded team measured -33% ROI in
        # the paper log: the book prices the absence before Elo does
        if mkt["side"] == "home":
            vs_short = a_match in absents_map
        elif mkt["side"] == "away":
            vs_short = h_match in absents_map
        else:  # totals: risky if either lineup is shorthanded
            vs_short = (a_match in absents_map
                        or h_match in absents_map)
        card_rows.append({
            "⚠": "⚠️" if match_conf < 0.8 else "",
            "⚕opp": "⚕" if vs_short else "",
            "vs_shorthanded": vs_short,
            "⚕ absent": absent_note,
            "match_conf": match_conf,
            "game_#": g.get("board_pos"),
            "time": g.get("time", ""),
            "game_date": g.get("date", ""),
            "matchup": f"{a_match} @ {h_match}",
            "site": vi.get("site", ""),
            "venue": vi.get("venue", ""),
            "bet": bet_label_, "odds": mkt["odds"],
            "book": mkt.get("book", ""),
            "model_prob": round(p, 4),
            "mkt_prob": round(p_mkt, 4),
            "blend_prob": round(p_blend, 4),
            "devig": (f"wpo ({mkt['devig_book']})"
                      if mkt.get("devig_book")
                      else "wpo" if mkt_paired else "one-sided"),
            f"p{CONSERVATIVE_Q}": round(p_lo, 4),
            "edge": round(edge, 4), "stake": stake_,
            "fair_odds": kelly.prob_to_american(p_blend),
            "market": mkt["market"], "side": mkt["side"],
            "point": mkt["point"],
            "away_team": a_match, "home_team": h_match,
        })
    return card_rows
