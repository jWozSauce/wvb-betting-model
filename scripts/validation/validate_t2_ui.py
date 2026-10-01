"""AppTest parity against the pre-refactor app, with all external IO blocked.

Run from repository root: .venv/bin/python scripts/validation/validate_t2_ui.py
Results are JSON/CSV in a timestamped run directory under --output.
"""
import argparse
import ast
import copy
import datetime as dt
import os
from contextlib import ExitStack
import json
from pathlib import Path
from evidence_runs import new_run
import subprocess
import sys
import time
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import app_config

BASE = "2efbb954e4810bc41015c61168e012f24c04b993"
PAIRS = [("nebraska", "wisconsin"), ("texas", "stanford"), ("pittsburgh", "louisville")]
MODES = ["Home court", "Neutral (host/label matters)", "True toss-up (symmetrized)"]


def element(elements, label):
    return next(e for e in elements if e.label == label)


def check(at):
    assert not at.exception, [e.message for e in at.exception]
    return at


def new_app(source):
    source = source.replace('HERE = os.path.dirname(os.path.abspath(__file__))', f'HERE = {str(ROOT)!r}')
    at = AppTest.from_string(source, default_timeout=30)
    at.secrets["APP_PASSWORD"] = ""
    at.session_state.sheet_synced = True
    return check(at.run())


def select_match(at, home, away, mode):
    element(at.selectbox, "Home team").set_value(home)
    element(at.selectbox, "Away team (listed first at the book)").set_value(away)
    element(at.selectbox, "Venue").set_value(mode)
    return check(at.run())


def board(at, tab=0):
    return next(d.value for d in at.tabs[tab].dataframe if "fair_odds" in d.value.columns)


