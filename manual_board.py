"""Date-scoped board-to-schedule decisions; pricing stays in the shared card path."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
from collections import Counter

import pandas as pd
import streamlit as st

import paste_odds
import schedule_pricing as schedule

SOURCE = "Schedule + board (manual match)"
EXCLUDE = "exclude"


def board_ids(games):
    """Stable across odds edits/order changes; repeated identical labels stay distinct."""
    seen = Counter()
    for g in games:
        labels = (g['away'], g['home'])
        seen[labels] += 1
        yield hashlib.sha256(repr((labels, seen[labels])).encode()).hexdigest()[:20]


def proposal(g, fixtures, ratings):
    names = dict(zip(ratings.team, ratings.name_full)) if 'name_full' in ratings else None
    a, ac = paste_odds.match_team(g['away'], ratings.team.tolist(), fullnames=names)
    h, hc = paste_odds.match_team(g['home'], ratings.team.tolist(), fullnames=names)
    hits = [r for r in fixtures if {r['home'], r['away']} == {a, h}]
    if a and h and a != h and min(ac, hc) >= .8 and len(hits) == 1:
        return hits[0]['contest_id'], a
    return None, None


def orient(g, fixture, board_away_team, day, venue_mode):
    """Keep a spread's sign attached to its picked team; flip side labels only."""
    if board_away_team not in (fixture['away'], fixture['home']):
        raise ValueError('Confirm which schedule team is listed first by the book')
    result = copy.deepcopy(g)
    reversed_ = board_away_team == fixture['home']
    if reversed_:
        for market in result['markets']:
            market['side'] = {'home': 'away', 'away': 'home'}.get(market['side'], market['side'])
    result.update(home=fixture['home'], away=fixture['away'], date=str(day),
                  time='' if schedule.game_time(fixture) == 'TBA' else schedule.game_time(fixture),
                  _schedule=dict(fixture), _venue_mode=venue_mode,
                  _book_reversed=reversed_)
    return result


