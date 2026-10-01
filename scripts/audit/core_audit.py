"""Read-only mathematical, data-integrity and Elo replay checks for T1."""
import argparse
from collections import defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from vbstats import model,rapm_price,elo
import bet_log,kelly,paste_odds


def enumerate_match(p,p5):
    totals=defaultdict(float)
    def branch(h,a,mass):
        if h==3 or a==3: totals[(h,a)]+=mass;return
        prob=p5 if h+a==4 else p
        branch(h+1,a,mass*prob);branch(h,a+1,mass*(1-prob))
    branch(0,0,1.)
    return np.array([totals[score] for score in model.OUTCOMES])


def enumerate_rallies(p1,p2,target):
    # Propagate every finite rally history via aggregated states; no DP
    # recursion, deuce fixed point, or library under test in this oracle.
    states={(0,0,True):.5,(0,0,False):.5};won=lost=0.
    for step in range(2000):
        following=defaultdict(float)
        for (h,a,serving),mass in states.items():
            p=p1 if serving else p2
            for nh,na,ns,q in ((h+1,a,True,p),(h,a+1,False,1-p)):
                prob=mass*q
                if nh>=target and nh-na>=2:won+=prob
                elif na>=target and na-nh>=2:lost+=prob
                else:following[nh,na,ns]+=prob
        states=following
        if sum(states.values())<1e-13:break
    return won,sum(states.values()),step+1


def math_checks(params):
    distribution=[]
    nodes,weights=np.polynomial.hermite.hermgauss(21)
    for eta,lam,sigma in itertools.product((-8,-2,0,2,8),(-.5,0,.7,1,1.5),(.01,.5,1.5)):
        pv=np.array([eta,0,0,0,lam,np.log(sigma)])
        actual=model.set_score_probs(np.array([[1.,0,0,0]]),pv)[0]
        expected=sum(w/np.sqrt(np.pi)*enumerate_match(np.clip(expit(eta+sigma*np.sqrt(2)*z),1e-9,1-1e-9),np.clip(.5+lam*(np.clip(expit(eta+sigma*np.sqrt(2)*z),1e-9,1-1e-9)-.5),1e-9,1-1e-9)) for z,w in zip(nodes,weights))
        distribution.append(dict(eta=eta,lam=lam,sigma=sigma,sum=float(actual.sum()),min=float(actual.min()),max_error=float(np.max(np.abs(actual-expected)))))
    quadrature=[]
    sigma=float(np.exp(params[5]));lam=float(params[4])
    for eta in (-5,-2,0,2,5):
        pv=params.copy();pv[:4]=[eta,0,0,0]
        actual=model.set_score_probs(np.array([[1.,0,0,0]]),pv)[0]
        exact=np.array([quad(lambda z:enumerate_match(np.clip(expit(eta+sigma*z),1e-9,1-1e-9),np.clip(.5+lam*(np.clip(expit(eta+sigma*z),1e-9,1-1e-9)-.5),1e-9,1-1e-9))[i]*np.exp(-z*z/2)/np.sqrt(2*np.pi),-10,10,epsabs=1e-11)[0] for i in range(6)])
        quadrature.append(dict(eta=eta,sigma=sigma,max_error=float(np.max(np.abs(actual-exact)))))
    dp=[]
    for p1,p2,target in itertools.product((.25,.43,.65),(.35,.57,.75),(15,25)):
        expected,residual,steps=enumerate_rallies(p1,p2,target)
        actual=rapm_price.set_win_prob(p1,p2,target)
        dp.append(dict(p1=p1,p2=p2,target=target,expected=expected,actual=actual,error=actual-expected,residual=residual,steps=steps))
    return dict(distribution_grid=distribution,quadrature=quadrature,dp=dp)


def micro_elo():
    common=dict(season=2026,start_epoch=10,home_id=1,away_id=2,home_seo='a',away_seo='b',home_conf='x',away_conf='y',is_neutral=False,is_championship=False,is_conf_tournament=False,venue='a',home_sets=3,away_sets=0)
    matches=pd.DataFrame([dict(contest_id=2,**common),dict(contest_id=1,**common)])
    points=pd.DataFrame([dict(contest_id=1,server_id=1,winner_id=1)])
    table,ratings=elo.run_elo(matches,points,conf_weight=.1)
    assert table.iloc[0].contest_id==1 and table.iloc[0].home_serve_elo==1500
    assert abs(table.iloc[1].home_serve_elo-1500.45)<1e-12
    assert abs(ratings.conf['x']-.05)<1e-12
    assert sum(ratings.games.values())==4
    ratings.regress_to_mean(.8)
    assert abs(ratings.serve[1]-1500.36)<1e-12
    assert sum(ratings.games.values())==0
    same=matches.iloc[:1].copy();same['away_conf']='x'
    _,single=elo.run_elo(same,pd.DataFrame([dict(contest_id=2,server_id=1,winner_id=1)]),conf_weight=.1)
    assert not single.conf and single.serve[1]==1500.5
    return dict(pregame_snapshot='PASS',cross_conference='PASS',within_conference='PASS',carryover='PASS',team_games_identity='PASS',simultaneous_game_risk='Later contestId sees earlier same-start match result; no finish-time constraint')


