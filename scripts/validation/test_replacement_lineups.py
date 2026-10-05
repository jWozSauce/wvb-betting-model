"""T13 replacement math, no-edit identity, four benchmark removals and actual UI."""
import copy
import io
import hashlib
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from unittest.mock import patch
import numpy as np
import pandas as pd
from validate_t2_ui import ROOT, guards, new_app, element, check, board, select_match
from evidence_runs import new_run
sys.path.insert(0,str(ROOT/'scripts/audit'))
import player_model_audit as audit
from vbstats import rapm_price as rp

current_rapm,current_ratings,current_meta,params=audit.data()
# Dated acceptance benchmark: daily ratings updates can remove the very player
# this benchmark must deselect (Watson left the latest default lineup).
BENCHMARK_REF='aafab84'
def snapshot(name):
 return subprocess.check_output(['git','show',f'{BENCHMARK_REF}:app_data/{name}'],cwd=ROOT)
rapm=pd.read_parquet(io.BytesIO(snapshot('rapm.parquet')))
ratings=pd.read_parquet(io.BytesIO(snapshot('elo_current.parquet'))).set_index('team')
meta=json.loads(snapshot('rapm_meta.json'))
read_parquet=pd.read_parquet
json_load=json.load
def benchmark_parquet(path,*args,**kwargs):
 if str(path).endswith('/app_data/rapm.parquet'):return rapm.copy(deep=True)
 if str(path).endswith('/app_data/elo_current.parquet'):return ratings.reset_index().copy(deep=True)
 return read_parquet(path,*args,**kwargs)
def benchmark_json(f,*args,**kwargs):
 if str(getattr(f,'name','')).endswith('/app_data/rapm_meta.json'):return copy.deepcopy(meta)
 return json_load(f,*args,**kwargs)
protected=['app_data/rapm.parquet','app_data/rapm_meta.json','app_data/model_params.json']
hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in protected}
source=(ROOT/'streamlit_app.py').read_text()
baseline=subprocess.check_output(['git','show','7941eb5:streamlit_app.py'],text=True)
results=[];labels=[]
for home,away,player in audit.CASES:
 hrows=rapm[rapm.team==home].sort_values(['sets_started_cur','recv'],ascending=False).to_dict('records')
 arows=rapm[rapm.team==away].sort_values(['sets_started_cur','recv'],ascending=False).to_dict('records')
 initial=audit.defaults(hrows);asel=audit.defaults(arows);initial.add(player)
 selected=initial-{player}
 rows,names,notes=rp.replacement_lineup(hrows,selected,initial)
 assert len(notes)==1
 note=notes[0]
 # Independent slot arithmetic, not the assembly implementation.
 original=next(r for r in hrows if r['player']==player)
 pool=[r for r in hrows if r['player'] not in initial and r['position']==original['position'] and (r['serve'] or r['recv'])
       and r['sets_started_cur'] < max(x['sets_started_cur'] for x in hrows)/2]
 expected_sv=float(np.mean([r['serve'] for r in pool]));expected_rc=float(np.mean([r['recv'] for r in pool]))
 assert note['tier']=='position bench'
 assert note['serve']==expected_sv and note['recv']==expected_rc
 weights={r['player']:6*(r['sets_started_cur']+1)/sum(v['sets_started_cur']+1 for v in hrows if v['player'] in initial) for r in hrows if r['player'] in initial}
 for phase in ['serve','recv']:
  val=sum(weights[r['player']]*(note[phase] if r['player']==player else r[phase]) for r in hrows if r['player'] in initial)
  got=rp.lineup_strength(rows,names)[0 if phase=='serve' else 1]
  assert np.isclose(val,got,atol=1e-15)
 # Reference computation must continue to see original rows, not synthetic rows.
 old_values=audit.values
 def changed_values(rs,sel):
  if rs is hrows and set(sel)==selected:
   return np.array(rp.replacement_strength(rs,sel,initial)[0][:2])
  return old_values(rs,sel)
 row={'team':home,'player':player,'tier':note['tier'],'replacement_serve':note['serve'],
      'replacement_recv':note['recv'],'replacement_pts_per_set':note['impact_per_set']}
 for mode in ['player','hybrid']:
  before=audit.distribution(home,away,hrows,arows,initial,asel,ratings,meta,params,mode)
  old=audit.distribution(home,away,hrows,arows,selected,asel,ratings,meta,params,mode)
  with patch.object(audit,'values',changed_values):
   new=audit.distribution(home,away,hrows,arows,selected,asel,ratings,meta,params,mode)
  row[mode+'_before']=float(sum(before[:3]));row[mode+'_redistribution']=float(sum(old[:3]));row[mode+'_replacement']=float(sum(new[:3]))
  if player in ['Teraya Sigler','Ayanna Watson']:
   assert row[mode+'_replacement']<=row[mode+'_before'],row
 results.append(row);labels.append(note)
