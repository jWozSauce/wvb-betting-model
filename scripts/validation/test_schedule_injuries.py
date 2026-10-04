"""Exercise shared injury rendering and the real cache using a counted fake client."""
import ast
import copy
import datetime as dt
import json
import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch
import streamlit as st
from validate_t2_ui import ROOT, guards, new_app, element, check, select_match, MODES
from evidence_runs import new_run
from vbstats.injury_ai import analyze_team
import schedule_pricing as sp

source = (ROOT/'streamlit_app.py').read_text()
cache_def = next(n for n in ast.parse(source).body
                 if isinstance(n, ast.FunctionDef) and n.name == 'cached_injury_analysis')
assert any(isinstance(d, ast.Call) and any(k.arg == 'ttl' and
           isinstance(k.value, ast.Constant) and k.value.value == 3600 for k in d.keywords)
           for d in cache_def.decorator_list)
slate = json.loads((ROOT/'evidence/t2-20261001/full-slate-1/slate.json').read_text())
day = dt.date.fromisoformat(slate['date'])
first = slate['priced'][0]
counts = {}
called_teams = []

def reply(**kwargs):
    prompt = kwargs['messages'][0]['content']
    team = prompt.split('Team: ', 1)[1].split('\n', 1)[0]
    called_teams.append(team)
    return SimpleNamespace(content=[SimpleNamespace(type='text', text=f'Mocked injury verdict for {team}')],
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5))

client = SimpleNamespace(messages=SimpleNamespace(create=Mock(side_effect=reply)))

def injuries(app, tab):
    return {e.label: [m.value for m in e.markdown] for e in app.tabs[tab].expander
            if 'AI injury analysis' in e.label}

with ExitStack() as stack:
    guards(stack)
    # Restore the real analyzer behind the existing cache; only its HTTP client is fake.
    stack.enter_context(patch('vbstats.injury_ai.analyze_team', analyze_team))
    stack.enter_context(patch('anthropic.Anthropic', return_value=client))
    stack.enter_context(patch.dict(os.environ, dict(os.environ)))
    os.environ.pop('WVB_ENABLE_SCHEDULE_INJURIES', None)
    fetch = stack.enter_context(patch('schedule_pricing.fetch_slate', return_value=copy.deepcopy(slate)))
    st.cache_data.clear()
    app = new_app(source)
    assert client.messages.create.call_count == 0
    element(app.radio, 'Odds source').set_value(sp.SOURCE)
    check(app.run())
    app.date_input(key='ncaa_date').set_value(day)
    check(app.run())
    app.button(key='ncaa_fetch').click()
    check(app.run())
    counts['loaded_slate'] = client.messages.create.call_count
    assert counts['loaded_slate'] == 0
    key = f"ncaa_venue:{day}:{first['contest_id']}"
    app.selectbox(key=key).set_value(next(m for m in MODES if m != first['venue_mode']))
    check(app.run())
    counts['repriced_slate'] = client.messages.create.call_count
    assert counts['repriced_slate'] == 0
    pick = f"ncaa_pick:{day}:{first['contest_id']}"
    app.button(key=pick).click()
    check(app.run())
    counts['first_drill_in'] = client.messages.create.call_count
    assert counts['first_drill_in'] == 2
    assert called_teams == [first['away'], first['home']]
    drill_in = injuries(app, 1)
    assert len(drill_in) == 2
    app.button(key=pick).click()
    check(app.run())
    counts['repeat_drill_in'] = client.messages.create.call_count
    assert counts['repeat_drill_in'] == 2
    assert injuries(app, 1) == drill_in
    select_match(app, first['home'], first['away'], first['venue_mode'])
    counts['same_manual_match'] = client.messages.create.call_count
    assert counts['same_manual_match'] == 2
    assert injuries(app, 0) == drill_in
    assert fetch.call_count == 1
    # Explicit zero is the rollback switch after acceptance.
    os.environ['WVB_ENABLE_SCHEDULE_INJURIES'] = '0'
    st.cache_data.clear()
    disabled = new_app(source)
    element(disabled.radio, 'Odds source').set_value(sp.SOURCE)
    check(disabled.run())
    disabled.date_input(key='ncaa_date').set_value(day)
    check(disabled.run())
    disabled.button(key='ncaa_fetch').click()
    check(disabled.run())
    disabled.button(key=pick).click()
    check(disabled.run())
    assert not injuries(disabled, 1)
    counts['disabled_drill_in'] = client.messages.create.call_count
    assert counts['disabled_drill_in'] == 2
out = new_run(ROOT/'evidence/t10-20261002')
(out/'injury-cache.json').write_text(json.dumps(dict(cumulative_client_calls=counts,
    called_teams=called_teams, injury_sections=drill_in, shared_section_equal=True,
    cache_ttl_seconds=3600, real_api_calls=0, accepted_default_on=True, explicit_zero_rollback=True), indent=2))
print('PASS shared injury sections, explicit selection, cache reuse, default-on and explicit-zero rollback')
