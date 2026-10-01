"""Read-only player/hybrid audit. No rebuilds or external service access."""
import argparse
from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts/validation'))
from validate_t2_ui import guards,new_app,select_match,element,board,check
from vbstats import model,rapm_price

CASES=[('nebraska','kansas','Harper Murray'),('pittsburgh','kansas','Olivia Babcock'),
       ('nebraska','kansas','Teraya Sigler'),('pittsburgh','kansas','Ayanna Watson')]


def data(ref=None):
    def get(path):
        return subprocess.check_output(['git','show',f'{ref}:{path}'],cwd=ROOT) if ref else (ROOT/path).read_bytes()
    return (pd.read_parquet(io.BytesIO(get('app_data/rapm.parquet'))),
            pd.read_parquet(io.BytesIO(get('app_data/elo_current.parquet'))).set_index('team'),
            json.loads(get('app_data/rapm_meta.json')),
            np.array(json.loads(get('app_data/model_params.json'))['params']))


def defaults(rows):
    tr=pd.DataFrame(rows).sort_values(['sets_started_cur','recv'],ascending=False)
    return set(tr[tr.in_last_lineup].player) or set(tr.head(6).player)


def values(rows,selected):
    return np.array(rapm_price.lineup_strength(rows,selected)[:2])


def distribution(home,away,hrows,arows,hsel,asel,ratings,meta,params,mode):
    hs,hr=values(hrows,hsel); a_s,ar=values(arows,asel)
    base=meta['intercept']
    p1=base+meta['home_serve']+hs-ar
    p2=1-(base-meta['home_serve']+a_s-hr)
    if mode=='player':
        return rapm_price.set_score_probs6(p1,p2,float(np.exp(params[5])))
    h,a=ratings.loc[home],ratings.loc[away]
    x=model.features(pd.DataFrame([dict(home_serve_elo=h.serve_elo,home_receive_elo=h.receive_elo,
          home_conf_elo=h.conf_elo,away_serve_elo=a.serve_elo,away_receive_elo=a.receive_elo,
          away_conf_elo=a.conf_elo,is_neutral=False)]))
    if mode=='elo': return model.set_score_probs(x,params)[0]
    def eta(hv,av):
        p=rapm_price.set_win_prob(base+hv[0]-av[1],1-(base+av[0]-hv[1]),25)
        p=np.clip(p,1e-6,1-1e-6)
        return float(np.log(p/(1-p)))
    delta=eta(values(hrows,hsel),values(arows,asel))-eta(values(hrows,{r['player'] for r in hrows}),values(arows,{r['player'] for r in arows}))
    pv=params.copy(); pv[:4]=[float(x[0]@params[:4])+delta,0,0,0]
    return model.set_score_probs(np.array([[1.,0,0,0]]),pv)[0]


