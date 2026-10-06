"""Boot accepted defaults and replay schedule drill-ins without external IO."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd
from validate_t2_ui import ROOT, guards, new_app, element, check, board, select_match, MODES, BASE
from evidence_runs import new_run
import repair_flags
import schedule_pricing as sp
from vbstats import model

source = (ROOT/'streamlit_app.py').read_text()
old = subprocess.check_output(['git', 'show', f'{BASE}:streamlit_app.py'], cwd=ROOT, text=True)
slate = json.loads((ROOT/'evidence/t2-20261001/full-slate-1/slate.json').read_text())
day = dt.date.fromisoformat(slate['date'])
rows = []
with ExitStack() as stack:
    guards(stack)
    stack.enter_context(patch.dict(os.environ, dict(os.environ)))
    for key in ('WVB_ENABLE_REPAIRS', 'WVB_ENABLE_NCAA_SCHEDULE',
                'WVB_ENABLE_INLINE_DRILL_IN', 'WVB_ENABLE_SCHEDULE_INJURIES',
                'WVB_ENABLE_LEARNED_MATCHING'):
        os.environ.pop(key, None)
    assert repair_flags.enabled()
    fetch = stack.enter_context(patch('schedule_pricing.fetch_slate', return_value=copy.deepcopy(slate)))
    sp.point_price.clear()
    app, baseline = new_app(source), new_app(old)
    assert any(tab.label == 'Team matching' for tab in app.tabs)
    assert sp.SOURCE in element(app.radio, 'Odds source').options
    element(app.radio, 'Odds source').set_value(sp.SOURCE)
    check(app.run())
    app.date_input(key='ncaa_date').set_value(day)
    check(app.run())
    app.button(key='ncaa_fetch').click()
    check(app.run())
    assert fetch.call_count == 1
    first = slate['priced'][0]
    changed = next(m for m in MODES if m != first['venue_mode'])
    with patch.object(model, 'set_score_probs', wraps=model.set_score_probs) as compute:
        app.selectbox(key=f"ncaa_venue:{day}:{first['contest_id']}").set_value(changed)
        check(app.run())
        assert compute.call_count in (1, 2), compute.call_count
        single_game_calls = compute.call_count
    for game in slate['priced'][:3]:
        cid = game['contest_id']
        app.button(key=f'ncaa_pick:{day}:{cid}').click()
        check(app.run())
        for mode in MODES:
            app.selectbox(key=f'ncaa_venue:{day}:{cid}').set_value(mode)
            check(app.run())
            select_match(baseline, game['home'], game['away'], mode)
            pd.testing.assert_frame_equal(board(baseline), board(app, 1), check_exact=True)
            rows.append(dict(home=game['home'], away=game['away'], venue=mode, markets=16))
    assert fetch.call_count == 1
    os.environ['WVB_ENABLE_REPAIRS'] = '0'
    os.environ['WVB_ENABLE_NCAA_SCHEDULE'] = '0'
    assert not repair_flags.enabled()
    rollback = new_app(source)
    assert sp.SOURCE not in element(rollback.radio, 'Odds source').options
out = new_run(ROOT/'evidence/integration-20261001')
(out/'defaults.json').write_text(json.dumps(dict(defaults_boot=True, learned_matching_default_on=True, rollback_boot=True,
    schedule_games=len(slate['priced']), unpriced_games=len(slate['unpriced']),
    drill_in_parity=rows, venue_change_model_calls=single_game_calls,
    slate_fetches=fetch.call_count, external_io='mocked'), indent=2))
print('PASS integrated defaults, cached slate, nine drill-in parity comparisons, rollback')
