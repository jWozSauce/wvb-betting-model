"""Replay a captured real NCAA slate and real historical odds in the T12 UI.
Cached DraftKings closing quotes are re-encoded as paste text (American odds
rounded to integer, the parser's input format); this is not a live BetOnline fetch.
No current betting recommendations or historical strategy test are produced.
"""
import copy
import datetime as dt
import json
import os
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd
from validate_t2_ui import ROOT, guards, new_app, element, check
from evidence_runs import new_run
import manual_board as mb

slate_path=ROOT/'evidence/t12-20261004/real-slate/run-20261004T195743.899221Z-szg1csja/slate.json'
slate=json.loads(slate_path.read_text())
odds_path=ROOT/'evidence/t3-20261001/run-3-corrected-matching/rebuilt_backtest.parquet'
odds=pd.read_parquet(odds_path)
quotes=odds[(odds.date.astype(str)=='2026-09-30') & (odds.matchup=='vanderbilt @ lsu')].copy()
assert len(quotes)==4
american=lambda d: round((d-1)*100 if d>=2 else -100/(d-1))
lines=[]
for side,team in [('away','Vanderbilt'),('home','LSU')]:
 parts=[team]
 for r in quotes[quotes.side==side].itertuples():
  if r.market=='spread':parts.append(f'{float(r.point):+g}')
  parts.append(f'{american(r.close_dec):+d}')
 lines.append(' '.join(parts))
paste='\n'.join(lines)
day=dt.date(2026,9,30)
with ExitStack() as stack:
 guards(stack)
 stack.enter_context(patch.dict(os.environ, {'WVB_ENABLE_MANUAL_BOARD':'1'}))
 fetch=stack.enter_context(patch('schedule_pricing.fetch_slate',return_value=copy.deepcopy(slate)))
 app=new_app((ROOT/'streamlit_app.py').read_text())
 element(app.radio,'Odds source').set_value(mb.SOURCE);check(app.run())
 app.date_input(key='manual_date').set_value(day);check(app.run())
 app.button(key='manual_fetch').click();check(app.run())
 app.text_area(key=f'manual_paste:{day}').set_value(paste);check(app.run())
 app.button(key='manual_parse').click();check(app.run())
 g=mb.paste_odds.parse_board(paste)[0][0];bid=next(mb.board_ids([g]))
 app.checkbox(key=f'manual:{day}:{bid}:confirm').check();check(app.run())
 app.button(key='manual_price').click();check(app.run())
 card=app.session_state.best_card
 assert len(card)==4 and set(card.home_team)=={'lsu'} and set(card.away_team)=={'vanderbilt'}
 assert fetch.call_count==1
 state=app.session_state.manual_boards[str(day)]
 assert state['counts']=={'matched':1}
 out=new_run(ROOT/'evidence/t12-20261004/real-replay')
 card.to_csv(out/'card.csv',index=False)
 pd.DataFrame(state['match_table']).to_csv(out/'match-table.csv',index=False)
 (out/'board.txt').write_text(paste)
 quotes[['date','book','market','side','point','close_dec','fixture','matchup']].to_csv(out/'source-quotes.csv',index=False)
 (out/'provenance.json').write_text(json.dumps(dict(slate=str(slate_path.relative_to(ROOT)),
  quotes=str(odds_path.relative_to(ROOT)),book='draftkings',format='American odds rounded to integer; reconstructed paste',
  date=str(day),matched=1,excluded=0,unmatched=0,schedule_fetched=slate['fetched'],
  schedule_unmatched=slate['fetched']-1,markets=4,external_io='mocked; earlier free NCAA capture',
  real_paid_calls=0,real_sheet_writes=0,ratings='current snapshot, not a historical model backtest'),indent=2))
 print(pd.DataFrame(state['match_table']).to_string(index=False))
 print(card[['matchup','market','side','odds','model_prob','blend_prob','edge','stake']].to_string(index=False))
