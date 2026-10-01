import os,sys,json
from pathlib import Path
from evidence_runs import new_run
from contextlib import ExitStack
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from validate_t2_ui import guards,new_app,element,check,select_match
with ExitStack() as stack:
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_REPAIRS':'1'}))
 at=new_app((ROOT/'streamlit_app.py').read_text());select_match(at,'spring-hill','kansas','Home court')
 for mode in ['Player (RAPM)','Hybrid (Elo + lineup adjust)']:
  element(at.radio,'Pricing model').set_value(mode);check(at.run());assert any('without both rosters' in w.value for w in at.warning)
 assert 'unchanged selections can already differ' in element(at.radio,'Pricing model').proto.help
 out=new_run(ROOT/'evidence/t8-20261001')/'player-guards.json';out.open('x').write(json.dumps({'modes':2,'missing_roster_no_crash':True,'help_corrected':True}))
 print('PASS: both player modes gracefully refuse missing roster; help states reference semantics')
