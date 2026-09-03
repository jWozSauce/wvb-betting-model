"""Women's College Volleyball — set-score model pricer.

Structured like the NCAAF Python_Asshole_Algo app: password gate, bankroll /
Kelly settings synced from the shared Constants Google Sheet (Vball row),
manual odds entry, Kelly staking with edge cap. No slate pull — pick the two
teams, enter the book's odds, get fair prices and stakes.

Tabs: Price a match | Rankings | Results (with "update current season").

Secrets (Streamlit Cloud -> App settings -> Secrets):
  APP_PASSWORD = "..."   # gate (optional; open when unset)
"""
import json
import os

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="WVB Pricer", page_icon="🏐", layout="wide")

import app_config
import bet_log
import kelly
import paste_odds
from vbstats import model

HERE = os.path.dirname(os.path.abspath(__file__))
CONSERVATIVE_Q = 20  # percentile of the posterior used for staking


# ------------------------------------------------------------------ auth gate
def gate():
    try:
        pw = st.secrets.get("APP_PASSWORD")
    except Exception:  # no secrets.toml configured (local use)
        pw = None
    if not pw:
        return True
    if st.session_state.get("authed"):
        return True
    with st.form("login"):
        guess = st.text_input("Password", type="password")
        if st.form_submit_button("Enter") and guess == pw:
            st.session_state.authed = True
            st.rerun()
    return False


if not gate():
    st.stop()


# ------------------------------------------------------------------ data
@st.cache_data
def load_ratings():
    return pd.read_parquet(f"{HERE}/app_data/elo_current.parquet")


