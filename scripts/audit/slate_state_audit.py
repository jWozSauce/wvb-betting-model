"""Show stale stakes after a sidebar edit without touching any real logs."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/validation'))
from validate_t2_ui import guards,new_app,element,check
out=ROOT/'evidence/t1-20261001/stale_slate.json'
with ExitStack() as stack:
 guards(stack);stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 at=new_app((ROOT/'streamlit_app.py').read_text())
 element(at.radio,'Odds source').set_value('Paste a board');check(at.run())
 element(at.text_area,'Pasted board').set_value('Wisconsin -110\nNebraska -110')
 element(at.button,'Parse & evaluate').click();check(at.run())
 old=at.session_state.best_card.copy();assert old.stake.sum()>0
 element(at.number_input,'Bankroll').set_value(1000.);check(at.run())
 stale=at.session_state.best_card.copy();pd.testing.assert_frame_equal(old,stale)
 element(at.button,'Parse & evaluate').click();check(at.run())
 refreshed=at.session_state.best_card.copy()
 record={'initial_bankroll':500,'updated_bankroll':1000,'initial_stakes':old.stake.tolist(),
         'stakes_after_sidebar_edit':stale.stake.tolist(),'stakes_after_re_evaluate':refreshed.stake.tolist(),
         'stakes_remain_stale':old.equals(stale),'log_context_risk':'pricing_context reads current sidebar globals when logging previously priced card; no log button was pressed'}
 with out.open('x') as f:json.dump(record,f,indent=2)
 print(json.dumps(record,indent=2))
