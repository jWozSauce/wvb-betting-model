"""T12 actual UI, shared evaluator parity, orientation, cache and state regressions.
All network, AI and real sheet access blocked. Captured NCAA slate; synthetic board.
"""
import copy
import datetime as dt
import json
import os
import subprocess
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd
from validate_t2_ui import ROOT, guards, new_app, element, check
from evidence_runs import new_run
import manual_board as mb
import board_pricing as bp
from vbstats import model

source = (ROOT/'streamlit_app.py').read_text()
baseline = subprocess.check_output(['git','show','ef13b81:streamlit_app.py'],text=True)
slate = json.loads((ROOT/'evidence/t2-20261001/full-slate-1/slate.json').read_text())
rated = pd.read_parquet(ROOT/'app_data/elo_current.parquet')
names = dict(zip(rated.team, rated.name_full))
# Three named games with unique confident proposals in the captured full slate.
rows = []
for r in slate['priced']:
 g = {'away': names[r['away']], 'home': names[r['home']]}
 if mb.proposal(g, slate['priced'], rated)[0] == r['contest_id']:
  rows.append(r)
 if len(rows) == 3: break
assert len(rows) == 3
# Include spreads and totals as well as moneylines; odds deliberately give qualifying bets.
paste = '\n'.join(f"{names[r['away']]} +1.5 -110 o3.5 -115 +200\n{names[r['home']]} -1.5 -110 u3.5 -105 +200" for r in rows)
games = mb.paste_odds.parse_board(paste)[0]
assert len(games) == 3 and all(len(g['markets']) == 6 for g in games)
bids = list(mb.board_ids(games)); day = dt.date.fromisoformat(slate['date'])
prefix = lambda i: f'manual:{day}:{bids[i]}'
checks={}; parity=[]
with ExitStack() as stack:
 guards(stack)
 stack.enter_context(patch.dict(os.environ, dict(os.environ)))
 os.environ.pop('WVB_ENABLE_MANUAL_BOARD',None)
 fetch = stack.enter_context(patch('schedule_pricing.fetch_slate',return_value=copy.deepcopy(slate)))
 stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 log = stack.enter_context(patch('bet_log.log_bets',return_value=1))
 app = new_app(source)
 element(app.radio,'Odds source').set_value(mb.SOURCE);check(app.run())
 app.date_input(key='manual_date').set_value(day);check(app.run())
 # Board-first then schedule must make proposals without losing the paste.
 app.text_area(key=f'manual_paste:{day}').set_value(paste);check(app.run())
 app.button(key='manual_parse').click();check(app.run())
 assert app.button(key='manual_price').disabled
 app.button(key='manual_fetch').click();check(app.run())
 for i,r in enumerate(rows):
  assert app.selectbox(key=prefix(i)+':fixture').value==r['contest_id']
  app.selectbox(key=f"manual_venue:{day}:{r['contest_id']}:{bids[i]}").set_value('Home court')
  app.checkbox(key=prefix(i)+':confirm').check();check(app.run())
 assert app.session_state.manual_boards[str(day)]['counts']=={'matched':3}
 bp.evaluate_game.clear()
 with patch.object(model,'set_score_probs',wraps=model.set_score_probs) as compute:
  app.button(key='manual_price').click();check(app.run())
  first_calls=compute.call_count
  assert first_calls>0
 assert log.call_count==0
 initial=app.session_state.best_card.copy()
 assert len(initial)==18
 # Compare existing paste source against pre-T12 implementation and manual path.
 old, pasted = new_app(baseline),new_app(source)
 for target in (old,pasted):
  element(target.radio,'Odds source').set_value('Paste a board');check(target.run())
  element(target.text_area,'Pasted board').set_value(paste)
  element(target.button,'Parse & evaluate').click();check(target.run())
 pd.testing.assert_frame_equal(old.session_state.best_card,pasted.session_state.best_card,check_exact=True)
 paste_card = pasted.session_state.best_card.copy()
 with patch('oddspapi.fetch_board', return_value=(games, 0)), patch('oddspapi.account', return_value={}):
  for target in (old,pasted):
   element(target.radio,'Odds source').set_value(next(o for o in element(target.radio,'Odds source').options if o.startswith('Live API')));check(target.run())
   element(target.button,'Fetch odds & evaluate').click();check(target.run())
  pd.testing.assert_frame_equal(old.session_state.best_card,pasted.session_state.best_card,check_exact=True)
 numeric=['model_prob','mkt_prob','blend_prob','p20','edge','stake','fair_odds','market','side','point','bet','odds','⚕ absent','⚕opp']
 pd.testing.assert_frame_equal(initial[numeric],paste_card[numeric],check_exact=True)
 parity=initial[['matchup','market','side','model_prob','blend_prob','p20','edge','stake']].to_dict('records')
 with patch.object(model,'set_score_probs',wraps=model.set_score_probs) as compute:
  app.button(key='manual_price').click();check(app.run());assert compute.call_count==0
 # Venue change invalidates existing prices/log controls and recomputes exactly one game.
 app.selectbox(key=f"manual_venue:{day}:{rows[0]['contest_id']}:{bids[0]}").set_value('Neutral (host/label matters)');check(app.run())
 assert 'best_card' not in app.session_state
 with patch.object(model,'set_score_probs',wraps=model.set_score_probs) as compute:
  app.button(key='manual_price').click();check(app.run());venue_calls=compute.call_count
 assert venue_calls==first_calls//3,(venue_calls,first_calls)
 changed=app.session_state.best_card.copy()
 pd.testing.assert_frame_equal(initial.iloc[6:].reset_index(drop=True),changed.iloc[6:].reset_index(drop=True),check_exact=True)
 # Capture shared paper path only; never a real worksheet.
 element(app.button,'📋 Track full card (paper)').click();check(app.run())
 assert log.called and log.call_args.args[0]
 for rec in log.call_args.args[0]:
  assert rec['game_date']==str(day)
  r=next(r for r in rows if r['home']==rec['home_team'] and r['away']==rec['away_team'])
  assert rec['venue_mode']==('neutral-host' if r==rows[0] else 'home')
  assert rec['game_time']==mb.schedule.game_time(r)
 # Reverse first board game, including its spreads; map side only, preserving picked handicap.
 reversed_paste='\n'.join([f"{names[rows[0]['home']]} -1.5 -110 u3.5 -105 +200",f"{names[rows[0]['away']]} +1.5 -110 o3.5 -115 +200"]+paste.splitlines()[2:])
 app.text_area(key=f'manual_paste:{day}').set_value(reversed_paste);check(app.run())
 assert 'best_card' not in app.session_state and app.button(key='manual_price').disabled
 app.button(key='manual_parse').click();check(app.run())
 revbid=list(mb.board_ids(mb.paste_odds.parse_board(reversed_paste)[0]))[0]
 revprefix=f'manual:{day}:{revbid}'
 assert app.selectbox(key=revprefix+':first').value==rows[0]['home']
 app.checkbox(key=revprefix+':confirm').check();check(app.run())
 app.button(key='manual_price').click();check(app.run())
 rev=app.session_state.best_card
 assert 'book lists reversed' in set(rev.book_orientation)
 cols=numeric+['home_team','away_team','game_date']
 pd.testing.assert_frame_equal(changed.iloc[:6][cols].sort_values(['market','side']).reset_index(drop=True),
                              rev.iloc[:6][cols].sort_values(['market','side']).reset_index(drop=True),check_exact=True)
 # Duplicate schedule pairing must block the price action.
 app.selectbox(key=prefix(1)+':fixture').set_value(rows[0]['contest_id']);check(app.run())
 assert app.selectbox(key=prefix(1)+':first').value is None
 app.selectbox(key=prefix(1)+':first').set_value(rows[0]['away']);check(app.run())
 app.checkbox(key=prefix(1)+':confirm').check();check(app.run())
 assert app.button(key='manual_price').disabled and 'best_card' not in app.session_state
 # Exclusion reconciles and survives independent reloads, date and source switches.
 app.selectbox(key=prefix(1)+':fixture').set_value(mb.EXCLUDE);check(app.run())
 assert app.session_state.manual_boards[str(day)]['counts']=={'matched':2,'excluded':1}
 app.button(key='manual_fetch').click();check(app.run())
 app.button(key='manual_parse').click();check(app.run())
 assert app.selectbox(key=prefix(1)+':fixture').value==mb.EXCLUDE
 element(app.radio,'Odds source').set_value('Paste a board');check(app.run())
 element(app.radio,'Odds source').set_value(mb.SOURCE);check(app.run())
 assert app.date_input(key='manual_date').value==day
 assert app.selectbox(key=prefix(1)+':fixture').value==mb.EXCLUDE
 app.date_input(key='manual_date').set_value(day-dt.timedelta(days=1));check(app.run())
 app.date_input(key='manual_date').set_value(day);check(app.run())
 assert app.selectbox(key=prefix(1)+':fixture').value==mb.EXCLUDE
 assert fetch.call_count==2 # only the two explicit schedule fetches
 # Editing a confirmed match to another valid game resets orientation and confirmation.
 app.selectbox(key=prefix(1)+':fixture').set_value(slate['priced'][10]['contest_id']);check(app.run())
 assert app.selectbox(key=prefix(1)+':first').value is None
 assert not app.checkbox(key=prefix(1)+':confirm').value
 # Unknown book names are repaired by explicit pairing + orientation.
 newrow=slate['priced'][10]
 app.selectbox(key=prefix(1)+':first').set_value(newrow['away']);check(app.run())
 app.checkbox(key=prefix(1)+':confirm').check();check(app.run())
 with patch.object(model,'set_score_probs',wraps=model.set_score_probs) as compute:
  app.button(key='manual_price').click();check(app.run());rematch_calls=compute.call_count
 assert rematch_calls in (501,1002),rematch_calls
 rematched=app.session_state.best_card
 assert set(rematched.iloc[6:12].home_team)=={newrow['home']}
 assert set(rematched.iloc[6:12].away_team)=={newrow['away']}
 assert fetch.call_count==2
 state=app.session_state.manual_boards[str(day)]
 assert sum(state['counts'].values())==3
 # Explicit zero hides the accepted source for rollback.
 os.environ['WVB_ENABLE_MANUAL_BOARD']='0'
 off=new_app(source);assert mb.SOURCE not in element(off.radio,'Odds source').options
 checks=dict(exact_existing_paste=True,exact_existing_live_api=True,one_rematch_model_calls=rematch_calls,three_game_manual_parity=True,reversed_all_markets=True,
             confirmation_required=True,duplicates_blocked=True,counts_reconcile=True,
             independent_reloads_preserve_decisions=True,source_date_state=True,accepted_default_on=True,explicit_zero_rollback=True,
             first_price_model_calls=first_calls,one_venue_change_model_calls=venue_calls,
             unchanged_game_rows_exact=True,schedule_fetches=fetch.call_count,
             mock_logged_rows=len(log.call_args.args[0]),real_writes=0,real_paid_calls=0)
 out=new_run(ROOT/'evidence/t12-20261004')
 (out/'summary.json').write_text(json.dumps(checks,indent=2))
 (out/'parity.json').write_text(json.dumps(parity,indent=2))
 (out/'match-table.json').write_text(json.dumps(state['match_table'],indent=2))
 initial.to_csv(out/'card.csv',index=False)
 (out/'synthetic-board.txt').write_text(paste)
 print(json.dumps(checks,indent=2))
