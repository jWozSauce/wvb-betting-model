"""Finite exhaustive team-name corpus and near-certain player merge checks."""
import json
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import paste_odds
from vbstats.names import fold_key
out=ROOT/'evidence/t1-20261001/matching-1';out.mkdir(exist_ok=False)
r=pd.read_parquet(ROOT/'app_data/elo_current.parquet');seos=r.team.tolist();full=dict(zip(r.team,r.name_full))
short={}
for path in sorted((ROOT/'data/raw/2026/contests').glob('*.json')):
 for c in json.loads(path.read_text()):
  for t in c.get('teams',[]):
   if t.get('seoname') in seos:
    short.setdefault(t['seoname'],set()).add(t.get('nameShort') or '')
rows=[]
for seo in seos:
 variants={'slug':seo,'full':str(full[seo]),'slug_spaces':seo.replace('-',' ')}
 for i,name in enumerate(sorted(short.get(seo,set()))):variants[f'schedule_short_{i}']=name
 for alias,target in paste_odds.ALIASES.items():
  if target==seo:variants['alias_'+alias]=alias
 for kind,name in variants.items():
  if not name:continue
  match,score=paste_odds.match_team(name,seos,fullnames=full)
  rows.append(dict(expected=seo,kind=kind,input=name,actual=match,score=score,verdict='correct' if match==seo else 'unmatched' if match is None else 'wrong'))
pd.DataFrame(rows).to_csv(out/'team_names.csv',index=False)
# Use the pre-merge boxscore table, preserving original spellings and jerseys.
import io,subprocess
box=pd.read_parquet(io.BytesIO(subprocess.check_output(['git','show','6f92059^:data/processed/player_box_2026.parquet'],cwd=ROOT)))
box['fold']=box.player.map(fold_key)
variants=box.groupby(['team','fold']).player.nunique();keys=variants[variants>1].index
merges=[]
for team,key in keys:
 group=box[(box.team==team)&(box.fold==key)]
 jersey={name:sorted(set(g.number.dropna().astype(str))) for name,g in group.groupby('player')}
 sets=[set(v) for v in jersey.values()]
 overlap=set.intersection(*sets) if all(sets) else set()
 merges.append(dict(team=team,fold=key,variants=json.dumps(jersey,ensure_ascii=False),shared_jerseys=','.join(sorted(overlap)),same_contest_variants=int((group.groupby('contest_id').player.nunique()>1).sum())))
pd.DataFrame(merges).to_csv(out/'player_merge_jerseys.csv',index=False)
summary={'rated_teams':len(seos),'teams_in_local_schedule':len(short),'name_cases':len(rows),'verdict_counts':pd.DataFrame(rows).verdict.value_counts().to_dict(),'player_variant_groups':len(merges),'groups_with_shared_jersey':sum(bool(m['shared_jerseys']) for m in merges),'groups_with_same_contest_variants':sum(m['same_contest_variants']>0 for m in merges)}
(out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));print(pd.DataFrame(rows).query("verdict=='wrong'").head(15).to_string(index=False))
