"""Diagnostic blend/gate analysis; never tunes or changes production defaults."""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import kelly

SEED=20261001
DRAWS=10000
WEIGHTS=(.30,.35,.40,.50)
GATES=(.01,.02,.03,.04,.06)
BUCKETS=((.02,.05,'2–5pp'),(.05,.08,'5–8pp'),(.08,.12,'8–12pp'),(.12,np.inf,'12+pp'))


def blend(model,market,w):
    pm=np.clip(np.asarray(model,float),1e-6,1-1e-6)
    pk=np.clip(np.asarray(market,float),1e-6,1-1e-6)
    z=w*np.log(pm/(1-pm))+(1-w)*np.log(pk/(1-pk))
    return 1/(1+np.exp(-z))


def stats(df,bootstrap=False):
    n=len(df)
    pnl=np.where(df['push'],0,np.where(df.won,df.close_dec-1,-1))
    result=dict(n=n,wins=int(df.won.sum()),losses=int((~df.won&~df['push']).sum()),pushes=int(df['push'].sum()),
                profit=float(pnl.sum()),roi=float(pnl.mean()) if n else None)
    if bootstrap:
        samples=np.random.default_rng(SEED).choice(pnl,size=(DRAWS,n),replace=True).mean(axis=1) if n else []
        result.update(ci90_low=float(np.quantile(samples,.05)) if n else None,
                      ci90_high=float(np.quantile(samples,.95)) if n else None)
    return result


def buckets(df):
    result=[]
    diff=df.p_model-df.p_mkt
    passed=blend(df.p_model,df.p_mkt,.30)-df.implied>=.02
    for low,high,label in BUCKETS:
        for passes in (False,True):
            result.append(dict(bucket=label,passed=passes,**stats(df[(diff>=low)&(diff<high)&(passed==passes)])))
    return result


def analyze(df,label,out):
    grid=[];marginal=[];marginal_rows=[]
    base=blend(df.p_model,df.p_mkt,.30)-df.implied>=.02
    for w in WEIGHTS:
        edge=blend(df.p_model,df.p_mkt,w)-df.implied
        for gate in GATES:
            selected=edge>=gate
            grid.append(dict(sample=label,w=w,gate=gate,**stats(df[selected],True)))
            # Report newly admitted AND removed bets: higher w is not monotone
            # when p_model is below p_mkt.
            add=selected&~base;remove=base&~selected
            marginal.append(dict(sample=label,w=w,gate=gate,kind='added',**stats(df[add],True)))
            marginal.append(dict(sample=label,w=w,gate=gate,kind='removed',**stats(df[remove],True)))
            if add.any():
                copy=df[add].copy();copy['w']=w;copy['gate']=gate
                marginal_rows.append(copy)
    pd.DataFrame(grid).to_csv(out/f'{label}_grid.csv',index=False)
    pd.DataFrame(marginal).to_csv(out/f'{label}_marginal.csv',index=False)
    if marginal_rows: pd.concat(marginal_rows).to_csv(out/f'{label}_marginal_bets.csv',index=False)
    pd.DataFrame(buckets(df)).to_csv(out/f'{label}_buckets.csv',index=False)
    ml=df[(df.market=='ml')&(df.side=='home')].drop_duplicates('fixture')
    ll=[]
    for w in (0.,*WEIGHTS,1.):
        p=np.clip(blend(ml.p_model,ml.p_mkt,w),1e-6,1-1e-6)
        y=ml.won.astype(float)
        ll.append(dict(sample=label,w=w,n=len(ml),logloss=float(-(y*np.log(p)+(1-y)*np.log(1-p)).mean()) if len(ml) else None))
    pd.DataFrame(ll).to_csv(out/f'{label}_logloss.csv',index=False)
    return dict(rows=len(df),fixtures=int(df.fixture.nunique()),baseline=stats(df[base],True))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--paper')
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    paths=['data/processed/odds_hist_2026.parquet','data/processed/backtest_odds_2026.parquet','app_data/model_params.json']
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    spec=importlib.util.spec_from_file_location('original_backtest',ROOT/'scripts/backtest_odds.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    write=pd.DataFrame.to_parquet
    def evidence_write(frame,path,*a,**kw):
        assert str(path)=='data/processed/backtest_odds_2026.parquet'
        return write(frame,out/'rebuilt_backtest.parquet',*a,**kw)
    with (out/'backtest_stdout.txt').open('x') as log,redirect_stdout(log),patch.object(pd.DataFrame,'to_parquet',evidence_write):
        module.main()
    bt=pd.read_parquet(out/'rebuilt_backtest.parquet')
    bt['date']=pd.to_datetime(bt.date)
    keys=['fixture','market','side','point']
    best=bt.sort_values('close_dec',ascending=False).drop_duplicates(keys)
    report={'seed':SEED,'bootstrap_draws':DRAWS,'source_hashes':hashes,'priced_rows':len(bt),
            'best_rows':len(best),'dedup_removed':len(bt)-len(best),'new_boarded_fixtures':None,
            'extension_status':'Blocked: fixture enumeration is billable; T3 permits zero billable requests.'}
    report['full']=analyze(best,'full',out)
    increment=best[best.date>pd.Timestamp('2026-09-26')]
    report['post_0926']=analyze(increment,'post_0926',out)
    if args.paper:
        raw=pd.DataFrame(json.loads(Path(args.paper).read_text()))
        numeric=['odds','model_prob','mkt_prob']
        settled=raw[raw.status.isin(['won','lost','push'])].copy()
        for c in numeric: settled[c]=pd.to_numeric(settled[c],errors='coerce')
        valid=settled[numeric].notna().all(axis=1)&settled.model_prob.between(0,1,inclusive='neither')&settled.mkt_prob.between(0,1,inclusive='neither')&(settled.odds.abs()>=100)
        d=settled[valid].copy()
        d['p_model']=d.model_prob;d['p_mkt']=d.mkt_prob
        d['close_dec']=d.odds.map(kelly.american_to_decimal) # taken, NOT closing prices
        d['implied']=1/d.close_dec;d['won']=d.status=='won';d['push']=d.status=='push'
        pd.DataFrame(buckets(d)).to_csv(out/'paper_buckets.csv',index=False)
        report['paper']={'total':len(raw),'settled':len(settled),'excluded_unsettled':len(raw)-len(settled),
                         'excluded_invalid_or_missing_probabilities':int((~valid).sum()),'analyzed':len(d),
                         'disagreement_buckets_total':sum(x['n'] for x in buckets(d)),
                         'outside_buckets':int(((d.p_model-d.p_mkt)<.02).sum())}
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (out/'summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