# Fifth label: a position without bench members falls back to overall bench.
hrows=rapm[rapm.team=='nebraska'].sort_values(['sets_started_cur','recv'],ascending=False).to_dict('records')
initial=audit.defaults(hrows)
_,note=rp.replacement_strength(hrows,initial-{'Ryan Hunter'},initial)
assert note[0]['tier']=='team bench'
assert not {'Bergen Reilly','Virginia Adriano'} & set(note[0]['members'])
labels+=note
# No available rated bench: a rotation-only team uses zero coefficients, keeps six shares.
only=[dict(player='A',position='OH',serve=.02,recv=.01,sets_started_cur=4),
      dict(player='B',position='S',serve=.01,recv=.02,sets_started_cur=2)]
strength,notes=rp.replacement_strength(only+[dict(player='Unrated',position='OH',serve=0.,recv=0.,sets_started_cur=0)],{'B'},{'A','B'})
assert notes[0]['tier']=='league average' and notes[0]['serve']==notes[0]['recv']==0
assert strength[:2]==rp.lineup_strength([dict(only[0],serve=0.,recv=0.),only[1]],{'A','B'})[:2]
# The Q9 cutoff is strict; a fitted player exactly at half is not eligible.
cutoff_rows = [dict(player='Starter',position='OH',serve=.02,recv=.01,sets_started_cur=10),
               dict(player='Half',position='OH',serve=.5,recv=.5,sets_started_cur=5),
               dict(player='Low',position='OH',serve=.003,recv=.002,sets_started_cur=4)]
_, boundary = rp.replacement_strength(cutoff_rows,set(),{'Starter'})
assert boundary[0]['members']==['Low'] and boundary[0]['serve']==.003
# Explicit substitute takes the removed slot's weight, rather than both slot and own minutes.
actual=[*only,dict(player='C',position='OH',serve=.005,recv=.006,sets_started_cur=0)]
rs,names,ns=rp.replacement_lineup(actual,{'B','C'},{'A','B'})
assert len(rs)==2 and ns[0]['tier']=='selected player' and ns[0]['target']=='C'
assert rp.lineup_strength(rs,names)==rp.lineup_strength([dict(only[0],serve=.005,recv=.006),only[1]],{'A','B'})
# Bit-exact untouched and full-roster selection for both weighting modes.
for team in rapm.team.unique():
 rs=rapm[rapm.team==team].to_dict('records');init=audit.defaults(rs)
 for sel in [init,{r['player'] for r in rs}]:
  for weighted in [True,False]:
   got,notes=rp.replacement_strength(rs,sel,init,weighted)
   assert got==rp.lineup_strength(rs,sel,weighted) and not notes
# Current production coefficients also preserve exact untouched arithmetic.
for team in current_rapm.team.unique():
 rs=current_rapm[current_rapm.team==team].to_dict('records');init=audit.defaults(rs)
 for sel in [init,{r['player'] for r in rs}]:
  for weighted in [True,False]:
   got,notes=rp.replacement_strength(rs,sel,init,weighted)
   assert got==rp.lineup_strength(rs,sel,weighted) and not notes
