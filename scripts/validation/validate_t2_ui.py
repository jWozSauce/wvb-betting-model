"""AppTest parity against the pre-refactor app, with all external IO blocked.

Run from repository root: .venv/bin/python scripts/validation/validate_t2_ui.py
Results are JSON/CSV in a new directory passed with --output.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
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
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
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
        pd.DataFrame(rows).to_csv(out/'manual_parity.csv',index=False)
        (out/'result.json').write_text(json.dumps({'baseline':BASE,'manual_parity':'PASS','rows':rows}, indent=2))


if __name__ == '__main__':
    main()
