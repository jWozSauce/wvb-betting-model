"""T15 offline gate preparation: no paid IO; real new-default fetch remains unapproved."""
import copy,json,os
from contextlib import ExitStack
from unittest.mock import Mock,patch
from validate_t2_ui import ROOT,guards,new_app,element,check
from evidence_runs import new_run
import oddspapi,kelly
ref={'231':{'marketType':'moneyline','period':'result','outcomes':[{'outcomeId':1,'outcomeName':'1'},{'outcomeId':2,'outcomeName':'2'}]}}
def markets(a,b):return {'231':{'outcomes':{str(i):{'players':{'0':{'active':True,'priceAmerican':v}}} for i,v in enumerate([a,b],1)}}}
f={'fixtureId':'123','statusId':0,'startTime':'2026-10-04T23:00:00Z','participant1Id':1,'participant2Id':2,'bookmakerOdds':{'pinnacle':{'markets':markets(-120,110)},'draftkings':{'markets':markets(105,-125)},'bovada.lv':{'markets':markets(120,115)}}}
with ExitStack() as stack:
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_BOOK_SELECTION':'1','WVB_ENABLE_LIVE_TEAM_MAP':'1'}))
 stack.enter_context(patch.object(oddspapi,'_markets_map',return_value=ref))
 stack.enter_context(patch.object(oddspapi,'_participants',return_value={'1':'Nebraska','2':'Kansas'}))
 req=stack.enter_context(patch.object(oddspapi.safe_http,'get',return_value=Mock(status_code=200,json=lambda:[copy.deepcopy(f)])))
 games,n=oddspapi.fetch_board(key='offline-only');assert n==5 and req.call_count==5
 sides={r['side']:r for r in games[0]['markets']}
 assert all(r['book']=='bovada.lv' for r in sides.values())
 assert all(r['devig_book']=='pinnacle' for r in sides.values())
 assert sides['home']['mkt_prob']==round(kelly.vig_free_probs(-120,110)[0],4)
 os.environ['WVB_ENABLE_BOOK_SELECTION']='0';assert oddspapi.default_books()==oddspapi.LEGACY_BOOKS
 os.environ['WVB_ENABLE_BOOK_SELECTION']='1'
 fetch=stack.enter_context(patch('oddspapi.fetch_board',return_value=(games,5)))
 stack.enter_context(patch('oddspapi.account',return_value={}))
 stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 app=new_app((ROOT/'streamlit_app.py').read_text())
 assert app.multiselect(key='api_books').value==list(oddspapi.BOOKS)
 element(app.button,'Fetch odds & evaluate').click();check(app.run());assert fetch.call_count==1
 element(app.button,'Fetch odds & evaluate').click();check(app.run());assert fetch.call_count==1
 app.multiselect(key='api_books').set_value(['bovada.lv','pinnacle']);check(app.run())
 assert 'best_card' not in app.session_state and 'live_games' not in app.session_state and fetch.call_count==1
 element(app.button,'Fetch odds & evaluate').click();check(app.run())
 assert fetch.call_count==2 and fetch.call_args.kwargs['books']==('pinnacle','bovada.lv')
 app.multiselect(key='api_books').set_value([]);check(app.run())
 assert element(app.button,'Fetch odds & evaluate').disabled and fetch.call_count==2
out=new_run(ROOT/'evidence/t15-20261004/offline')
checks=dict(bovada_best_lines=True,pinnacle_anchor_preserved=True,default_off_legacy_four=True,default_on_five=True,selection_order_sharp_first=True,cache_by_books=True,selection_change_no_fetch=True,empty_selection_no_fetch=True,real_paid_calls=0,real_sheet_writes=0)
(out/'checks.json').write_text(json.dumps(checks,indent=2));print(out);print(json.dumps(checks,indent=2))