def measures(rapm,ratings,meta,params,cases=CASES):
    results=[]
    for home,away,player in cases:
        hrows=rapm[rapm.team==home].to_dict('records')
        arows=rapm[rapm.team==away].to_dict('records')
        hsel,asel=defaults(hrows),defaults(arows)
        # Explicit with/without comparison, even if already absent by default.
        hsel.add(player)
        remaining=hsel-{player}
        before=values(hrows,hsel); after=values(hrows,remaining)
        selected=[r for r in hrows if r['player'] in hsel]
        record=next(r for r in selected if r['player']==player)
        u=record['sets_started_cur']+1
        U=sum(r['sets_started_cur']+1 for r in selected)
        expected_change=6*u/(U-u)*(before/6-np.array([record['serve'],record['recv']]))
        assert np.allclose(after-before,expected_change,atol=1e-15)
        base=meta['intercept']; av=values(arows,asel)
        set_before=rapm_price.set_win_prob(base+meta['home_serve']+before[0]-av[1],1-(base-meta['home_serve']+av[0]-before[1]),25)
        set_after=rapm_price.set_win_prob(base+meta['home_serve']+after[0]-av[1],1-(base-meta['home_serve']+av[0]-after[1]),25)
        row=dict(home=home,away=away,player=player,sets=record['sets_started_cur'],serve=record['serve'],recv=record['recv'],
                 selected_by_default=player in defaults(hrows),effective_weight=6*u/U,
                 expected_serve_change=expected_change[0],observed_serve_change=(after-before)[0],
                 expected_recv_change=expected_change[1],observed_recv_change=(after-before)[1],
                 set_before=set_before,set_after=set_after)
        for mode in ('player','hybrid','elo'):
            pb=distribution(home,away,hrows,arows,hsel,asel,ratings,meta,params,mode)
            pa=distribution(home,away,hrows,arows,remaining,asel,ratings,meta,params,mode)
            row[mode+'_before']=float(sum(pb[:3])); row[mode+'_after']=float(sum(pa[:3]))
        results.append(row)
    return results


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    out=Path(parser.parse_args().output);out.mkdir(parents=True,exist_ok=False)
    rapm,ratings,meta,params=data()
    current=measures(rapm,ratings,meta,params)
    leaders=rapm[rapm.sets_started_cur>0].assign(impact=lambda r:r.serve+r.recv).nlargest(5,'impact')
    top_cases=[(r.team,'kansas',r.player) for r in leaders.itertuples()]
    pd.DataFrame(measures(rapm,ratings,meta,params,top_cases)).to_csv(out/'top5_removals.csv',index=False)
    pd.DataFrame(current).to_csv(out/'removals.csv',index=False)
    # Historical snapshots isolate what changed at the named merge, without refitting.
    historical=[]
    for ref in ('6f92059^','6f92059'):
        for row in measures(*data(ref)):
            historical.append(dict(ref=ref,**row))
    pd.DataFrame(historical).to_csv(out/'canonicalization_comparison.csv',index=False)
    source=(ROOT/'streamlit_app.py').read_text()
    checks=[]
    with ExitStack() as stack:
        guards(stack)
        for row in current:
            at=new_app(source);select_match(at,row['home'],row['away'],'Home court')
            pure=float(board(at).iloc[0]['prob'])
            for mode in ('player','hybrid'):
                element(at.radio,'Pricing model').set_value('Player (RAPM)' if mode=='player' else 'Hybrid (Elo + lineup adjust)')
                check(at.run())
                key=f"lineup_{row['home']}"
                selected=list(at.multiselect(key=key).value)
                if row['player'] not in selected: selected.append(row['player'])
                at.multiselect(key=key).set_value(selected);check(at.run())
                before=float(board(at).iloc[0]['prob'])
                at.multiselect(key=key).set_value([p for p in selected if p!=row['player']]);check(at.run())
                after=float(board(at).iloc[0]['prob'])
                assert before==round(row[mode+'_before'],4),(row['player'],mode,before,row[mode+'_before'])
                assert after==round(row[mode+'_after'],4)
                checks.append(dict(player=row['player'],mode=mode,expected_before=round(row[mode+'_before'],4),
                                   ui_before=before,expected_after=round(row[mode+'_after'],4),ui_after=after))
        # No-edit identity: default lineup vs season-reference selection.
        at=new_app(source);select_match(at,'nebraska','kansas','Home court')
        elo=board(at).copy()
        element(at.radio,'Pricing model').set_value('Hybrid (Elo + lineup adjust)');check(at.run())
        hybrid_default=board(at).copy()
        for team in ('nebraska','kansas'):
            at.multiselect(key=f'lineup_{team}').set_value(rapm[rapm.team==team].player.tolist())
        check(at.run())
        pd.testing.assert_frame_equal(elo,board(at),check_exact=True)
        identity=dict(elo=float(elo.iloc[0]['prob']),hybrid_default=float(hybrid_default.iloc[0]['prob']),
                      hybrid_season_reference=float(board(at).iloc[0]['prob']),
                      default_exact=bool(elo.equals(hybrid_default)),season_reference_exact=True)
    pd.DataFrame(checks).to_csv(out/'ui_wiring.csv',index=False)
    # Coverage of missing rosters and absent-player join, without opening real sheets.
    roster_teams=set(rapm.team)
    no_roster=sorted(set(ratings.index)-roster_teams)
    available=pd.read_parquet(ROOT/'app_data/availability.parquet')
    core=available[(available.team_matches>=3)&(available.matches_started/available.team_matches>=.5)]
    absent=core[~core.appeared_last]
    joined=absent.merge(rapm,on=['team','player'],how='left',indicator=True,suffixes=('_availability','_rapm'))
    joined.to_csv(out/'absent_join.csv',index=False)
    report=dict(no_edit_identity=identity,rated_teams_without_rosters=no_roster,absent_core_count=len(absent),
                unmatched_absent_count=int((joined['_merge']=='left_only').sum()),
                absent_already_deselected=int((joined.in_last_lineup==False).sum()),
                alpha=meta['alpha'],recency=meta['recency'])
    (out/'summary.json').write_text(json.dumps(report,indent=2))
    print(pd.DataFrame(current)[['player','player_before','player_after','hybrid_before','hybrid_after']].to_string(index=False))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
