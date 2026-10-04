"""T14 actual UI, disk reload, ID precedence, cloud CAS and source isolation. No IO."""
import base64,copy,json,os,subprocess,tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch,Mock
import pandas as pd
from validate_t2_ui import ROOT,guards,new_app,element,check
from evidence_runs import new_run
import live_team_map as lm
import oddspapi,paste_odds
ratings=pd.read_parquet(ROOT/'app_data/elo_current.parquet');seos=ratings.team.tolist();full=dict(zip(ratings.team,ratings.name_full))
names=oddspapi._participants()
ids={name:pid for pid,name in names.items()}
game=dict(home='Washington Huskies',away='Purdue Boilermakers',home_participant_id=ids['Washington Huskies'],away_participant_id=ids['Purdue Boilermakers'],fixture_id='test-purdue-washington',date='2026-10-04',time='7:00 PM',board_pos=1,markets=[dict(market='ml',side='home',point='',odds=150),dict(market='ml',side='away',point='',odds=-110)])
source=(ROOT/'streamlit_app.py').read_text();baseline=subprocess.check_output(['git','show','aafab84:streamlit_app.py'],text=True)
results={};out=new_run(ROOT/'evidence/t14-20261004')
with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
 guards(stack)
 stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_LIVE_TEAM_MAP':'1','WVB_MAPPING_STORAGE':'local'}))
 path=Path(tmp)/'mapping.json';path.write_text('{}\n');stack.enter_context(patch.object(lm,'MAP_PATH',path))
 stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 fetch=stack.enter_context(patch('oddspapi.fetch_board',return_value=([game],0)))
 stack.enter_context(patch('oddspapi.account',return_value={}))
 app=new_app(source);element(app.button,'Fetch odds & evaluate').click();check(app.run())
 assert app.session_state.best_card.empty
 assert app.selectbox(key='live-map:test-purdue-washington:away').value=='purdue'
 app.selectbox(key='live-map:test-purdue-washington:home').set_value('washington');check(app.run())
 app.button(key='live-map:test-purdue-washington:save').click();check(app.run())
 card=app.session_state.best_card.copy();assert len(card)==2
 assert set(card.home_team)=={'washington'} and set(card.away_team)=={'purdue'}
 persisted=json.loads(path.read_text());assert persisted=={ids['Washington Huskies']:'washington',ids['Purdue Boilermakers']:'purdue'}
 # Recreate app/session, no shared session-state mapping; persisted disk map is sufficient.
 again=new_app(source);element(again.button,'Fetch odds & evaluate').click();check(again.run())
 assert not [b for b in again.button if b.label=='Confirm teams & save']
 pd.testing.assert_frame_equal(card,again.session_state.best_card,check_exact=True)
 renamed={**game,'home':'Unknown changed vendor spelling'}
 assert lm.resolve(renamed,'home',seos,full,persisted)==('washington',1.)
 # Name fallback never auto-persists, duplicate-team confirmation impossible.
 path.write_text('{}\n');third=new_app(source);element(third.button,'Fetch odds & evaluate').click();check(third.run())
 third.selectbox(key='live-map:test-purdue-washington:home').set_value('purdue');check(third.run())
 assert third.button(key='live-map:test-purdue-washington:save').disabled and json.loads(path.read_text())=={}
 # Stale mapping conflict preserves another owner's update.
 path.write_text(json.dumps({ids['Washington Huskies']:'washington-st'}))
 try:lm.save({ids['Washington Huskies']:'washington'},{},seos)
 except lm.MappingError:pass
 else:raise AssertionError('Conflict accepted')
 assert json.loads(path.read_text())[ids['Washington Huskies']]=='washington-st'
 # Gate OFF is exact legacy live output, including an unresolved fixture.
 os.environ['WVB_ENABLE_LIVE_TEAM_MAP']='0'
 old,off=new_app(baseline),new_app(source)
 for target in (old,off):element(target.button,'Fetch odds & evaluate').click();check(target.run())
 pd.testing.assert_frame_equal(old.session_state.best_card,off.session_state.best_card,check_exact=True)
 assert old.session_state.best_unmatched==off.session_state.best_unmatched
 # Paste is exact with gate ON; it never consults the provider-ID store.
 os.environ['WVB_ENABLE_LIVE_TEAM_MAP']='1'
 for target in (old,off):
  element(target.radio,'Odds source').set_value('Paste a board');check(target.run())
  element(target.text_area,'Pasted board').set_value('Purdue +150\nWashington -110')
  element(target.button,'Parse & evaluate').click();check(target.run())
 pd.testing.assert_frame_equal(old.session_state.best_card,off.session_state.best_card,check_exact=True)
 results.update(ui_first_confirm_prices=True,fresh_session_persisted_prices=True,id_precedence=True,conflict_preserves_other_change=True,duplicate_team_refused=True,flag_off_exact=True,paste_exact=True,real_sheet_writes=0,paid_calls=0)
 card.to_csv(out/'purdue-washington-card.csv',index=False)
 # Remote adapter: merge unrelated concurrent IDs, fixed path + blob SHA, no raw errors.
 os.environ['WVB_MAPPING_STORAGE']='github'
 def response(mapping,sha='latest'):return Mock(status_code=200,json=lambda:{'content':base64.b64encode(json.dumps(mapping).encode()).decode(),'sha':sha})
 with patch.object(lm.requests,'get',return_value=response({'99':'texas'})),patch.object(lm.requests,'put',return_value=Mock(status_code=200)) as put:
  saved=lm.save(persisted,{},seos,'test-token')
  assert saved['99']=='texas';body=put.call_args.kwargs['json']
  assert body['sha']=='latest' and body['branch']=='main' and put.call_args.args==(lm.CONTENT_URL,)
  assert json.loads(base64.b64decode(body['content']))==saved
 with patch.object(lm.requests,'get',return_value=response({})),patch.object(lm.requests,'put',return_value=Mock(status_code=409)) as put:
  try:lm.save(persisted,{},seos,'test-token')
  except lm.MappingError as e:assert '409' in str(e)
  else:raise AssertionError('CAS conflict accepted')
  assert put.call_count==1
 results['github_cas_mock']=True
