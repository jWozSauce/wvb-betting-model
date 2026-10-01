"""Additional independent simulation and fitted-model provenance evidence."""
import json,sys,itertools
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from vbstats import rapm_price,model
from scripts.audit.core_audit import enumerate_rallies
rng=np.random.default_rng(20261001);checks=[]
for p1,p2,target in itertools.product((.25,.43,.65),(.35,.57,.75),(15,25)):
 n=50000;h=np.zeros(n,dtype=int);a=h.copy();serve=rng.random(n)<.5;live=np.ones(n,dtype=bool)
 while live.any():
  ix=np.flatnonzero(live);win=rng.random(len(ix))<np.where(serve[ix],p1,p2);h[ix]+=win;a[ix]+=~win;serve[ix]=win;live=(np.maximum(h,a)<target)|(np.abs(h-a)<2)
 actual=float((h>a).mean());exact=rapm_price.set_win_prob(p1,p2,target);se=np.sqrt(exact*(1-exact)/n)
 checks.append(dict(p1=p1,p2=p2,target=target,n=n,simulation=actual,dp=exact,z=(actual-exact)/se))
ext=[]
for p1,p2 in [(.02,.97),(.03,.98),(.98,.02),(.02,.02),(.98,.98)]:
 expected,residual,steps=enumerate_rallies(p1,p2,15);actual=rapm_price.set_win_prob(p1,p2,15);ext.append(dict(p1=p1,p2=p2,error=actual-expected,residual=residual,steps=steps))
b=json.loads((ROOT/'app_data/model_params.json').read_text());params=np.array(b['params']);cov=np.array(b['cov']);draws=np.random.default_rng(7).multivariate_normal(params,cov,500)
result={'seed':20261001,'simulation':checks,'dp_extremes':ext,'cov_min_eigenvalue':float(np.linalg.eigvalsh(cov).min()),'lambda_draws_outside_0_1':int(((draws[:,4]<0)|(draws[:,4]>1)).sum()),'equal_team_home_ml':float(model.set_score_probs(np.array([[1,0,0,1]]),params)[0,:3].sum()),'equal_team_neutral_label_ml':float(model.set_score_probs(np.array([[1,0,0,0]]),params)[0,:3].sum())}
p=ROOT/'evidence/t1-20261001/model_supplement.json';p.open('x').write(json.dumps(result,indent=2));print({k:v for k,v in result.items() if k!='simulation'});print('MC max abs z',max(abs(x['z']) for x in checks))