def settlements():
    n=0
    for hs,aw in model.OUTCOMES:
        for side in ('home','away'):
            won,push=bet_log._settle('ml',side,'',hs,aw);assert won==((hs if side=='home' else aw)> (aw if side=='home' else hs)) and not push;n+=1
            for line in (-2.5,-1.5,0,1.5,2.5):
                margin=(hs-aw) if side=='home' else (aw-hs)
                w,p=bet_log._settle('spread',side,line,hs,aw)
                assert w==(margin+line>0) and p==(margin+line==0);n+=1
        for line in (3,3.5,4,4.5,5):
            for side in ('over','under'):
                w,p=bet_log._settle('total',side,line,hs,aw)
                assert w==((hs+aw>line) if side=='over' else (hs+aw<line)) and p==(hs+aw==line);n+=1
        for side in ('yes','no'):
            w,p=bet_log._settle('five',side,'',hs,aw)
            assert w==((hs+aw==5) if side=='yes' else (hs+aw!=5)) and not p;n+=1
    for odds in (-1000,-110,100,250,1000):
        implied=kelly.american_to_prob(odds)
        for p in (.05,.4,.6,.95):
            edge=min(p-implied,.06);b=kelly.american_to_decimal(odds)-1
            expected=max(0,(b*(implied+edge)-(1-implied-edge))/b)*500*.5
            assert abs(kelly.kelly_stake(500,.5,odds,p,.06)-expected)<1e-8
    return dict(settlement_cases=n,kelly_cases=20)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    paths=list((ROOT/'data/processed').glob('*.parquet'))+[ROOT/'app_data/model_params.json']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    params=np.array(json.loads((ROOT/'app_data/model_params.json').read_text())['params'])
    result=dict(math=math_checks(params),elo_micro=micro_elo(),settlement=settlements())
    counts=[];state=elo.TeamRatings();warm=[]
    for year in range(2021,2027):
        matches=pd.read_parquet(ROOT/f'data/processed/matches_{year}.parquet')
        points=pd.read_parquet(ROOT/f'data/processed/points_{year}.parquet')
        ids=set(matches.contest_id);pids=set(points.contest_id)
        counts.append(dict(season=year,matches=len(matches),unique_matches=len(ids),points=len(points),point_matches=len(pids),no_points=len(ids-pids),orphan_points=len(pids-ids),duplicate_point_keys=int(points.duplicated(['contest_id','set','point_num']).sum()),unknown_servers=int(points.server_id.isna().sum()),serve_conflicts=int(points.serve_conflict.sum()),invalid_finals=int((model.outcome_index(matches)<0).sum())))
        if year<=2025:
            if year>2021:state.regress_to_mean(.8)
            started=time.perf_counter()
            table,state=elo.run_elo(matches,points,conf_weight=.1,ratings=state)
            assert sum(state.games.values())==2*len(matches)
            hot=(table.home_games_played>=10)&(table.away_games_played>=10)
            valid=model.outcome_index(table)>=0
            sample=table[hot&valid]
            pr=model.markets(model.set_score_probs(model.features(sample),params))['home_ml']
            # Two rating-only decisions, plus fixed-parameter set model.
            gap=(sample.home_serve_elo+sample.home_receive_elo+2*sample.home_conf_elo)-(sample.away_serve_elo+sample.away_receive_elo+2*sample.away_conf_elo)
            fittedgap=params[1]*(sample.home_serve_elo-sample.away_serve_elo+sample.home_conf_elo-sample.away_conf_elo)+params[2]*(sample.home_receive_elo-sample.away_receive_elo+sample.home_conf_elo-sample.away_conf_elo)
            for method,pred in [('elo_sum',gap>0),('elo_weighted',fittedgap>0),('fixed_set_model',pr>.5)]:
                warm.append(dict(season=year,method=method,n=len(sample),correct=int((pred==sample.home_win).sum()),accuracy=float((pred==sample.home_win).mean())))
            print(year,'chained replay',round(time.perf_counter()-started,2),'seconds',flush=True)
    pd.DataFrame(counts).to_csv(out/'data_counts.csv',index=False)
    pd.DataFrame(warm).to_csv(out/'warm_accuracy.csv',index=False)
    result['source_hashes']=hashes
    result['hashes_unchanged']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    assert result['hashes_unchanged']
    (out/'checks.json').write_text(json.dumps(result,indent=2))
    print('All audit outputs written; originals unchanged',flush=True)


if __name__=='__main__':main()