# The provider decoder carries stable IDs without changing best-price / anchor math.
ref={'231':{'marketType':'moneyline','period':'result','outcomes':[{'outcomeId':1,'outcomeName':'1'},{'outcomeId':2,'outcomeName':'2'}]}}
def markets(a,b):
 return {'231':{'outcomes':{str(i):{'players':{'0':{'active':True,'priceAmerican':v}}} for i,v in enumerate([a,b],1)}}}
f={'fixtureId':'123','statusId':0,'startTime':'2026-10-04T23:00:00Z','participant1Id':game['home_participant_id'],'participant2Id':game['away_participant_id'],'bookmakerOdds':{'pinnacle':{'markets':markets(-120,110)},'draftkings':{'markets':markets(105,-125)}}}
response=Mock(status_code=200,json=lambda:[copy.deepcopy(f)])
with patch.object(oddspapi,'_markets_map',return_value=ref),patch.object(oddspapi.safe_http,'get',return_value=response),patch.object(oddspapi.time,'sleep'):
 decoded,n=oddspapi.fetch_board(books=('pinnacle','draftkings'),key='test-only')
 assert decoded[0]['home_participant_id']==game['home_participant_id']
 assert decoded[0]['away_participant_id']==game['away_participant_id'] and decoded[0]['fixture_id']=='123'
 sides={r['side']:r for r in decoded[0]['markets']}
 assert sides['home']['book']=='draftkings' and sides['away']['book']=='pinnacle'
 assert all(r['devig_book']=='pinnacle' for r in sides.values())
 results['provider_ids_and_line_shop']=True
# Full sport map includes international/men's teams; NCAA subset proven by cached tournament fixtures.
fixtures=json.loads((ROOT/'evidence/t3-20261001/extension-1/raw/fixtures.json').read_text())['payload']
pids={str(f[k]) for f in fixtures for k in ('participant1Id','participant2Id')}
pids.update(game[k] for k in ('home_participant_id','away_participant_id'))
cases=[]
for pid in sorted(pids):
 name=names.get(pid,pid);seo,score=paste_odds.match_team(name,seos,full)
 cases.append(dict(participant_id=pid,name=name,matched=seo,score=score,needs_confirmation=not seo or score<.8))
(out/'participant-corpus.json').write_text(json.dumps(cases,indent=2))
results.update(ncaa_participants=len(cases),needs_confirmation=sum(c['needs_confirmation'] for c in cases))
(out/'checks.json').write_text(json.dumps(results,indent=2));print(out);print(json.dumps(results,indent=2))
