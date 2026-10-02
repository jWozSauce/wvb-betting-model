"""Verify row adjacency, single-panel movement, close, state and pricing parity."""
import copy
import datetime as dt
import json
import os
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd
from validate_t2_ui import ROOT, guards, new_app, element, check, board, select_match, MODES
from evidence_runs import new_run
import schedule_pricing as sp

source = (ROOT/'streamlit_app.py').read_text()
slate = json.loads((ROOT/'evidence/t2-20261001/full-slate-1/slate.json').read_text())
day = dt.date.fromisoformat(slate['date'])
games = slate['priced']
indices = [len(games)//2, 2, len(games)-2]
parity = []

def assert_adjacent(app, index):
    game = games[index]
    label = f"{game['away']} @ {game['home']}"
    blocks = list(app.tabs[1].children.values())
    row_index = next(i for i,b in enumerate(blocks) if b.type == 'flex_container'
                     and any(n.type == 'markdown' and n.value == label for n in b))
    panel = blocks[row_index+1]
    assert any(n.type == 'button' and n.label == '✕' for n in panel)
    assert any(n.type == 'subheader' and n.value.startswith(label+' —') for n in panel)
    next_label = f"{games[index+1]['away']} @ {games[index+1]['home']}"
    assert any(n.type == 'markdown' and n.value == next_label for n in blocks[row_index+2])
    assert sum(n.type == 'button' and n.label == '✕' for n in app.tabs[1]) == 1

with ExitStack() as stack:
    guards(stack)
    stack.enter_context(patch.dict(os.environ, {'WVB_ENABLE_INLINE_DRILL_IN':'1',
                                              'WVB_ENABLE_SCHEDULE_INJURIES':'1'}))
    fetch = stack.enter_context(patch('schedule_pricing.fetch_slate', return_value=copy.deepcopy(slate)))
    app, manual = new_app(source), new_app(source)
    element(app.radio, 'Odds source').set_value(sp.SOURCE);check(app.run())
    app.date_input(key='ncaa_date').set_value(day);check(app.run())
    app.button(key='ncaa_fetch').click();check(app.run())
    for index in indices:
        game = games[index];cid = game['contest_id']
        app.button(key=f'ncaa_pick:{day}:{cid}').click();check(app.run())
        assert_adjacent(app, index)
        for venue in MODES[:2]:
            app.selectbox(key=f'ncaa_venue:{day}:{cid}').set_value(venue);check(app.run())
            assert_adjacent(app,index)
            select_match(manual,game['home'],game['away'],venue)
            pd.testing.assert_frame_equal(board(app,1),board(manual),check_exact=True)
            parity.append(dict(row=index,home=game['home'],away=game['away'],venue=venue,markets=16))
    selected=games[indices[-1]]['contest_id']
    saved=copy.deepcopy(app.session_state.ncaa_slates[str(day)])
    element(app.radio,'Odds source').set_value('Paste a board');check(app.run())
    element(app.radio,'Odds source').set_value(sp.SOURCE);check(app.run())
    assert_adjacent(app,indices[-1])
    app.date_input(key='ncaa_date').set_value(day-dt.timedelta(days=1));check(app.run())
    app.date_input(key='ncaa_date').set_value(day);check(app.run())
    assert_adjacent(app,indices[-1])
    assert app.session_state.ncaa_slates[str(day)]['overrides']==saved['overrides']
    app.button(key=f'ncaa_close:{day}:{selected}').click();check(app.run())
    assert app.session_state.ncaa_slates[str(day)]['selected'] is None
    assert not any(b.label=='✕' for b in app.button)
    assert not any('fair_odds' in d.value.columns for d in app.tabs[1].dataframe)
    assert len([b for b in app.tabs[1].button if b.label=='Price this game'])==len(games)
    assert fetch.call_count==1
out=new_run(ROOT/'evidence/t11-20261002')
(out/'inline-panel.json').write_text(json.dumps(dict(row_adjacency=True,checked_row_indices=indices,
    single_panel=True,close_restores_plain_rows=True,source_date_state_preserved=True,
    slate_fetches=fetch.call_count,parity=parity,external_io='mocked'),indent=2))
print('PASS inline placement, six exact pricing boards, selected venue updates, close and state')
