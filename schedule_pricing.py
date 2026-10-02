"""NCAA slate acquisition and classification; no sportsbook or logging calls."""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd
import streamlit as st

from vbstats import model
from vbstats.ncaa import NCAAClient

SOURCE = "NCAA schedule (price everything)"
VENUE_MODES = ("Home court", "Neutral (host/label matters)",
               "True toss-up (symmetrized)")


@st.cache_data(ttl=600, show_spinner=False)
def schedule_response(day, division, _client):
    season = day.year if day.month >= 6 else day.year - 1
    return {"retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "contests": _client.contests(day, season, division)}


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def game_response(contest_id, _client):
    # Keep the raw response in the cache before interpreting its location.
    # Exceptions propagate and are never cached as a successful empty venue.
    return {"retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "game": _client.game(contest_id)}


def partition_schedule(responses, rated_teams):
    """Deduplicate cross-division listings; account for every unique contest."""
    rated_teams = set(rated_teams)
    seen, priced, unpriced = {}, [], []
    raw_count = 0
    for division, response in responses.items():
        for c in response["contests"]:
            raw_count += 1
            cid = str(c.get("contestId") or "")
            if not cid:
                raise ValueError("NCAA contest is missing its contestId; slate not loaded")
            if cid in seen:
                if seen[cid] != c:
                    raise ValueError(f"Conflicting NCAA listings for contest {cid}")
                continue
            seen[cid] = c
            teams = c.get("teams") or []
            homes = [t for t in teams if t.get("isHome") is True]
            aways = [t for t in teams if t.get("isHome") is False]
            valid = len(teams) == 2 and len(homes) == len(aways) == 1
            home = homes[0].get("seoname") if valid else None
            away = aways[0].get("seoname") if valid else None
            row = {"contest_id": cid, "division": division,
                   "home": home, "away": away,
                   "teams": " vs ".join(t.get("nameShort") or t.get("seoname")
                                            or "unknown" for t in teams),
                   "start_epoch": c.get("startTimeEpoch") if c.get("hasStartTime") else None}
            if not valid or not home or not away or home == away:
                row["reason"] = "invalid/missing team or home label"
                unpriced.append(row)
            elif home not in rated_teams or away not in rated_teams:
                missing = [t for t in (away, home) if t not in rated_teams]
                row["reason"] = "unrated team: " + ", ".join(missing)
                unpriced.append(row)
            else:
                priced.append(row)
    key = lambda r: (r["start_epoch"] or float("inf"), r["contest_id"])
    return {"priced": sorted(priced, key=key), "unpriced": sorted(unpriced, key=key),
            "fetched": len(seen), "raw_count": raw_count,
            "duplicates": raw_count - len(seen)}


def classify_venue(row, location, home_venue_map, venue_owner):
    """Use the task's explicit fallbacks; swap labels when away owns the gym."""
    row = dict(row)
    venue = location.get("venue")
    row["venue"] = ", ".join(x for x in (venue, location.get("city"),
                                               location.get("stateUsps")) if x)
    row["ncaa_home"], row["ncaa_away"] = row["home"], row["away"]
    row["host_swapped"] = False
    if not venue:
        row["site"], mode = "venue ?", VENUE_MODES[0]
    elif venue == home_venue_map.get(row["home"]):
        row["site"], mode = "true home", VENUE_MODES[0]
    elif venue == home_venue_map.get(row["away"]):
        row["site"], mode = "AWAY team's gym — host shown as home", VENUE_MODES[0]
        row["home"], row["away"] = row["away"], row["home"]
        row["host_swapped"] = True
    else:
        owner = venue_owner.get(venue)
        row["site"] = f"neutral ({owner}'s gym)" if owner else "neutral (3rd site)"
        mode = VENUE_MODES[2]
    row["venue_mode"] = mode
    return row


def fetch_slate(day, ratings, home_venues, progress=lambda value, text: None):
    """Atomic slate: no partial success on API failure. Cache successful calls."""
    client = NCAAClient()  # Preserve the existing 0.3-second request throttle.
    responses = {}
    for division in (1, 2, 3):
        progress((division - 1) / 10, f"Fetching NCAA Division {division} schedule…")
        responses[division] = schedule_response(day, division, client)
    slate = partition_schedule(responses, ratings.team)
    hv_map = dict(zip(home_venues.team, home_venues.home_venue))
    owners = home_venues.sort_values("n", ascending=False) if "n" in home_venues else home_venues
    owners = owners.drop_duplicates("home_venue")
    owner_map = dict(zip(owners.home_venue, owners.team))
    games = []
    count = len(slate["priced"])
    for index, row in enumerate(slate["priced"]):
        progress(0.3 + 0.7 * index / max(count, 1),
                 f"Venue {index + 1}/{count}: {row['away']} @ {row['home']}")
        response = game_response(row["contest_id"], client)
        location = (response["game"] or {}).get("location") or {}
        games.append(classify_venue(row, location, hv_map, owner_map))
    slate["priced"] = games
    slate["date"] = day.isoformat()
    slate["retrieved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    progress(1.0, f"Loaded {count} rated games; {len(slate['unpriced'])} not priced")
    return slate


def elo_features(home, away, neutral):
    return model.features(pd.DataFrame([{
        "home_serve_elo": home.serve_elo, "home_receive_elo": home.receive_elo,
        "home_conf_elo": home.conf_elo, "away_serve_elo": away.serve_elo,
        "away_receive_elo": away.receive_elo, "away_conf_elo": away.conf_elo,
        "is_neutral": neutral}]))


@st.cache_data(show_spinner=False, max_entries=4096)
def point_price(home_values, away_values, venue_mode, params):
    # Only this game's ratings and venue are cache inputs. Other games retain
    # their prices when a single dropdown changes; no posterior work in the slate.
    h = pd.Series(dict(zip(("serve_elo", "receive_elo", "conf_elo"), home_values)))
    a = pd.Series(dict(zip(("serve_elo", "receive_elo", "conf_elo"), away_values)))
    neutral = venue_mode != VENUE_MODES[0]
    p = model.set_score_probs(elo_features(h, a, neutral), np.asarray(params))[0]
    if venue_mode == VENUE_MODES[2]:
        pf = model.set_score_probs(elo_features(a, h, neutral), np.asarray(params))[0]
        p = 0.5 * (p + pf[::-1])
    return p


def game_time(row):
    if not row.get("start_epoch"):
        return "TBA"
    return pd.Timestamp(row["start_epoch"], unit="s", tz="UTC").tz_convert(
        "America/New_York").strftime("%-I:%M %p")


def render_schedule(ratings, params, home_venues, render_panel):
    """Date-scoped slate and durable overrides; widget cleanup cannot erase them."""
    import kelly
    import time

    today = pd.Timestamp.now(tz="America/New_York").date()
    day = st.date_input("NCAA schedule date", value=today,
                        min_value=today - dt.timedelta(days=7),
                        max_value=today + dt.timedelta(days=7), key="ncaa_date")
    date_key = day.isoformat()
    slates = st.session_state.setdefault("ncaa_slates", {})
    if st.button("Fetch NCAA schedule", type="primary", key="ncaa_fetch"):
        status = st.progress(0.0, text="Fetching NCAA schedule…")
        started = time.perf_counter()
        try:
            slate = fetch_slate(day, ratings, home_venues,
                                lambda value, text: status.progress(value, text=text))
        except Exception as exc:
            st.error(f"NCAA fetch failed; no partial slate loaded: {exc}")
        else:
            previous = slates.get(date_key, {})
            slate["overrides"] = previous.get("overrides", {})
            slate["selected"] = previous.get("selected")
            slate["load_seconds"] = time.perf_counter() - started
            slates[date_key] = slate
    slate = slates.get(date_key)
    if slate is None:
        st.info("Fetch the schedule to price every game with two rated teams.")
        return
    st.caption(f"{slate['fetched']} unique games fetched = {len(slate['priced'])} priced + "
               f"{len(slate['unpriced'])} not priced. {slate['raw_count']} division listings, "
               f"{slate['duplicates']} duplicate listings. Times Eastern. "
               f"Loaded in {slate['load_seconds']:.2f}s at {slate['retrieved_at']}.")
    st.caption("Fair prices use Team Elo. Venue changes affect only that game; "
               "Price this game opens all markets and staking controls below.")
    if slate["unpriced"]:
        with st.expander(f"Not priced ({len(slate['unpriced'])}) — unrated teams or invalid schedule data"):
            st.dataframe(pd.DataFrame(slate["unpriced"])[
                ["contest_id", "division", "teams", "reason"]], hide_index=True)
    indexed = ratings.set_index("team")
    widths = [1, 2.2, 2.2, 2, 1.5, 2.2, 2.2, 1.2]
    headers = ["Time (ET)", "Away @ Home", "Site", "Venue", "ML (away / home)",
               "Spreads (home / away)", "Totals (under / over)", "Full prices"]
    for col, label in zip(st.columns(widths), headers):
        col.markdown(f"**{label}**")
    for row in slate["priced"]:
        cid = row["contest_id"]
        cols = st.columns(widths)
        cols[0].write(game_time(row))
        cols[1].write(f"{row['away']} @ {row['home']}")
        cols[2].write(row["site"])
        cols[2].caption(row["venue"] or "No venue supplied")
        current = slate["overrides"].get(cid, row["venue_mode"])
        widget_key = f"ncaa_venue:{date_key}:{cid}"
        # The model state survives Streamlit removing widgets on source/date switches.
        def save_override(cid=cid, widget_key=widget_key):
            slate["overrides"][cid] = st.session_state[widget_key]
        mode = cols[3].selectbox("Venue", VENUE_MODES, index=VENUE_MODES.index(current),
                                 key=widget_key, on_change=save_override,
                                 label_visibility="collapsed")
        h, a = indexed.loc[row["home"]], indexed.loc[row["away"]]
        values = lambda r: tuple(float(r[k]) for k in ("serve_elo", "receive_elo", "conf_elo"))
        probs = point_price(values(h), values(a), mode, tuple(params))
        markets = {k: v[0] for k, v in model.markets(probs[None, :]).items()}
        def odds(p):
            value = kelly.prob_to_american(float(p))
            return "—" if value is None else f"{value:+.0f}"
        cols[4].write(f"{odds(1-markets['home_ml'])} / {odds(markets['home_ml'])}")
        for line in (1, 2):
            p = markets[f"home_minus_{line}_5"]
            q = markets[f"away_minus_{line}_5"]
            cols[5].caption(f"H −{line}.5 / A +{line}.5: {odds(p)} / {odds(1-p)}")
            cols[5].caption(f"H +{line}.5 / A −{line}.5: {odds(1-q)} / {odds(q)}")
        for line in (3, 4):
            p = markets[f"under_{line}_5_sets"]
            cols[6].caption(f"{line}.5: {odds(p)} / {odds(1-p)}")
        if cols[7].button("Price this game", key=f"ncaa_pick:{date_key}:{cid}"):
            slate["selected"] = cid
    selected = next((r for r in slate["priced"] if r["contest_id"] == slate["selected"]), None)
    if selected:
        st.divider()
        mode = slate["overrides"].get(selected["contest_id"], selected["venue_mode"])
        st.subheader(f"{selected['away']} @ {selected['home']} — {game_time(selected)} ET")
        st.caption(f"{mode} · {selected['site']} · {selected['venue'] or 'venue ?'}")
        render_panel(selected["home"], selected["away"], mode,
                     key_prefix=f"ncaa:{date_key}:{selected['contest_id']}:",
                     default_date=day,
                     default_time="" if game_time(selected) == "TBA" else game_time(selected),
                     show_news=os.environ.get("WVB_ENABLE_SCHEDULE_INJURIES") == "1")
