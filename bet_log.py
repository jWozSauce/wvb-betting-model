"""Bet log on Google Sheets (gspread + service account) with auto-grading.

Mirrors NCAAF Python_Asshole_Algo/bet_log.py: worksheet Vball_Bet_Log in the
same Constants spreadsheet the bankroll uses. Grading uses the app's own
results table (app_data/results_current.parquet), so it needs no extra API —
grade after the nightly ratings update has pulled the finals.

Credentials: st.secrets["gcp_service_account"] (service-account JSON pasted
into Streamlit secrets) or the shared local key file on the Mac. The
spreadsheet must be shared (Editor) with the service-account email.

Market encoding (columns market / side / point):
  ml     side=home|away             point empty
  spread side=home|away             point = picked team's spread (e.g. -1.5)
  total  side=over|under            point = total-sets line (e.g. 4.5)
  five   side=yes|no                point empty (match goes 5 sets)
"""
import os

import pandas as pd

WORKSHEET = "Vball_Bet_Log"
PAPER_WORKSHEET = "Vball_Paper_Log"  # model-tracking: every qualifying bet
LOCAL_KEY = ("/Volumes/Samsung T7/.CloudStorage/Data/Dropbox/Annual_Sports_Main/"
             "NBA_Folder/Claude_Pregame_NBA_Quarters/"
             "dogwood-keep-395516-c4b3e7bd811c.json")
SCOPES = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]

HEADER = ["logged_at", "game_date", "matchup", "home_team", "away_team",
          "bet", "market", "side", "point", "book", "odds", "stake",
          "edge", "model_prob", "model_fair", "status", "profit", "graded_at"]


def _client():
    import gspread
    from google.oauth2.service_account import Credentials
    info = None
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
    except Exception:
        pass
    if info is not None:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif os.path.exists(LOCAL_KEY):
        creds = Credentials.from_service_account_file(LOCAL_KEY, scopes=SCOPES)
    else:
        raise RuntimeError(
            "No Google credentials: add [gcp_service_account] to Streamlit "
            "secrets (service-account JSON) or keep the local key file.")
    return gspread.authorize(creds)


def _ws(worksheet=WORKSHEET):
    import gspread
    from app_config import _sheet_id
    ss = _client().open_by_key(_sheet_id())
    try:
        return ss.worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=worksheet, rows=2000, cols=len(HEADER))
        ws.update([HEADER], "A1")
        return ws


def log_bets(rows, worksheet=WORKSHEET, dedupe=False):
    """Append bet dicts (keys from HEADER) to the sheet. With dedupe=True,
    rows whose (game_date, matchup, bet) already exist are skipped — so
    re-pasting the same slate doesn't double-track."""
    ws = _ws(worksheet)
    if dedupe:
        existing = {(str(r.get("game_date")), r.get("matchup"), r.get("bet"))
                    for r in ws.get_all_records()}
        rows = [r for r in rows
                if (str(r.get("game_date")), r.get("matchup"), r.get("bet"))
                not in existing]
    if not rows:
        return 0
    values = [[str(r.get(h, "")) for h in HEADER] for r in rows]
    ws.append_rows(values, value_input_option="USER_ENTERED")
    return len(values)


def read_log(worksheet=WORKSHEET):
    return pd.DataFrame(_ws(worksheet).get_all_records())


def _find_result(results, home, away, date):
    """Result row for this matchup within one day of game_date. Matches the
    fixture in either orientation (bets sometimes get logged with home/away
    swapped); returns (row, flipped) — flipped=True means the bet's
    'home_team' was actually the away team in the result."""
    d0 = pd.Timestamp(date)
    for flipped, (h, a) in ((False, (home, away)), (True, (away, home))):
        hit = results[(results.home_seo == h) & (results.away_seo == a)]
        if not len(hit):
            continue
        hit = hit.assign(dd=(pd.to_datetime(hit.date) - d0).abs().dt.days)
        hit = hit[hit.dd <= 1].sort_values("dd")
        if len(hit):
            return hit.iloc[0], flipped
    return None, False


def _settle(market, side, point, home_sets, away_sets):
    """Returns (won, push)."""
    total = home_sets + away_sets
    if market == "ml":
        return ((home_sets if side == "home" else away_sets) == 3, False)
    if market == "spread":
        margin = (home_sets - away_sets) if side == "home" else (away_sets - home_sets)
        adj = margin + float(point)
        return adj > 0, adj == 0
    if market == "total":
        diff = total - float(point)
        return (diff > 0 if side == "over" else diff < 0), diff == 0
    if market == "five":
        return ((total == 5) if side == "yes" else (total != 5), False)
    raise ValueError(f"unknown market {market!r}")


def grade_pending(results: pd.DataFrame, worksheet=WORKSHEET):
    """Grade pending bets against the results table. Returns (n, message)."""
    ws = _ws(worksheet)
    recs = ws.get_all_records()
    if not recs:
        return 0, "log is empty"
    now = pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d %H:%M")
    updates, graded = [], 0
    for i, r in enumerate(recs):
        if str(r.get("status", "")).lower() != "pending":
            continue
        g, flipped = _find_result(results, r["home_team"], r["away_team"],
                                  str(r["game_date"]))
        if g is None:
            continue
        # sets in the bet's own frame: hs = sets won by the bet's home_team
        hs, as_ = ((int(g.away_sets), int(g.home_sets)) if flipped
                   else (int(g.home_sets), int(g.away_sets)))
        won, push = _settle(str(r["market"]), str(r["side"]).lower(),
                            r["point"], hs, as_)
        odds = float(r["odds"])
        stake = float(r["stake"]) if str(r["stake"]) not in ("", "nan") else 0.0
        profit = 0.0 if push else (
            stake * (odds / 100 if odds > 0 else 100 / -odds) if won else -stake)
        status = "push" if push else ("won" if won else "lost")
        updates.append((i + 2, status, round(profit, 2), now))
        graded += 1
    for row_ix, status, profit, ts in updates:
        c = HEADER.index("status") + 1
        ws.update_cell(row_ix, c, status)
        ws.update_cell(row_ix, c + 1, profit)
        ws.update_cell(row_ix, c + 2, ts)
    return graded, f"graded {graded} pending bets"
