"""Ensure review-disabled behavior is preserved and annotations do not reprice."""
from contextlib import ExitStack
from pathlib import Path
from evidence_runs import new_run
from unittest.mock import patch
import json,os,sys,subprocess
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from validate_t2_ui import guards,new_app,element,check,select_match,board,MODES
old=subprocess.check_output(['git','show','490ccea:streamlit_app.py'],text=True,cwd=ROOT);new=(ROOT/'streamlit_app.py').read_text()
rows=[]
with ExitStack() as stack:
 guards(stack);stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 for enabled in ['0','1']:
  with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':enabled}):
   before=new_app(old);after=new_app(new)
   for venue in MODES:
    select_match(before,'nebraska','kansas',venue);select_match(after,'nebraska','kansas',venue)
    for mode in ['Team Elo','Hybrid (Elo + lineup adjust)','Player (RAPM)']:
     element(before.radio,'Pricing model').set_value(mode);check(before.run());element(after.radio,'Pricing model').set_value(mode);check(after.run())
     pd.testing.assert_frame_equal(board(before),board(after),check_exact=True);rows.append(dict(enabled=enabled,venue=venue,model=mode,market_rows=16))
   # Compare Best bets cards with exactly the same inputs.
   for app in [before,after]:
    element(app.radio,'Odds source').set_value('Paste a board');check(app.run());element(app.text_area,'Pasted board').set_value('Wisconsin -110\nNebraska -110');element(app.button,'Parse & evaluate').click();check(app.run())
   # Absence annotation text intentionally changes when enabled.
   cols=[c for c in before.session_state.best_card.columns if c!='⚕ absent']
   pd.testing.assert_frame_equal(before.session_state.best_card[cols],after.session_state.best_card[cols],check_exact=True)
 # Actual API UI error surface, fake credential only, without network.
 with patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}),patch('oddspapi.fetch_board',side_effect=RuntimeError('URL apiKey=FAKE_UI_SECRET')):
  app=new_app(new);element(app.button,'Fetch odds & evaluate').click();check(app.run());messages=' '.join(x.value for x in app.error)
  assert 'FAKE_UI_SECRET' not in messages and 'details withheld' in messages
out=new_run(ROOT/'evidence/repairs-20261001');(out/'parity.json').write_text(json.dumps({'manual':rows,'card_comparisons':2,'fake_error_ui_safe':True},indent=2));print('PASS: 18 manual comparisons, 2 slate cards, fake credential UI')