with ExitStack() as stack:
 stack.enter_context(patch('pandas.read_parquet',side_effect=benchmark_parquet))
 stack.enter_context(patch('json.load',side_effect=benchmark_json))
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_REPLACEMENT_LINEUPS':'1'}))
 old,new=new_app(baseline),new_app(source)
 for row in results:
  home=row['team'];player=row['player']
  for app in (old,new):select_match(app,home,'kansas','Home court')
  for mode,ui in [('player','Player (RAPM)'),('hybrid','Hybrid (Elo + lineup adjust)')]:
   for app in (old,new):
    element(app.radio,'Pricing model').set_value(ui);check(app.run())
    for team in (home,'kansas'):
     rs=rapm[rapm.team==team].to_dict('records')
     app.multiselect(key=f'lineup_{team}').set_value(sorted(audit.defaults(rs)))
    check(app.run())
   element(new.radio,'Removed minutes go to').set_value('replacement-level sub (default)');check(new.run())
   pd.testing.assert_frame_equal(board(old),board(new),check_exact=True)
   selected=list(new.multiselect(key=f'lineup_{home}').value)
   assert player in selected
   for app in (old,new):
    app.multiselect(key=f'lineup_{home}').set_value([p for p in selected if p!=player]);check(app.run())
   assert board(new).iloc[0]['prob']==round(row[mode+'_replacement'],4),(player,mode)
   note=next(n for n in labels if n['player']==player)
   expected=f"{home}: {player} → {note['target']} ({note['impact_per_set']:+.2f} pts/set)"
   assert expected in [m.value for m in new.markdown]
   element(new.radio,'Removed minutes go to').set_value('remaining selected players');check(new.run())
   pd.testing.assert_frame_equal(board(old),board(new),check_exact=True)
 # Full roster hybrid and player are exactly the previous app (including reference behavior).
 for ui in ['Player (RAPM)','Hybrid (Elo + lineup adjust)']:
  for app in (old,new):
   select_match(app,'nebraska','kansas','Home court')
   element(app.radio,'Pricing model').set_value(ui);check(app.run())
   for team in ('nebraska','kansas'):app.multiselect(key=f'lineup_{team}').set_value(rapm[rapm.team==team].player.tolist())
   check(app.run())
  element(new.radio,'Removed minutes go to').set_value('replacement-level sub (default)');check(new.run())
  pd.testing.assert_frame_equal(board(old),board(new),check_exact=True)
 # Fifth displayed label.
 app=new_app(source);select_match(app,'nebraska','kansas','Home court')
 element(app.radio,'Pricing model').set_value('Player (RAPM)');check(app.run())
 sel=list(app.multiselect(key='lineup_nebraska').value)
 app.multiselect(key='lineup_nebraska').set_value([p for p in sel if p!='Ryan Hunter']);check(app.run())
 n=labels[-1];assert f"nebraska: Ryan Hunter → {n['target']} ({n['impact_per_set']:+.2f} pts/set)" in [m.value for m in app.markdown]
 # Actual selected replacement overrides the synthetic UI and its calculations.
 initial=audit.defaults(hrows);removed='Teraya Sigler';added='Skyler Pierce'
 app.multiselect(key='lineup_nebraska').set_value(sorted(initial-{removed}|{added}));check(app.run())
 assert any(f'{removed} → {added}' in m.value for m in app.markdown)
 # Explicit rollback => old UI and removal arithmetic after default-on acceptance.
 os.environ['WVB_ENABLE_REPLACEMENT_LINEUPS']='0'
 off=new_app(source);select_match(off,'nebraska','kansas','Home court')
 element(off.radio,'Pricing model').set_value('Player (RAPM)');check(off.run())
 assert not any(r.label=='Removed minutes go to' for r in off.radio)
for f,digest in hashes.items():assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==digest
out=new_run(ROOT/'evidence/t13-20261004')
pd.DataFrame(results).to_csv(out/'removals.csv',index=False)
(out/'labels.json').write_text(json.dumps(labels,indent=2))
(out/'checks.json').write_text(json.dumps(dict(exact_unedited_teams=int(rapm.team.nunique()),
 exact_full_roster=True,weighting_modes=2,ui_modes=2,benchmarks=4,ui_label_checks=5,
 redistribution_toggle_exact=True,explicit_sub_override=True,league_fallback=True,
 protected_sha256=hashes,real_paid_calls=0,real_writes=0,explicit_rollback=True,benchmark_ref=BENCHMARK_REF,current_unedited_teams=int(current_rapm.team.nunique())),indent=2))
print(pd.DataFrame(results).to_string(index=False));print('PASS T13 gates')
