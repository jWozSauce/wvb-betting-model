"""Actual UI regressions with external calls and Sheets replaced by mocks."""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import os,sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from validate_t2_ui import guards,new_app,element,check
out=ROOT/'evidence/t8-20261001/run-2';out.mkdir(parents=True,exist_ok=False)
with ExitStack() as stack:
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}));stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 # Override the safety guard with a capture-only mock, never a worksheet.
 log=stack.enter_context(patch('bet_log.log_bets',return_value=1))
 at=new_app((ROOT/'streamlit_app.py').read_text().replace('absents_map = load_availability()', 'absents_map = {}')); element(at.radio,'Odds source').set_value('Paste a board');check(at.run())
 element(at.text_area,'Pasted board').set_value('Wisconsin -110\nNebraska -110')
 def evaluate():element(at.button,'Parse & evaluate').click();check(at.run())
 evaluate();old=at.session_state.best_card.stake.sum();assert old>0
 checks=[]
 edits=[('number_input','Bankroll',1000.),('checkbox','Conservative (p20 of posterior)',False),('number_input','Model weight in market blend',.4),('number_input','Min edge',.025),('selectbox','Venue for ALL games on this slate','True toss-up (symmetrized)'),('number_input','Kelly fraction',.25),('number_input','Edge cap',.04)]
 for kind,label,value in edits:
  element(getattr(at,kind),label).set_value(value);check(at.run())
  assert 'best_card' not in at.session_state,label
  assert not any(b.label in ['Log selected bets','📋 Track full card (paper)'] for b in at.button),label
  evaluate();checks.append(label)
  if label=='Bankroll':assert at.session_state.best_card.stake.sum()==2*old
 # Returned to a known qualifying baseline, then capture actual paper logging.
 element(at.number_input,'Min edge').set_value(.02);element(at.selectbox,'Venue for ALL games on this slate').set_value('Home court');check(at.run());evaluate()
 context=dict(at.session_state.best_context)
 element(at.button,'📋 Track full card (paper)').click();check(at.run())
 assert log.called and log.call_args.args[0]
 for row in log.call_args.args[0]:
  for key,value in context.items():assert row[key]==value,(key,row[key],value)
 result={'invalidated_controls':checks,'baseline_stake':old,'bankroll_doubling_after_reevaluate':2*old,'mock_logged_rows':len(log.call_args.args[0]),'logged_snapshot_exact':True,'real_writes':0}
 (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
