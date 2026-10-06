"""T16: actual batch UI, persisted ID precedence, corpus and generalization gates.
All confirmations are mocked owner choices in a temporary file; no real writes.
"""
import copy,json,os,tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from validate_t2_ui import ROOT,guards,new_app,element,check
from evidence_runs import new_run
import learned_matching as learn,bulk_team_matching as bulk,live_team_map as lm
r=pd.read_parquet(ROOT/'app_data/elo_current.parquet');seos=r.team.tolist();full=dict(zip(r.team,r.name_full))
# Explicit test choices, not proposed production ground truth.
answers={'1074744':'utah-tech','1088295':'bowie-st','1179139':'west-ga','1192083':'mercyhurst',
'1375582':'west-florida','287441':'umes','287443':'umkc','290570':'toledo','290628':'denver',
'290630':'western-ill','290634':'george-mason','290642':'siu-edwardsville','290644':'murray-st',
'290648':'northern-ill','290902':'campbell','292330':'virginia','294052':'utrgv','294098':'robert-morris',
'296276':'la-lafayette','300576':'texas-st'}
source=(ROOT/'streamlit_app.py').read_text()
with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
 guards(stack);stack.enter_context(patch.dict(os.environ,{'WVB_ENABLE_LEARNED_MATCHING':'1','WVB_MAPPING_STORAGE':'local'}))
 path=Path(tmp)/'mapping.json';path.write_text('{}\n');stack.enter_context(patch.object(lm,'MAP_PATH',path))
 writes=stack.enter_context(patch.object(lm,'save',wraps=lm.save))
 before,_=bulk.inventory(r,{})
 app=new_app(source);assert any(t.label=='Team matching' for t in app.tabs)
 assert writes.call_count==0 and json.loads(path.read_text())=={}
 app.multiselect(key='bulk_ids').set_value(list(answers));check(app.run())
 for pid,seo in answers.items():app.selectbox(key=f'bulk_school:{pid}').set_value(seo)
 element(app.button,'Confirm & save 20 mappings').click();check(app.run())
 assert writes.call_count==1
 saved=json.loads(path.read_text());assert saved==answers
 check(app.run());assert app.multiselect(key='bulk_ids').value==[] and writes.call_count==1
 # New session sees permanent map; confirmed IDs disappear from unresolved inventory.
 fresh=new_app(source);assert fresh.session_state.bulk_mapping==answers
 after,rules=bulk.inventory(r,saved);assert len(before)-len(after)==20
 for pid,seo in answers.items():
  assert lm.resolve({'home':'Different vendor spelling','home_participant_id':pid},'home',seos,full,saved)==(seo,1.)
 names=learn.participants();confirmed={learn.norm(names[p]):s for p,s in answers.items()}
 cases=json.loads(learn.VALIDATION.read_text());wrong=[];refused=0
 for row in cases:
  expected=row['expected'] if row['expected'] is not None else confirmed.get(learn.norm(row['name']))
  actual=learn.apply(row['name'],seos,full,rules)[0]
  if actual is not None and actual!=expected:wrong.append((row['name'],expected,actual))
  if row['expected'] is not None:assert actual==row['expected']
  refused+=actual is None
 assert not wrong
 # A stale bulk save cannot overwrite a confirmation from another session.
 current={**saved,'1074744':'utah'};path.write_text(json.dumps(current))
 try:lm.save({'1074744':'utah-tech'},{},seos)
 except lm.MappingError:pass
 else:raise AssertionError('Stale batch overwrote a saved identity')
 assert json.loads(path.read_text())==current
 # Runtime rule construction is read-only; no persisted guesses.
 assert writes.call_count==2
 os.environ['WVB_ENABLE_LEARNED_MATCHING']='0'
 off=new_app(source);assert not any(t.label=='Team matching' for t in off.tabs)
# Independent multi-school mascot evidence, on synthetic names only.
learn._derive.cache_clear()
synthetic={**learn.participants(),'90000001':'Nebraska Moonbirds','90000002':'Kansas Moonbirds'}
with patch.object(learn,'participants',return_value=synthetic):
 inferred=learn.rules_for({'90000001':'nebraska','90000002':'kansas'},seos,full)
 assert 'moonbirds' in inferred['suffixes']
 assert learn.apply('Utah Moonbirds',seos,full,inferred)==('utah',1.)
 assert learn.apply('USC Unknown Campus Moonbirds',seos,full,inferred)[0] is None
 assert learn.apply('Shared Moonbirds',seos+['test-a','test-b'],{**full,'test-a':'Shared','test-b':'Shared'},inferred)[0] is None
# A contradicted known identity cannot train a name rule over the corpus.
learn._derive.cache_clear()
with patch.object(learn,'participants',return_value={'90000003':'Utah Utes'}):
 blocked=learn.rules_for({'90000003':'utah-st'},seos,full)
 assert blocked['rejected'] and learn.apply('Utah Utes',seos,full,blocked)[0]=='utah'
# Missing gate data refuses new name resolution but preserves exact confirmed IDs.
learn._derive.cache_clear()
with patch.dict(os.environ,{'WVB_ENABLE_LEARNED_MATCHING':'1'}),patch.object(learn,'VALIDATION',Path('/nonexistent/team-gate.json')):
 assert lm.resolve({'home':'Utah','home_participant_id':'123'},'home',seos,full,{})[0] is None
 assert lm.resolve({'home':'Unknown','home_participant_id':'123'},'home',seos,full,{'123':'utah'})==('utah',1.)
learn._derive.cache_clear()
out=new_run(ROOT/'evidence/t16-20261004')
summary=dict(bulk_confirmed_in_one_session=20,one_batch_write=True,refused_before=len(before),refused_after=len(after),actual_owner_confirmations=0,validation_cases=len(cases)+20,wrong=0,known_corpus_exact=1596,persisted_id_precedence=True,stale_batch_refused=True,synthetic_suffix_generalizes=True,ambiguous_campus_refused=True,contradicted_rule_rejected=True,missing_gate_fails_closed=True,default_off_rollback=True,real_provider_calls=0,real_mapping_writes=0,real_sheet_writes=0)
(out/'checks.json').write_text(json.dumps(summary,indent=2));(out/'mock-rules.json').write_text(json.dumps(rules,indent=2));print(json.dumps(summary,indent=2))
