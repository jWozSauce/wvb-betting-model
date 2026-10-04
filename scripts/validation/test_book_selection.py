"""T15 stage-2 offline verification; no real odds, GitHub, AI or Sheet calls."""
import copy,json,os,tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import Mock,patch
from validate_t2_ui import ROOT,guards,new_app,element,check
from evidence_runs import new_run
import oddspapi,kelly
ref={'231':{'marketType':'moneyline','period':'result','outcomes':[{'outcomeId':1,'outcomeName':'1'},{'outcomeId':2,'outcomeName':'2'}]}}
def markets(a,b):return {'231':{'outcomes':{str(i):{'players':{'0':{'active':True,'priceAmerican':v}}} for i,v in enumerate([a,b],1)}}}
f={'fixtureId':'123','statusId':0,'startTime':'2026-10-04T23:00:00Z','participant1Id':1,'participant2Id':2,'bookmakerOdds':{'pinnacle':{'markets':markets(-120,110)},'draftkings':{'markets':markets(105,-125)},'hardrockbet':{'markets':markets(120,115)},'sbobet':{'markets':markets(-130,105)},'1xbet':{'markets':markets(500,500)},'bwin':{'markets':markets(400,400)}}}
with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_BOOK_SELECTION':'1','WVB_ENABLE_LIVE_TEAM_MAP':'1'}))
 stack.enter_context(patch.object(oddspapi,'_markets_map',return_value=ref))
 stack.enter_context(patch.object(oddspapi,'_participants',return_value={'1':'Nebraska','2':'Kansas'}))
 req=stack.enter_context(patch.object(oddspapi.safe_http,'get',return_value=Mock(status_code=200,json=lambda:[copy.deepcopy(f)])))
 games,n=oddspapi.fetch_board(key='offline-only');assert n==5 and req.call_count==5
 assert [c.kwargs['params']['bookmaker'] for c in req.call_args_list]==list(oddspapi.BOOKS)
 sides={r['side']:r for r in games[0]['markets']}
 assert all(r['book']=='hardrockbet' for r in sides.values())
 assert all(r['devig_book']=='sbobet' for r in sides.values())
 assert sides['home']['mkt_prob']==round(kelly.vig_free_probs(-130,105)[0],4)
 from scripts.validation.live_book_gate import verify_prices
 cache={b:{'status':200,'payload':[copy.deepcopy(f)]} for b in oddspapi.BOOKS}
 assert verify_prices(games,cache)==2
 corrupted=copy.deepcopy(games);corrupted[0]['markets'][0]['book']='1xbet'
 try:verify_prices(corrupted,cache)
 except AssertionError:pass
 else:raise AssertionError('Live verifier accepted an information-only best line')
 # A manually selected sharp book anchors ahead of DK, irrespective of click order.
 selected=oddspapi.order_books(['hardrockbet','draftkings','pinnacle'])
 assert selected==('pinnacle','draftkings','hardrockbet')
 extra,_=oddspapi.fetch_board(books=selected,key='offline-only')
 assert all(r['book']=='hardrockbet' and r['devig_book']=='pinnacle' for r in extra[0]['markets'])
 os.environ['WVB_ENABLE_BOOK_SELECTION']='0';assert oddspapi.default_books()==oddspapi.LEGACY_BOOKS
 os.environ['WVB_ENABLE_BOOK_SELECTION']='1'
 # Use representative provider-schema catalog in a temp dir; no invented production catalog.
 stack.enter_context(patch.object(oddspapi,'HERE',Path(tmp)))
 (Path(tmp)/'app_data').mkdir();catalog=Path(tmp)/'app_data/oddspapi_bookmakers.json'
 assert oddspapi.available_books()[1] is False
 raw=[{'slug':s,'bookmakerName':s} for s in ['bovada.lv','pinnacle','betonline.ag',*oddspapi.BOOKS]]
 catalog.write_text(json.dumps(raw));assert oddspapi.available_books()==(tuple(sorted(r['slug'] for r in raw)),True)
 fetch=stack.enter_context(patch('oddspapi.fetch_board',return_value=(games,5)))
 stack.enter_context(patch('oddspapi.account',return_value={}))
 stack.enter_context(patch('vbstats.venues.slate_venues',return_value={}))
 app=new_app((ROOT/'streamlit_app.py').read_text())
 assert app.multiselect(key='api_books').value==list(oddspapi.BOOKS)
 assert 'bovada.lv' in app.multiselect(key='api_books').options
 assert 'bovada.lv' not in app.multiselect(key='api_books').value
 element(app.button,'Fetch odds & evaluate').click();check(app.run());assert fetch.call_count==1
 element(app.button,'Fetch odds & evaluate').click();check(app.run());assert fetch.call_count==1
 app.multiselect(key='api_books').set_value(['hardrockbet','pinnacle']);check(app.run())
 assert 'best_card' not in app.session_state and 'live_games' not in app.session_state and fetch.call_count==1
 element(app.button,'Fetch odds & evaluate').click();check(app.run())
 assert fetch.call_count==2 and fetch.call_args.kwargs['books']==('pinnacle','hardrockbet')
 app.multiselect(key='api_books').set_value(['sbobet','1xbet']);check(app.run())
 assert element(app.button,'Fetch odds & evaluate').disabled and fetch.call_count==2
 app.multiselect(key='api_books').set_value([]);check(app.run())
 assert element(app.button,'Fetch odds & evaluate').disabled and fetch.call_count==2
 catalog.write_text('{}')
 try:oddspapi.available_books()
 except ValueError:pass
 else:raise AssertionError('Malformed catalog accepted')
 # Actual workspace lacking catalog is explicitly labelled rather than called complete.
 catalog.unlink();fallback=new_app((ROOT/'streamlit_app.py').read_text())
 assert any('Full bookmaker catalog is unavailable' in e.value for e in fallback.caption)
 assert fallback.multiselect(key='api_books').value==list(oddspapi.BOOKS)
out=new_run(ROOT/'evidence/t15-20261004/offline')
checks=dict(hardrock_best_lines=True,sbobet_default_anchor=True,international_odds_never_actionable=True,anchor_only_fetch_disabled=True,optional_pinnacle_anchor=True,default_off_legacy_four=True,default_on_five_requests=True,catalog_consumed_without_fetch=True,missing_catalog_label=True,invalid_catalog_rejected=True,nondefault_books_not_auto_selected=True,cache_by_books=True,selection_change_no_fetch=True,empty_selection_no_fetch=True,real_paid_calls=0,real_sheet_writes=0)
(out/'checks.json').write_text(json.dumps(checks,indent=2));print(out);print(json.dumps(checks,indent=2))
