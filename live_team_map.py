"""Owner-confirmed OddsPapi identities; no fuzzy result is persisted automatically.

Cloud writes target one fixed repository file, using GitHub's blob-SHA compare
and swap. Local mode is explicitly opt-in (for a local checkout / offline tests).
No external calls occur on import. Never expose response bodies or credentials.
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import tempfile
import fcntl
import requests
import paste_odds

MAP_PATH = Path(__file__).resolve().parent/'app_data/oddspapi_team_map.json'
CONTENT_URL = 'https://api.github.com/repos/jWozSauce/wvb-betting-model/contents/app_data/oddspapi_team_map.json'

class MappingError(RuntimeError):
    pass


def validate(mapping, seos):
    if not isinstance(mapping, dict) or any(
        not isinstance(k,str) or not k.isascii() or not k.isdigit() or not isinstance(v,str) or v not in seos
        for k,v in mapping.items()):
        raise MappingError('Invalid participant mapping; no changes saved.')
    return mapping


def load_local(seos):
    try:
        return validate(json.loads(MAP_PATH.read_text()),seos)
    except (OSError,ValueError):
        raise MappingError('Cannot read participant mappings; restore the mapping file.') from None


def resolve(game, side, seos, fullnames, mapping):
    pid = str(game.get(side+'_participant_id',''))
    if pid in mapping:
        seo=mapping[pid]
        return (seo,1.) if seo in seos else (None,0.)
    return paste_odds.match_team(game[side],seos,fullnames=fullnames)


def _remote(token):
    try:
        r=requests.get(CONTENT_URL,headers={'Authorization':f'Bearer {token}',
            'Accept':'application/vnd.github+json'},params={'ref':'main'},timeout=20)
        if r.status_code!=200:
            raise MappingError(f'Mapping read failed (HTTP {r.status_code}); no changes saved.')
        data=r.json()
        return json.loads(base64.b64decode(data['content'])),data['sha']
    except (requests.RequestException,ValueError,KeyError):
        raise MappingError('Mapping read failed; no changes saved.') from None


def refresh(seos, token=None):
    if os.environ.get('WVB_MAPPING_STORAGE')=='local':
        return load_local(seos)
    if token:
        return validate(_remote(token)[0],seos)
    return load_local(seos)


def _merge(current, updates, expected, seos):
    validate(current,seos);validate(updates,seos)
    for pid,seo in updates.items():
        if current.get(pid) not in (expected.get(pid),seo):
            raise MappingError('A mapping changed in another session. Fetch again before confirming.')
    return {**current,**updates}


def save(updates, expected, seos, token=None):
    if os.environ.get('WVB_MAPPING_STORAGE')=='local':
        with MAP_PATH.with_suffix('.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            merged=_merge(load_local(seos),updates,expected,seos)
            fd,tmp=tempfile.mkstemp(dir=MAP_PATH.parent,prefix='.team-map-')
            try:
                with os.fdopen(fd,'w') as f: json.dump(merged,f,indent=2,sort_keys=True);f.write('\n')
                os.replace(tmp,MAP_PATH)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
        return merged
    if not token:
        raise MappingError('Permanent matching needs the repository mapping credential configured by the owner.')
    current,sha=_remote(token)
    merged=_merge(current,updates,expected,seos)
    if merged==current:return merged
    content=base64.b64encode((json.dumps(merged,indent=2,sort_keys=True)+'\n').encode()).decode()
    try:
        r=requests.put(CONTENT_URL,headers={'Authorization':f'Bearer {token}',
            'Accept':'application/vnd.github+json'},json={'message':'Save owner-confirmed OddsPapi team identities',
            'content':content,'sha':sha,'branch':'main'},timeout=20)
        if r.status_code not in (200,201):
            raise MappingError(f'Mapping save failed (HTTP {r.status_code}). Fetch again before retrying.')
    except requests.RequestException:
        raise MappingError('Mapping save outcome unknown. Fetch again to verify before retrying.') from None
    return merged


def credential():
    import streamlit as st
    try:
        # Never enable repository writes in an unauthenticated cloud app.
        if st.secrets.get('APP_PASSWORD') and st.session_state.get('authed'):
            return st.secrets.get('TEAM_MAP_GITHUB_TOKEN')
    except Exception:
        pass
    return None


def render(games, ratings, mapping):
    """Show every unresolved fixture; confirms both identities in a single action."""
    import streamlit as st
    seos=ratings.team.tolist();full=dict(zip(ratings.team,ratings.name_full))
    changed=False; unresolved=0
    for game in games:
        h,hs=resolve(game,'home',seos,full,mapping)
        a,acs=resolve(game,'away',seos,full,mapping)
        if h and a and h!=a and min(hs,acs)>=.8:continue
        unresolved+=1
        fid=str(game.get('fixture_id',game.get('board_pos')))
        st.markdown(f"**{game['away']} @ {game['home']}** · {game.get('date','')} {game.get('time','')}")
        cols=st.columns([3,3,2]);chosen={}
        for col,side,guess in [(cols[0],'away',a),(cols[1],'home',h)]:
            chosen[side]=col.selectbox(f"{side.title()}: {game[side]}",seos,
                index=seos.index(guess) if guess in seos else None,
                format_func=lambda t:f'{t} — {full[t]}',key=f'live-map:{fid}:{side}')
        ids=[str(game.get(side+'_participant_id','')) for side in ('away','home')]
        valid=all(chosen.values()) and chosen['home']!=chosen['away'] and all(p.isdigit() for p in ids) and ids[0]!=ids[1]
        if cols[2].button('Confirm teams & save',key=f'live-map:{fid}:save',disabled=not valid):
            try:
                mapping=save(dict(zip(ids,[chosen['away'],chosen['home']])),mapping,seos,credential())
                st.session_state.live_mapping=mapping
                st.success('Team identities saved. Pricing uses the confirmed mapping.')
                changed=True
            except MappingError as e:st.error(str(e))
        if not all(p.isdigit() for p in ids):st.warning('Participant IDs are missing; this fixture cannot be saved or priced.')
    if unresolved:st.caption(f'{unresolved} fixture(s) need confirmation. Unconfirmed fixtures stay out of pricing.')
    return mapping,changed
