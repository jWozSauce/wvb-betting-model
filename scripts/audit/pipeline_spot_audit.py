"""Read-only sampled raw-feed validation and RAPM phase-table spot check."""
import importlib.util,json
from pathlib import Path
import sys
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from vbstats.parse import parse_match
from vbstats.names import apply_canonical,canonical_map
out=ROOT/'evidence/t1-20261001/pipeline-1';out.mkdir(exist_ok=False)
rows=[]
for year in (2023,2026):
 paths=sorted((ROOT/f'data/raw/{year}/games').glob('*.json'))
 # Deterministic systematic sample across filenames; not a random performance estimate.
 sample=paths[::max(1,len(paths)//100)][:100]
 for path in sample:
  b=json.loads(path.read_text());pbp=b.get('pbp');g=b.get('game') or {}
  if not pbp or not pbp.get('periods'):continue
  p=parse_match(pbp)['points'];finals={}
  for point in p:finals[point['set']]=(point['home_score'],point['away_score'])
  for line in g.get('linescores') or []:
   if not str(line['home']).isdigit() or not str(line['visit']).isdigit():continue
   official=(int(line['home']),int(line['visit']));period=int(line['period'])
   got=finals.get(period)
   rows.append(dict(season=year,contest_id=path.stem,period=period,official=str(official),parsed=str(got),matches=got==official,reconstructed=any(x['score_reconstructed'] for x in p if x['set']==period)))
pd.DataFrame(rows).to_csv(out/'raw_score_checks.csv',index=False)
# Recreate only an in-memory phase table from existing tables (no player rebuild).
spec=importlib.util.spec_from_file_location('fit_rapm_audit',ROOT/'scripts/fit_rapm.py');fit=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit)
m=pd.read_parquet(ROOT/'data/processed/matches_2026.parquet');pts=pd.read_parquet(ROOT/'data/processed/points_2026.parquet');st=pd.read_parquet(ROOT/'data/processed/set_starters_2026.parquet')
phase=fit.phase_table(m,pts,st);checks=[]
for row in phase.head(20).itertuples():
 raw=pts[(pts.contest_id==row.contest_id)&(pts['set']==row.set)&(pts.server_id==row.server_id)]
 checks.append(dict(contest_id=int(row.contest_id),set=int(row.set),server_id=int(row.server_id),phase_rallies=int(row.n),raw_rallies=len(raw),phase_wins=int(row.w),raw_wins=int((raw.winner_id==row.server_id).sum())))
 assert len(raw)==row.n and (raw.winner_id==row.server_id).sum()==row.w
# Sign convention: each phase's serve +6 and receive -6 total design mass.
X,ix=fit.build_design(phase.head(20))
assert np.allclose(np.asarray(X[:,:-1:2].sum(axis=1)).ravel(),6)
assert np.allclose(np.asarray(X[:,1:-1:2].sum(axis=1)).ravel(),-6)
summary=dict(raw_sample_sets=len(rows),raw_sets_match=sum(r['matches'] for r in rows),raw_reconstructed_sets=sum(r['reconstructed'] for r in rows),raw_reconstructed_match=sum(r['matches'] and r['reconstructed'] for r in rows),phase_rows=len(phase),phase_spotchecks=checks,design_signs='serve +6, receive -6 on all 20 rows')
local=list((ROOT/'data/raw/2026/games').glob('*.json'))
summary['local_2026_game_files']=len(local)
summary['local_2026_boxscore_files']=sum(bool(json.loads(p.read_text()).get('boxscore')) for p in local)
(out/'summary.json').write_text(json.dumps(summary,indent=2));print({k:v for k,v in summary.items() if k!='phase_spotchecks'})