@st.cache_data
def load_results():
    df = pd.read_parquet(f"{HERE}/app_data/results_current.parquet")
    df["date"] = (pd.to_datetime(df.start_epoch, unit="s", utc=True)
                  .dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d"))
    return df


@st.cache_data
def load_model():
    blob = json.load(open(f"{HERE}/app_data/model_params.json"))
    params = np.array(blob["params"])
    cov = np.array(blob["cov"])
    rng = np.random.default_rng(7)
    draws = rng.multivariate_normal(params, cov, size=500)
    return params, draws


ratings = load_ratings()
params, param_draws = load_model()

cfg = app_config.load()
if "sheet_synced" not in st.session_state:
    try:
        cfg = app_config.refresh_from_sheet()
    except Exception as _e:
        st.sidebar.warning(f"Google Sheet sync failed, using saved values ({_e})")
    st.session_state.sheet_synced = True

st.title("🏐 Women's College Volleyball — Set-Score Pricer")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Bankroll & Kelly")
    c1, c2 = st.columns(2)
    bankroll = c1.number_input("Bankroll", value=float(cfg["bankroll"]), step=50.0)
    kfrac = c2.number_input("Kelly fraction", value=float(cfg["kelly_fraction"]),
                            step=0.05)
    c3, c4 = st.columns(2)
    edge_cap = c3.number_input("Edge cap", value=float(cfg["edge_cap"]), step=0.01)
    value_req = c4.number_input(
        "Min edge", value=float(cfg["value_req"]), step=0.005, format="%.3f",
        help="Minimum edge = your probability minus the VIG-INCLUDED implied "
             "probability of the odds you're taking (-110 implies 52.4%, not "
             "50%). Synced with the sheet's value_req column.")
    if st.button("↻ Refresh from Google Sheet"):
        cfg = app_config.refresh_from_sheet()
        st.rerun()
    app_config.update(bankroll=bankroll, kelly_fraction=kfrac,
                      edge_cap=edge_cap, value_req=value_req)

    st.header("Staking basis")
    conservative = st.checkbox(
        f"Conservative (p{CONSERVATIVE_Q} of posterior)", value=True,
        help="Gate and size bets off the low end of the model's parameter "
             "uncertainty instead of the point estimate.")


# ------------------------------------------------------------------ helpers
def away_first(df):
    """Reorder columns so away_team displays before home_team."""
    cols = list(df.columns)
    if "home_team" in cols and "away_team" in cols:
        cols.insert(cols.index("home_team"), cols.pop(cols.index("away_team")))
    return df[cols]


def overall_rating(df):
    """Regression-weighted overall rating on the Elo scale.

    The set-win model is matchup-separable: a team contributes
    b_serve*(serve+conf) + b_receive*(receive+conf) to the logit, so the
    weighted average of the two Elo components (weights = fitted betas) IS
    the model's own one-number team strength, conference anchor included.
    """
    b_serve, b_receive = params[1], params[2]
    w = b_serve + b_receive
    return (b_serve * (df.serve_elo + df.conf_elo)
            + b_receive * (df.receive_elo + df.conf_elo)) / w


tab_price, tab_best, tab_rank, tab_results, tab_log = st.tabs(
    ["Price a match", "Best bets", "Rankings", "Results", "Bet log"])

# ================================================================== pricing
with tab_price:
    st.subheader("Matchup")
    team_opts = ratings.team.tolist()

    def team_label(seo):
        r = ratings[ratings.team == seo].iloc[0]
        return f"{seo}  ({r.conf}, {int(r.games)} gms)"

    mc = st.columns([3, 3, 2])
    away_team = mc[0].selectbox("Away team (listed first at the book)",
                                team_opts, index=None, format_func=team_label,
                                placeholder="Choose away team…")
    home_team = mc[1].selectbox("Home team", team_opts, index=None,
                                format_func=team_label,
                                placeholder="Choose home team…")
    venue_mode = mc[2].selectbox(
        "Venue", ["Home court", "Neutral (host/label matters)",
                  "True toss-up (symmetrized)"],
        help="Home court: normal. Neutral: venue isn't the home team's, but "
             "the home label still carries its usual edge (hosts/stronger "
             "seeds get it — the data says this holds at most flagged-neutral "
             "sites). True toss-up: the label is arbitrary (e.g. Final Four) "
             "— prices are averaged over both label orientations, which "
             "cancels the label effect but keeps the strength difference.")
    neutral = venue_mode != "Home court"
    tossup = venue_mode.startswith("True toss-up")

    if home_team and away_team and home_team != away_team:
        h = ratings[ratings.team == home_team].iloc[0]
        a = ratings[ratings.team == away_team].iloc[0]
        for r in (h, a):
            if r.games < 5:
                st.warning(f"{r.team} has only {int(r.games)} rated games this "
                           f"season — rating still leans on last season's "
                           f"carryover.")

        df = pd.DataFrame([{
            "home_serve_elo": h.serve_elo, "home_receive_elo": h.receive_elo,
            "home_conf_elo": h.conf_elo,
            "away_serve_elo": a.serve_elo, "away_receive_elo": a.receive_elo,
            "away_conf_elo": a.conf_elo,
            "is_neutral": neutral,
        }])
        X = model.features(df)

        h_overall = float(overall_rating(pd.DataFrame([h])).iloc[0])
        a_overall = float(overall_rating(pd.DataFrame([a])).iloc[0])
        gap = a_overall - h_overall  # away perspective, matches column order
        gap_color = "#09ab3b" if gap >= 0 else "#ff4b4b"

        def _cell(label, value):
            return (f"<div style='min-width:7.5rem'>"
                    f"<div style='font-size:0.7rem;opacity:0.6'>{label}</div>"
                    f"<div style='font-size:1.05rem;font-weight:600'>{value}"
                    f"</div></div>")

        # away team first, mirroring the away-then-home picker order above
        st.markdown(
            "<div style='display:flex;gap:1.4rem;flex-wrap:wrap;"
            "margin:0.25rem 0 0.75rem 0'>"
            + _cell(f"{away_team} overall",
                    f"{a_overall:.0f} <span style='font-size:0.75rem;"
                    f"color:{gap_color}'>{gap:+.0f} vs opp</span>")
            + _cell(f"{away_team} serve / receive",
                    f"{a.serve_elo:.0f} / {a.receive_elo:.0f}")
            + _cell(f"{away_team} conf ({a.conf})", f"{a.conf_elo:+.0f}")
            + _cell(f"{home_team} overall", f"{h_overall:.0f}")
            + _cell(f"{home_team} serve / receive",
                    f"{h.serve_elo:.0f} / {h.receive_elo:.0f}")
            + _cell(f"{home_team} conf ({h.conf})", f"{h.conf_elo:+.0f}")
            + "</div>",
            unsafe_allow_html=True)

        Xf = model.features(pd.DataFrame([{
            "home_serve_elo": a.serve_elo, "home_receive_elo": a.receive_elo,
            "home_conf_elo": a.conf_elo,
            "away_serve_elo": h.serve_elo, "away_receive_elo": h.receive_elo,
            "away_conf_elo": h.conf_elo, "is_neutral": neutral,
        }]))

        def probs6(param_vec):
            """Set-score distribution; toss-up mode averages both label
            orientations (flipped one reversed back to home perspective)."""
            p = model.set_score_probs(X, param_vec)[0]
            if tossup:
                pf = model.set_score_probs(Xf, param_vec)[0]
                p = 0.5 * (p + pf[::-1])
            return p

        probs = probs6(params)[None, :]
        mk_point = {k: v[0] for k, v in model.markets(probs).items()}
        draw_probs = np.stack([probs6(d) for d in param_draws])

        def draw_markets(dp):
            return {
                "home_ml": dp[:, 0] + dp[:, 1] + dp[:, 2],
                "home_minus_1_5": dp[:, 0] + dp[:, 1],
                "home_minus_2_5": dp[:, 0],
                "away_minus_1_5": dp[:, 5] + dp[:, 4],
                "away_minus_2_5": dp[:, 5],
                "under_3_5_sets": dp[:, 0] + dp[:, 5],
                "under_4_5_sets": dp[:, 0] + dp[:, 5] + dp[:, 1] + dp[:, 4],
                "exactly_5_sets": dp[:, 2] + dp[:, 3],
            }

        mk_draws = draw_markets(draw_probs)

        # label, market prob key, complement?, (market, side, point) for the log
        ROWS = [
            (f"{home_team} ML", "home_ml", False, ("ml", "home", "")),
            (f"{away_team} ML", "home_ml", True, ("ml", "away", "")),
            (f"{home_team} -1.5 sets", "home_minus_1_5", False, ("spread", "home", -1.5)),
            (f"{away_team} +1.5 sets", "home_minus_1_5", True, ("spread", "away", 1.5)),
            (f"{home_team} -2.5 sets", "home_minus_2_5", False, ("spread", "home", -2.5)),
            (f"{away_team} +2.5 sets", "home_minus_2_5", True, ("spread", "away", 2.5)),
            (f"{away_team} -1.5 sets", "away_minus_1_5", False, ("spread", "away", -1.5)),
            (f"{home_team} +1.5 sets", "away_minus_1_5", True, ("spread", "home", 1.5)),
            (f"{away_team} -2.5 sets", "away_minus_2_5", False, ("spread", "away", -2.5)),
            (f"{home_team} +2.5 sets", "away_minus_2_5", True, ("spread", "home", 2.5)),
            ("Under 3.5 sets", "under_3_5_sets", False, ("total", "under", 3.5)),
            ("Over 3.5 sets", "under_3_5_sets", True, ("total", "over", 3.5)),
            ("Under 4.5 sets", "under_4_5_sets", False, ("total", "under", 4.5)),
            ("Over 4.5 sets", "under_4_5_sets", True, ("total", "over", 4.5)),
            ("Match goes 5 (yes)", "exactly_5_sets", False, ("five", "yes", "")),
            ("Match goes 5 (no)", "exactly_5_sets", True, ("five", "no", "")),
        ]

        rows = []
        for label, key, complement, (market_, side_, point_) in ROWS:
            p = 1 - mk_point[key] if complement else mk_point[key]
            d = 1 - mk_draws[key] if complement else mk_draws[key]
            p_lo = float(np.percentile(d, CONSERVATIVE_Q))
            p_basis = p_lo if conservative else p  # same basis as the Kelly gate
            rows.append({
                "outcome": label,
                "prob": round(p, 4),
                f"prob_p{CONSERVATIVE_Q}": round(p_lo, 4),
                "fair_odds": kelly.prob_to_american(p),
                "min_edge_odds": kelly.prob_to_american(p_basis - value_req)
                if p_basis - value_req > 0 else None,
                "market": market_, "side": side_, "point": point_,
            })
        board = pd.DataFrame(rows)

        st.subheader("Set-score distribution")
        dist = pd.DataFrame({
            "score": [f"{hc}-{ac}" for hc, ac in model.OUTCOMES],
            "prob": (probs[0] * 100).round(1),
        })
        st.dataframe(dist.set_index("score").T, width="stretch")

        st.subheader("Fair prices")
        basis_note = (f"the conservative p{CONSERVATIVE_Q} probability"
                      if conservative else "the model probability")
        st.caption("fair_odds = zero-edge price (its raw implied equals the "
                   "model probability — the vig you eat is already in this "
                   "comparison). min_edge_odds = the WORST book price that "
                   f"still clears your min edge, computed from {basis_note} "
                   "(matches the Kelly gate below); bet only at that number "
                   "or better.")
        st.dataframe(board.drop(columns=["market", "side", "point"]),
                     width="stretch", height=600)

        st.subheader("Kelly stake")
        kc = st.columns(3)
        pick = kc[0].selectbox("Outcome", board.outcome.tolist())
        book_odds = kc[1].number_input("Book odds", value=-110, step=5)
        row = board[board.outcome == pick].iloc[0]
        p_stake = (row[f"prob_p{CONSERVATIVE_Q}"] if conservative
                   else row["prob"])
        implied = kelly.american_to_prob(book_odds)
        edge = p_stake - implied
        edge_point = row["prob"] - implied
        stake = (kelly.kelly_stake(bankroll, kfrac, book_odds, p_stake, edge_cap)
                 if edge >= value_req else 0.0)
        basis = f"p{CONSERVATIVE_Q}" if conservative else "point"
        kc[2].metric("Stake", f"${stake:,.2f}", delta=f"edge {edge:+.1%} ({basis})",
                     help=f"Gated and sized on the {basis} probability "
                          f"{p_stake:.1%} vs vig-included implied {implied:.1%}."
                          f" $0 means that edge < min edge ({value_req:.1%}).")
        st.caption(f"Point-estimate edge {edge_point:+.1%} | "
                   f"conservative p{CONSERVATIVE_Q} edge "
                   f"{row[f'prob_p{CONSERVATIVE_Q}'] - implied:+.1%} — the "
                   f"'{basis}' one is what gates and sizes the bet.")

        lg = st.columns([2, 2, 2, 2])
        game_date = lg[0].date_input("Game date", value=pd.Timestamp.now(
            tz="America/New_York").date(), key="log_date")
        book = lg[1].text_input("Book", value=cfg.get("last_book", "betonline"),
                                key="log_book")
        stake_actual = lg[2].number_input("Stake placed ($)",
                                          value=float(stake), step=1.0,
                                          key="log_stake")
        if lg[3].button("Log this bet", type="primary",
                        help="Appends to the Vball_Bet_Log worksheet of the "
                             "Constants Google Sheet."):
            rec = dict(
                logged_at=pd.Timestamp.now(tz="America/New_York")
                .strftime("%Y-%m-%d %H:%M"),
                game_date=str(game_date),
                matchup=f"{away_team} @ {home_team}",
                home_team=home_team, away_team=away_team,
                bet=pick, market=row["market"], side=row["side"],
                point=row["point"], book=book, odds=book_odds,
                stake=stake_actual, edge=round(edge, 4),
                model_prob=row["prob"], model_fair=row["fair_odds"],
                status="pending", profit="", graded_at="")
            try:
                bet_log.log_bets([rec])
                app_config.update(last_book=book)
                st.success(f"Logged: {pick} @ {book_odds} ({book}) "
                           f"for ${stake_actual:,.2f}")
            except Exception as e:
                st.error(f"Logging failed: {e}")

        with st.expander("Flip check (price as if the other team were 'home')"):
            Xf = model.features(pd.DataFrame([{
                "home_serve_elo": a.serve_elo,
                "home_receive_elo": a.receive_elo, "home_conf_elo": a.conf_elo,
                "away_serve_elo": h.serve_elo,
                "away_receive_elo": h.receive_elo, "away_conf_elo": h.conf_elo,
                "is_neutral": neutral,
            }]))
            pf = model.set_score_probs(Xf, params)
            ml_flip = 1 - model.markets(pf)["home_ml"][0]
            st.write(f"{home_team} ML priced normally: "
                     f"**{mk_point['home_ml']:.1%}** — with labels flipped: "
                     f"**{ml_flip:.1%}**. The 'True toss-up' venue option "
                     f"prices at the average of the two.")
    else:
        st.info("Pick two different teams to price the match.")

# ================================================================== best bets
with tab_best:
    st.subheader("Best bets from a pasted board")
    st.caption(
        "Open the book's NCAA W volleyball page, select all (Cmd+A), copy, "
        "and paste below. Away team is assumed to be listed first in each "
        "game. Every parsed market is priced with the model; bets are gated "
        "and sized exactly like the pricing tab (same staking basis, min "
        "edge, and edge cap).")
    with st.expander("How to copy the board (bookmarklet — one-time setup)"):
        st.markdown(
            "BetOnline's odds buttons are excluded from normal select-all "
            "copy, so use this instead:\n\n"
            "1. Create a bookmark in your browser; name it `Copy board` and "
            "paste this as the URL:\n"
            "```\n"
            "javascript:(async()=>{await navigator.clipboard.writeText("
            "document.body.innerText);alert('Board copied to clipboard');})()"
            "\n```\n"
            "2. Open the book's NCAA W volleyball page, click the `Copy "
            "board` bookmark, then paste below.\n\n"
            "Alternative (no bookmark): open DevTools Console on the page "
            "(Cmd+Opt+J) and run `copy(document.body.innerText)`.")
    paste = st.text_area("Pasted board", height=200,
                         placeholder="Paste the sportsbook page text here…")
    venue_b = st.selectbox(
        "Venue for ALL games on this slate", ["Home court",
        "Neutral (host/label matters)", "True toss-up (symmetrized)"],
        key="best_venue",
        help="Applied to every parsed game on the next Parse & evaluate. "
             "Home court is right for normal slates; use toss-up for "
             "tournament days where the book's home label is arbitrary.")
    neutral_b = venue_b != "Home court"
    tossup_b = venue_b.startswith("True toss-up")
    @st.cache_data(ttl=3600, show_spinner="Looking up venues on the NCAA "
                                          "schedule…")
    def cached_venues(pairs_tuple):
        from vbstats.venues import slate_venues
        try:
            hv = pd.read_parquet(f"{HERE}/app_data/home_venues.parquet")
            hv_map = dict(zip(hv.team, hv.home_venue))
        except Exception:
            hv_map = {}
        try:
            return slate_venues(list(pairs_tuple), hv_map)
        except Exception:
            return {}

    if st.button("Parse & evaluate", type="primary") and paste.strip():
        games, unparsed, n_oddsless = paste_odds.parse_board(paste)
        matched_pairs = []
        for g in games:
            hm_, _ = paste_odds.match_team(g["home"], ratings.team.tolist())
            am_, _ = paste_odds.match_team(g["away"], ratings.team.tolist())
            if hm_ and am_:
                matched_pairs.append((am_, hm_))
        venue_info = cached_venues(tuple(sorted(matched_pairs)))
        if not games and n_oddsless >= 2:
            st.error(
                f"Found ~{n_oddsless // 2} games but NO odds in the paste — "
                "BetOnline's odds buttons don't survive select-all copy. "
                "Use the bookmarklet in the instructions expander below, "
                "then paste what it puts on your clipboard.")
        seos = ratings.team.tolist()
        card_rows, unmatched = [], []
        for g in games:
            h_match, hs = paste_odds.match_team(g["home"], seos)
            a_match, as_ = paste_odds.match_team(g["away"], seos)
            if not h_match or not a_match:
                unmatched.append(f"{g['away']} @ {g['home']} "
                                 f"(match scores {as_:.2f}/{hs:.2f})")
                continue
            h = ratings[ratings.team == h_match].iloc[0]
            a = ratings[ratings.team == a_match].iloc[0]
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
            for mkt in g["markets"]:
                p = paste_odds.price_market(probs_pt, mkt["market"],
                                            mkt["side"], mkt["point"])
                if p is None:
                    continue
                p_draws = np.array([
                    paste_odds.price_market(dp, mkt["market"], mkt["side"],
                                            mkt["point"]) for dp in draws_g])
                p_lo = float(np.percentile(p_draws, CONSERVATIVE_Q))
                p_basis = p_lo if conservative else p
                implied = kelly.american_to_prob(mkt["odds"])
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
                vi = venue_info.get((a_match, h_match), {})
                card_rows.append({
                    "game_#": g.get("board_pos"),
                    "time": g.get("time", ""),
                    "matchup": f"{a_match} @ {h_match}",
                    "site": vi.get("site", ""),
                    "venue": vi.get("venue", ""),
                    "bet": bet_label_, "odds": mkt["odds"],
                    "model_prob": round(p, 4),
                    f"p{CONSERVATIVE_Q}": round(p_lo, 4),
                    "edge": round(edge, 4), "stake": stake_,
                    "fair_odds": kelly.prob_to_american(p),
                    "market": mkt["market"], "side": mkt["side"],
                    "point": mkt["point"],
                    "away_team": a_match, "home_team": h_match,
                })
        st.session_state.best_card = pd.DataFrame(card_rows)
        st.session_state.best_unmatched = unmatched
        st.session_state.best_unparsed = unparsed
        st.session_state.best_n_games = len(games)

    if "best_card" in st.session_state:
        card = st.session_state.best_card
        st.caption(f"{st.session_state.best_n_games} games parsed, "
                   f"{len(card)} markets priced.")
        if st.session_state.best_unmatched:
            st.warning("Could not match teams for: "
                       + "; ".join(st.session_state.best_unmatched))
        if len(card):
            sort_by = st.radio("Order card by", ["edge", "game order"],
                               horizontal=True, key="best_sort")
            bets = card[card.stake > 0]
            bets = (bets.sort_values("edge", ascending=False)
                    if sort_by == "edge"
                    else bets.sort_values(["game_#", "edge"],
                                          ascending=[True, False]))
            if len(bets):
                st.success(f"{len(bets)} qualifying bets | total stake "
                           f"${bets.stake.sum():,.2f}")
                show_cols = ["game_#", "time", "matchup", "site", "venue",
                             "bet", "odds", "model_prob",
                             f"p{CONSERVATIVE_Q}", "edge", "stake",
                             "fair_odds"]
                bets_show = bets[show_cols].reset_index(drop=True)
                bets_show.insert(0, "log", False)
                edited = st.data_editor(
                    bets_show, width="stretch", key="best_editor",
                    disabled=[c for c in bets_show.columns if c != "log"])
                bc = st.columns([2, 2, 2, 2])
                book_b = bc[0].text_input("Book", value=cfg.get(
                    "last_book", "betonline"), key="best_book")
                paper_date = bc[2].date_input(
                    "Game date (for tracking)",
                    value=pd.Timestamp.now(tz="America/New_York").date(),
                    key="paper_date")
                if bc[3].button("📋 Track full card (paper)",
                                help="Logs EVERY qualifying bet to the "
                                     "Vball_Paper_Log worksheet so model "
                                     "performance is tracked even for bets "
                                     "you don't place. Re-pasting the same "
                                     "slate won't double-log."):
                    now = pd.Timestamp.now(tz="America/New_York")
                    recs = [dict(
                        logged_at=now.strftime("%Y-%m-%d %H:%M"),
                        game_date=str(paper_date),
                        matchup=r.matchup, home_team=r.home_team,
                        away_team=r.away_team, bet=r.bet,
                        market=r.market, side=r.side, point=r.point,
                        book=book_b, odds=r.odds, stake=r.stake,
                        edge=r.edge, model_prob=r.model_prob,
                        model_fair=r.fair_odds, status="pending",
                        profit="", graded_at="")
                        for r in bets.itertuples()]
                    try:
                        n_ = bet_log.log_bets(
                            recs, worksheet=bet_log.PAPER_WORKSHEET,
                            dedupe=True)
                        st.success(f"Tracking {n_} new paper bets "
                                   f"({len(recs) - n_} already tracked).")
                    except Exception as e:
                        st.error(f"Paper logging failed: {e}")
                if bc[1].button("Log selected bets", type="primary",
                                key="best_log"):
                    picks = bets.reset_index(drop=True)[edited["log"].values]
                    if not len(picks):
                        st.warning("Tick 'log' on the bets you placed.")
                    else:
                        now = pd.Timestamp.now(tz="America/New_York")
                        recs = [dict(
                            logged_at=now.strftime("%Y-%m-%d %H:%M"),
                            game_date=now.strftime("%Y-%m-%d"),
                            matchup=r.matchup, home_team=r.home_team,
                            away_team=r.away_team, bet=r.bet,
                            market=r.market, side=r.side, point=r.point,
                            book=book_b, odds=r.odds, stake=r.stake,
                            edge=r.edge, model_prob=r.model_prob,
                            model_fair=r.fair_odds, status="pending",
                            profit="", graded_at="")
                            for r in picks.itertuples()]
                        try:
                            n_ = bet_log.log_bets(recs)
                            app_config.update(last_book=book_b)
                            st.success(f"Logged {n_} bets.")
                        except Exception as e:
                            st.error(f"Logging failed: {e}")
            else:
                st.info("No bets clear the min-edge gate — that's the normal "
                        "result most days.")
            with st.expander("All priced markets"):
                st.dataframe(card.sort_values("edge", ascending=False),
                             width="stretch", height=400)
        if st.session_state.best_unparsed:
            with st.expander(
                    f"Unparsed tokens ({len(st.session_state.best_unparsed)})"):
                st.write(st.session_state.best_unparsed[:100])

# ================================================================== rankings
with tab_rank:
    st.subheader("Team rankings")
    st.caption("overall = regression-weighted blend of serve and receive Elo "
               "with the conference anchor included "
               f"(weights from the fitted model: serve {params[1]:.2f}, "
               f"receive {params[2]:.2f} per 100 Elo). Click any column "
               "header to sort.")
    rk = ratings.copy()
    rk["overall"] = overall_rating(rk).round(1)
    rk = rk.sort_values("overall", ascending=False).reset_index(drop=True)
    rk.insert(0, "rank", rk.index + 1)

    fc = st.columns([3, 3, 2])
    search = fc[0].text_input("Search team", "")
    conf_pick = fc[1].multiselect("Conference", sorted(rk.conf.dropna().unique()))
    min_games = fc[2].number_input("Min games", value=0, step=1)

    view = rk
    if search:
        view = view[view.team.str.contains(search, case=False, na=False)]
    if conf_pick:
        view = view[view.conf.isin(conf_pick)]
    if min_games:
        view = view[view.games >= min_games]

    st.dataframe(
        view[["rank", "team", "conf", "overall", "serve_elo", "receive_elo",
              "conf_elo", "games"]].round(
            {"serve_elo": 1, "receive_elo": 1, "conf_elo": 1}),
        width="stretch", height=600, hide_index=True)

# ================================================================== results
with tab_results:
    results = load_results()
    st.caption(f"{len(results)} games this season, through "
               f"{results.date.max() if len(results) else '—'}")

    rf = st.columns([3, 3, 2])
    team_f = rf[0].text_input("Filter by team", "")
    conf_f = rf[1].multiselect(
        "Conference",
        sorted(pd.concat([results.home_conf, results.away_conf])
               .dropna().unique()),
        key="results_conf")
    view = results
    if team_f:
        view = view[view.home_seo.str.contains(team_f, case=False, na=False)
                    | view.away_seo.str.contains(team_f, case=False, na=False)]
    if conf_f:
        view = view[view.home_conf.isin(conf_f) | view.away_conf.isin(conf_f)]

    show = view.sort_values("start_epoch", ascending=False)[[
        "date", "away_seo", "away_sets", "home_seo", "home_sets",
        "venue", "home_conf", "away_conf", "is_championship"]]
    show.columns = ["date", "away", "away sets", "home", "home sets",
                    "venue", "home conf", "away conf", "champ"]
    st.dataframe(show, width="stretch", height=600, hide_index=True)

# ================================================================== bet log
with tab_log:
    st.subheader("Bet log")
    lc = st.columns([2, 2, 4])
    if lc[0].button("↻ Refresh log"):
        st.session_state.pop("bet_log_df", None)
    if lc[1].button("Grade pending bets", type="primary",
                    help="Settles pending bets in BOTH logs (real + paper) "
                         "against the results table."):
        try:
            with st.spinner("Grading…"):
                n1, msg1 = bet_log.grade_pending(load_results())
                n2, msg2 = bet_log.grade_pending(
                    load_results(), worksheet=bet_log.PAPER_WORKSHEET)
            st.success(f"real: {msg1} | paper: {msg2}")
            st.session_state.pop("bet_log_df", None)
            st.session_state.pop("paper_log_df", None)
        except Exception as e:
            st.error(f"Grading failed: {e}")

    if "bet_log_df" not in st.session_state:
        try:
            st.session_state.bet_log_df = bet_log.read_log()
        except Exception as e:
            st.error(f"Could not read the bet log: {e}")
            st.session_state.bet_log_df = pd.DataFrame()
    log_df = st.session_state.bet_log_df

    if len(log_df):
        settled = log_df[log_df.status.isin(["won", "lost", "push"])]
        profit = pd.to_numeric(settled.profit, errors="coerce").sum() \
            if len(settled) else 0.0
        staked = pd.to_numeric(settled.stake, errors="coerce").sum() \
            if len(settled) else 0.0
        mcols = st.columns(4)
        mcols[0].metric("Bets logged", len(log_df))
        mcols[1].metric("Record", f"{(settled.status == 'won').sum()}-"
                                  f"{(settled.status == 'lost').sum()}-"
                                  f"{(settled.status == 'push').sum()}")
        mcols[2].metric("Profit", f"${profit:,.2f}")
        mcols[3].metric("ROI", f"{profit / staked:+.1%}" if staked else "—")
        st.dataframe(away_first(log_df).iloc[::-1], width="stretch",
                     height=500, hide_index=True)
    else:
        st.info("No bets logged yet — log one from the pricing tab.")

    st.subheader("Paper-trade tracker (model performance)")
    st.caption("Every qualifying bet from Best bets cards you chose to "
               "track — placed or not. This is the model's honest scoreboard.")
    if "paper_log_df" not in st.session_state:
        try:
            st.session_state.paper_log_df = bet_log.read_log(
                worksheet=bet_log.PAPER_WORKSHEET)
        except Exception as e:
            st.error(f"Could not read the paper log: {e}")
            st.session_state.paper_log_df = pd.DataFrame()
    paper = st.session_state.paper_log_df

    if len(paper):
        settled = paper[paper.status.isin(["won", "lost", "push"])]
        profit = pd.to_numeric(settled.profit, errors="coerce").sum() \
            if len(settled) else 0.0
        staked = pd.to_numeric(settled.stake, errors="coerce").sum() \
            if len(settled) else 0.0
        pc = st.columns(4)
        pc[0].metric("Tracked bets", len(paper))
        pc[1].metric("Record", f"{(settled.status == 'won').sum()}-"
                               f"{(settled.status == 'lost').sum()}-"
                               f"{(settled.status == 'push').sum()}")
        pc[2].metric("Paper profit", f"${profit:,.2f}")
        pc[3].metric("Paper ROI", f"{profit / staked:+.1%}" if staked else "—")
        if len(settled) >= 10:
            g = settled.copy()
            g["edge_bucket"] = pd.cut(
                pd.to_numeric(g.edge, errors="coerce"),
                [0, 0.03, 0.06, 0.10, 1.0],
                labels=["2-3%", "3-6%", "6-10%", "10%+"])
            by = g.groupby("edge_bucket", observed=True).apply(
                lambda d: pd.Series({
                    "n": len(d),
                    "win%": (d.status == "won").mean(),
                    "roi": pd.to_numeric(d.profit, errors="coerce").sum()
                    / max(pd.to_numeric(d.stake, errors="coerce").sum(), 1e-9),
                }), include_groups=False)
            st.caption("ROI by claimed edge — if the model is honest, bigger "
                       "claimed edges should earn more:")
            st.dataframe(by.round(3), width="stretch")
        st.dataframe(away_first(paper).iloc[::-1], width="stretch", height=400)
    else:
        st.info("Nothing tracked yet — use '📋 Track full card (paper)' on "
                "the Best bets tab after parsing a slate.")
