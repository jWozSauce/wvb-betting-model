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
import json
from pathlib import Path

import pandas as pd
import repair_flags

WORKSHEET = "Vball_Bet_Log"
PAPER_WORKSHEET = "Vball_Paper_Log"  # model-tracking: every qualifying bet
LOCAL_KEY = ("/Volumes/Samsung T7/.CloudStorage/Data/Dropbox/Annual_Sports_Main/"
             "NBA_Folder/Claude_Pregame_NBA_Quarters/"
             "dogwood-keep-395516-c4b3e7bd811c.json")
SCOPES = ["https://spreadsheets.google.com/feeds",
          "https://www.googleapis.com/auth/drive"]

HEADER = ["logged_at", "game_date", "matchup", "home_team", "away_team",
          "bet", "market", "side", "point", "book", "odds", "stake",
          "edge", "model_prob", "model_fair", "status", "profit", "graded_at",
          "mkt_prob", "blend_prob", "venue_mode",
          # full pricing context per bet (added 2026-09-23)
          "w_model", "basis", "min_edge", "kelly_frac", "edge_cap",
          "bankroll", "price_model",
          # scheduled start time when known (added 2026-09-26) — new columns
          # must always be APPENDED so historical column indices don't shift
          "game_time"]


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
        ws = ss.worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=worksheet, rows=2000, cols=len(HEADER))
        ws.update([HEADER], "A1")
        return ws
    # schema migration: when the code grows new (appended) columns, widen
    # the grid and rewrite the header so get_all_records keys line up
    if ws.col_count < len(HEADER):
        ws.resize(cols=len(HEADER))
    if len(ws.row_values(1)) < len(HEADER):
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


def _find_result_legacy(results, home, away, date):
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


def _find_result_safe(results, home, away, date):
    """Rank both orientations by calendar date; refuse equally close fixtures."""
    direct = (results.home_seo == home) & (results.away_seo == away)
    reverse = (results.home_seo == away) & (results.away_seo == home)
    hit = results[direct | reverse].copy()
    if hit.empty:
        return None, False
    try:
        day = pd.Timestamp(date).normalize()
        distance = (pd.to_datetime(hit.date).dt.normalize() - day).abs().dt.days
    except (ValueError, TypeError):
        return None, False
    hit = hit.assign(_distance=distance)
    hit = hit[hit._distance <= 1]
    if hit.empty:
        return None, False
    nearest = hit[hit._distance == hit._distance.min()]
    if len(nearest) != 1:
        return None, False
    row = nearest.iloc[0].drop(labels=['_distance'])
    return row, bool(row.home_seo == away and row.away_seo == home)


def _find_result(results, home, away, date):
    finder = _find_result_safe if repair_flags.enabled() else _find_result_legacy
    return finder(results, home, away, date)


def _game_start_et(game_date, game_time):
    if game_date in (None, "") or game_time in (None, ""):
        return None
    text = str(game_time).strip()
    if not text or text.upper() in {"TBA", "TBD"}:
        return None
    try:
        return pd.Timestamp(f"{game_date} {text}", tz="America/New_York")
    except (ValueError, TypeError):
        try:
            parsed = pd.to_datetime(f"{game_date} {text}")
        except (ValueError, TypeError):
            return None
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed).tz_localize("America/New_York")


def _result_day(result):
    try:
        return pd.Timestamp(result.date).normalize()
    except (AttributeError, ValueError, TypeError):
        return None


def _same_pair(home, away, row_home, row_away):
    return ((str(row_home) == str(home) and str(row_away) == str(away)) or
            (str(row_home) == str(away) and str(row_away) == str(home)))


def _raw_schedule_pairs_for_date(day):
    try:
        date = pd.Timestamp(day).date()
    except (ValueError, TypeError):
        return set()
    path = Path(__file__).resolve().parent / "data" / "raw" / str(date.year) / "contests" / f"{date}.json"
    if not path.exists():
        return set()
    try:
        contests = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return set()
    pairs = set()
    for contest in contests:
        teams = contest.get("teams") or []
        home = next((t.get("seoname") for t in teams if t.get("isHome") is True), None)
        away = next((t.get("seoname") for t in teams if t.get("isHome") is False), None)
        if home and away:
            pairs.add((str(date), str(home), str(away)))
    return pairs


def _same_day_fixture_exists(results, home, away, date, schedule_pairs=None):
    try:
        day = pd.Timestamp(date).normalize()
    except (ValueError, TypeError):
        return False
    if "date" in results.columns and not results.empty:
        dates = pd.to_datetime(results.date, errors="coerce").dt.normalize()
        same_day = results[dates == day]
        for row in same_day.itertuples():
            if _same_pair(home, away, row.home_seo, row.away_seo):
                return True
    pairs = set(schedule_pairs or ()) | _raw_schedule_pairs_for_date(day)
    date_key = str(day.date())
    return ((date_key, str(home), str(away)) in pairs or
            (date_key, str(away), str(home)) in pairs)


def _date_slop_allowed(results, result, home, away, date, schedule_pairs=None):
    result_day = _result_day(result)
    try:
        bet_day = pd.Timestamp(date).normalize()
    except (ValueError, TypeError):
        return False
    if result_day is None:
        return False
    if result_day == bet_day:
        return True
    return not _same_day_fixture_exists(results, home, away, date, schedule_pairs)


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


def grade_pending(results: pd.DataFrame, worksheet=WORKSHEET, now=None, schedule_pairs=None):
    """Grade pending bets against the results table. Returns (n, message)."""
    ws = _ws(worksheet)
    recs = ws.get_all_records()
    if not recs:
        return 0, "log is empty"
    now_ts = now if now is not None else pd.Timestamp.now(tz="America/New_York")
    now_ts = pd.Timestamp(now_ts)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("America/New_York")
    else:
        now_ts = now_ts.tz_convert("America/New_York")
    graded_at = now_ts.strftime("%Y-%m-%d %H:%M")
    updates, graded = [], 0
    for i, r in enumerate(recs):
        status = str(r.get("status", "")).lower()
        # grade pending rows, and repair rows a past partial write left with
        # a settled status but no profit
        half_written = (status in ("won", "lost", "push")
                        and str(r.get("profit", "")).strip() == "")
        if status != "pending" and not half_written:
            continue
        start = _game_start_et(r.get("game_date"), r.get("game_time"))
        if start is not None and now_ts < start:
            continue
        g, flipped = _find_result(results, r["home_team"], r["away_team"],
                                  str(r["game_date"]))
        if g is None:
            continue
        if not _date_slop_allowed(results, g, r["home_team"], r["away_team"],
                                  str(r["game_date"]), schedule_pairs):
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
        updates.append((i + 2, status, round(profit, 2), graded_at))
        graded += 1
    if updates:
        # single batched write — per-cell writes trip the Sheets API's
        # 60-writes/minute quota on any decent-sized card
        from gspread.utils import rowcol_to_a1
        c = HEADER.index("status") + 1
        data = [{"range": f"{rowcol_to_a1(rix, c)}:{rowcol_to_a1(rix, c + 2)}",
                 "values": [[status, profit, ts]]}
                for rix, status, profit, ts in updates]
        ws.batch_update(data, value_input_option="USER_ENTERED")
    return graded, f"graded {graded} pending bets"