def render(ratings, home_venues):
    today = pd.Timestamp.now(tz='America/New_York').date()
    ss = st.session_state
    def save_day():
        ss.manual_last_day = ss.manual_date
    day = st.date_input('NCAA schedule date', value=ss.get('manual_last_day', today),
                        min_value=today-dt.timedelta(days=7),
                        max_value=today+dt.timedelta(days=7), key='manual_date', on_change=save_day)
    date_key = str(day)
    state = ss.setdefault('manual_boards', {}).setdefault(date_key, {
        'slate': None, 'games': [], 'decisions': {}, 'overrides': {},
        'paste': '', 'unparsed': [], 'oddsless': 0})
    if st.button('Fetch NCAA schedule', key='manual_fetch'):
        progress = st.progress(0., text='Fetching NCAA schedule…')
        try:
            loaded = schedule.fetch_slate(day, ratings, home_venues,
                        lambda v, t: progress.progress(v, text=t))
        except Exception as exc:
            st.error(f'NCAA fetch failed; previous schedule retained: {exc}')
        else:
            state['slate'] = loaded
    paste_key = f'manual_paste:{date_key}'
    if paste_key not in ss:
        ss[paste_key] = state['paste']
    def save_paste():
        state['paste'] = ss[paste_key]
    st.text_area('Pasted board', key=paste_key, height=180, on_change=save_paste)
    if st.button('Parse board', key='manual_parse'):
        parsed, unparsed, oddsless = paste_odds.parse_board(ss[paste_key])
        state.update(games=parsed, unparsed=unparsed, oddsless=oddsless,
                     parsed_paste=ss[paste_key])
        if not parsed:
            st.warning('No games with odds parsed. Use the book’s full text including its odds buttons.')
    stale_paste = state.get('parsed_paste', '') != state['paste']
    if stale_paste:
        st.info('Board text changed. Parse it before pricing.')
    slate = state['slate']
    fixtures = ([] if slate is None else slate['priced'] +
                [r for r in slate['unpriced'] if r.get('home') and r.get('away')])
    lookup = {r['contest_id']: r for r in fixtures}
    rated = set(ratings.team)
    selections, table, errors = [], [], []
    selected_ids = Counter()
    # Reconcile model state before creating widgets; callbacks persist decisions.
    for bid, g in zip(board_ids(state['games']), state['games']):
        decision = state['decisions'].setdefault(bid, {})
        if not decision:
            cid, first = proposal(g, fixtures, ratings)
            if fixtures:  # board-first loading must still propose after a fetch
                decision.update(cid=cid, first=first, confirmed=False)
        cid = decision.get('cid')
        if cid is not None and cid not in lookup and cid != EXCLUDE:
            decision.update(cid=None, first=None, confirmed=False)
        if decision.get('confirmed') and decision.get('cid') in lookup:
            selected_ids[decision['cid']] += 1
    if state['games']:
        st.caption('Choose the schedule fixture and the team listed first by the book, then confirm. Only confirmed pairs are priced. Times Eastern.')
    for index, (bid, g) in enumerate(zip(board_ids(state['games']), state['games']), 1):
        decision = state['decisions'][bid]
        prefix = f'manual:{date_key}:{bid}'
        cols = st.columns([2, 3, 2, 2, 1])
        cols[0].write(f"{index}. {g['away']} @ {g['home']}")
        key = prefix+':fixture'
        ss[key] = decision.get('cid')
        def change_fixture(d=decision, k=key, pre=prefix, game=g):
            cid = ss[k]
            d.update(cid=cid, confirmed=False, first=None)
            if cid in lookup:
                proposed, first = proposal(game, [lookup[cid]], ratings)
                d['first'] = first if proposed else None
            ss.pop(pre+':first', None)
            ss[pre+':confirm'] = False
        def fixture_label(cid):
            if cid is None: return '— choose fixture —'
            if cid == EXCLUDE: return '— exclude —'
            r = lookup[cid]
            return f"{r['away']} @ {r['home']}, {schedule.game_time(r)}, {r.get('site', r.get('reason', ''))} [{cid}]"
        cid = cols[1].selectbox('Schedule game', [None, EXCLUDE, *lookup],
                                key=key, format_func=fixture_label, on_change=change_fixture)
        r = lookup.get(cid)
        reason = ''
        if r:
            firstkey = prefix+':first'
            ss[firstkey] = decision.get('first') if decision.get('first') in (r['away'], r['home']) else None
            def change_first(d=decision, k=firstkey, pre=prefix):
                d.update(first=ss[k], confirmed=False)
                ss[pre+':confirm'] = False
            first = cols[2].selectbox(f"Book first: {g['away']} →", [None, r['away'], r['home']],
                                     key=firstkey, format_func=lambda t: t or '— choose team —',
                                     on_change=change_first)
            vkey = f'manual_venue:{date_key}:{cid}:{bid}'
            ss[vkey] = state['overrides'].get(cid, r.get('venue_mode', schedule.VENUE_MODES[0]))
            def save_venue(k=vkey, c=cid):
                state['overrides'][c] = ss[k]
            mode = cols[3].selectbox('Venue', schedule.VENUE_MODES, key=vkey, on_change=save_venue)
            ckey = prefix+':confirm'
            eligible = first is not None and {r['home'], r['away']} <= rated
            ss[ckey] = decision.get('confirmed', False)
            if not eligible: ss[ckey] = False; decision['confirmed'] = False
            def confirm(d=decision, k=ckey): d['confirmed'] = ss[k]
            confirmed = cols[4].checkbox('Confirm', key=ckey, on_change=confirm, disabled=not eligible)
            if first == r['home']: cols[0].caption('book lists reversed')
            if not {r['home'], r['away']} <= rated:
                reason = 'Unrated schedule team — cannot price'; cols[1].warning(reason)
            elif selected_ids[cid] > 1:
                reason = 'Duplicate fixture — confirm only one board row'; cols[1].warning(reason)
                errors.append(reason)
            elif confirmed and eligible:
                selections.append(orient(g, r, first, day, mode))
            else:
                reason = 'Awaiting confirmation'
        status = 'excluded' if cid == EXCLUDE else ('matched' if r and not reason else 'unmatched')
        table.append({'board_#': index, 'board': f"{g['away']} @ {g['home']}",
                      'schedule': fixture_label(cid), 'status': status,
                      'orientation': ('reversed' if r and decision.get('first') == r['home'] else
                                      'same' if r and decision.get('first') == r['away'] else ''),
                      'venue_mode': state['overrides'].get(cid, r.get('venue_mode', '') if r else ''),
                      'reason': reason})
    counts = Counter(row['status'] for row in table)
    st.caption(f"Board games: {len(table)} = {counts['matched']} matched + {counts['excluded']} excluded + {counts['unmatched']} unmatched")
    used = {g['_schedule']['contest_id'] for g in selections}
    leftovers = [r for r in fixtures if r['contest_id'] not in used]
    with st.expander(f'Schedule games unmatched ({len(leftovers)})'):
        st.dataframe(pd.DataFrame(leftovers), hide_index=True)
    if state['unparsed']:
        with st.expander(f"Unparsed tokens ({len(state['unparsed'])})"):
            st.write(state['unparsed'][:100])
    if counts['unmatched']:
        st.info('Unmatched and unconfirmed rows will not be priced.')
    price = st.button('Price', type='primary', key='manual_price',
                       disabled=not selections or bool(errors) or stale_paste)
    state['match_table'] = table
    state['counts'] = dict(counts)
    # The parent invalidates displayed cards when these meaningful inputs change.
    snapshot = {'date': date_key, 'games': selections, 'table': table,
                'paste': state['paste'], 'parsed_paste': state.get('parsed_paste', '')}
    return price, selections, state['unparsed'], snapshot