def guards(stack):
    defaults = dict(app_config.DEFAULTS)
    defaults["value_req"] = .02
    stack.enter_context(patch('app_config.load', return_value=defaults))
    stack.enter_context(patch('app_config.refresh_from_sheet', return_value=defaults))
    stack.enter_context(patch('app_config.update', return_value=defaults))
    stack.enter_context(patch('bet_log.read_log', return_value=pd.DataFrame()))
    stack.enter_context(patch('bet_log.log_bets', side_effect=AssertionError("Real log write prohibited")))
    stack.enter_context(patch('bet_log.grade_pending', side_effect=AssertionError("Real grading prohibited")))
    stack.enter_context(patch('vbstats.news.team_news', return_value=[]))
    stack.enter_context(patch('vbstats.injury_ai.analyze_team', return_value="Offline stub: no paid call"))
    stack.enter_context(patch('requests.sessions.Session.request', side_effect=RuntimeError("Network prohibited in UI test")))
    stack.enter_context(patch('urllib.request.urlopen', side_effect=RuntimeError("Network prohibited in UI test")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--slate')
    args = parser.parse_args()
    out = new_run(args.output)
    original = subprocess.check_output(['git','show',f'{BASE}:streamlit_app.py'], cwd=ROOT, text=True)
    updated = (ROOT/'streamlit_app.py').read_text()
    rows = []
    with ExitStack() as stack:
        guards(stack)
        old, new = new_app(original), new_app(updated)
        for home, away in PAIRS:
            for mode in MODES:
                select_match(old, home, away, mode)
                select_match(new, home, away, mode)
                b1, b2 = board(old), board(new)
                pd.testing.assert_frame_equal(b1,b2,check_exact=True)
                rows.append({'home':home,'away':away,'venue':mode,
                             'original_ml':float(b1.iloc[0]['prob']),
                             'refactor_ml':float(b2.iloc[0]['prob']),
                             'original_p20':float(b1.iloc[0]['prob_p20']),
                             'refactor_p20':float(b2.iloc[0]['prob_p20']),
                             'markets_equal':len(b1)})
                print(home, away, mode, '16 markets identical', flush=True)
        # Verify the original pricing math also survives both lineup modes.
        for mode in ("Hybrid (Elo + lineup adjust)", "Player (RAPM)"):
            element(old.radio, "Pricing model").set_value(mode)
            element(new.radio, "Pricing model").set_value(mode)
            check(old.run()); check(new.run())
            pd.testing.assert_frame_equal(board(old), board(new), check_exact=True)
        # Existing sportsbook path must be the identical AST, then exercise it.
        def best_body(source):
            return next(n.body for n in ast.parse(source).body if isinstance(n, ast.With)
                        and ast.unparse(n.items[0].context_expr) == "tab_best")
        before, after = best_body(original), best_body(updated)
        offset = next(i for i,n in enumerate(before) if isinstance(n, ast.Assign)
                      and ast.unparse(n.targets[0]) == "paste")
        assert [ast.dump(n) for n in before[offset:]] == [ast.dump(n) for n in after[-1].orelse]
        import paste_odds
        pasted = "Wisconsin +180\nNebraska -220"
        fixture = paste_odds.parse_board(pasted)[0]
        assert len(fixture) == 1
        with patch('vbstats.venues.slate_venues', return_value={}), \
             patch('oddspapi.fetch_board', return_value=(fixture, 0)), \
             patch('oddspapi.account', return_value={}):
            sportsbook = new_app(updated)
            element(sportsbook.radio, "Odds source").set_value("Paste a board")
            check(sportsbook.run())
            element(sportsbook.text_area, "Pasted board").set_value(pasted)
            element(sportsbook.button, "Parse & evaluate").click()
            check(sportsbook.run())
            paste_card = sportsbook.session_state.best_card.copy()
            assert len(paste_card) == 2
            element(sportsbook.radio, "Odds source").set_value("Live API (Pinnacle/DK/FD/BetOnline)")
            check(sportsbook.run())
            element(sportsbook.button, "Fetch odds & evaluate").click()
            check(sportsbook.run())
            pd.testing.assert_frame_equal(paste_card, sportsbook.session_state.best_card, check_exact=True)
        extras = {"lineup_modes": "identical", "sportsbook_AST": "identical",
                  "paste_UI": "PASS", "live_API_UI_fixture": "PASS; no billable calls"}
        if args.slate:
            import schedule_pricing as sp
            from vbstats import model
            fixture_slate = json.loads(Path(args.slate).read_text())
            day = dt.date.fromisoformat(fixture_slate['date'])
            sp.point_price.clear()
            with patch.dict(os.environ, {"WVB_ENABLE_NCAA_SCHEDULE":"1"}), \
                 patch('schedule_pricing.fetch_slate', return_value=copy.deepcopy(fixture_slate)) as fetch:
                scheduled = new_app(updated)
                element(scheduled.radio, "Odds source").set_value(sp.SOURCE)
                check(scheduled.run())
                scheduled.date_input(key="ncaa_date").set_value(day)
                check(scheduled.run())
                start=time.perf_counter()
                scheduled.button(key="ncaa_fetch").click()
                check(scheduled.run())
                extras['slate_render_seconds']=time.perf_counter()-start
                assert fetch.call_count == 1
                first=fixture_slate['priced'][0]
                key=f"ncaa_venue:{day}:{first['contest_id']}"
                changed=next(m for m in MODES if m!=first['venue_mode'])
                with patch.object(model, 'set_score_probs', wraps=model.set_score_probs) as compute:
                    start=time.perf_counter()
                    scheduled.selectbox(key=key).set_value(changed)
                    check(scheduled.run())
                    extras['single_venue_change_seconds']=time.perf_counter()-start
                    extras['single_venue_model_calls']=compute.call_count
                    assert compute.call_count in (1,2), compute.call_count
                assert fetch.call_count == 1
                extras['venue_change_refetches']=fetch.call_count-1
                parity=[]
                # Test actual schedule drill-in against the independent original app.
                element(old.radio, "Pricing model").set_value("Team Elo")
                for game in fixture_slate['priced'][:3]:
                    cid=game['contest_id']
                    scheduled.button(key=f"ncaa_pick:{day}:{cid}").click()
                    check(scheduled.run())
                    for mode in MODES:
                        scheduled.selectbox(key=f"ncaa_venue:{day}:{cid}").set_value(mode)
                        check(scheduled.run())
                        select_match(old, game['home'], game['away'], mode)
                        pd.testing.assert_frame_equal(board(old), board(scheduled,1),check_exact=True)
                        b=board(scheduled,1)
                        parity.append(dict(home=game['home'],away=game['away'],venue=mode,
                                           original_ml=float(board(old).iloc[0]['prob']),
                                           drill_in_ml=float(b.iloc[0]['prob']),
                                           original_p20=float(board(old).iloc[0]['prob_p20']),
                                           drill_in_p20=float(b.iloc[0]['prob_p20']),markets_equal=len(b)))
                pd.DataFrame(parity).to_csv(out/'drill_in_parity.csv', index=False)
                # Manual panel and drill-in simultaneously: keys must not collide.
                select_match(scheduled, first['home'],first['away'],MODES[0])
                assert len(board(scheduled))==len(board(scheduled,1))==16
                overrides=dict(scheduled.session_state.ncaa_slates[str(day)]['overrides'])
                element(scheduled.radio,'Odds source').set_value('Paste a board')
                check(scheduled.run())
                element(scheduled.radio,'Odds source').set_value(sp.SOURCE)
                check(scheduled.run())
                assert scheduled.session_state.ncaa_slates[str(day)]['overrides']==overrides
                assert fetch.call_count==1
                # Date switches and return preserve per-game state without loading.
                scheduled.date_input(key='ncaa_date').set_value(day-dt.timedelta(days=1))
                check(scheduled.run())
                scheduled.date_input(key='ncaa_date').set_value(day)
                check(scheduled.run())
                assert scheduled.session_state.ncaa_slates[str(day)]['overrides']==overrides
                assert fetch.call_count==1
                extras['source_date_switch_state']='PASS'
        (out/'extra_checks.json').write_text(json.dumps(extras,indent=2))
        pd.DataFrame(rows).to_csv(out/'manual_parity.csv',index=False)
        (out/'result.json').write_text(json.dumps({'baseline':BASE,'manual_parity':'PASS','rows':rows}, indent=2))


if __name__ == '__main__':
    main()
