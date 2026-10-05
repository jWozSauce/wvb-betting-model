"""Candidate name rules learned only from confirmed participant IDs.

No provider or storage calls. Every candidate must preserve the packaged identity
corpus and all still-unconfirmed refusal regressions before runtime use.
"""
from collections import defaultdict
from functools import lru_cache
import json,re
from pathlib import Path
import paste_odds
HERE=Path(__file__).resolve().parent
PARTICIPANTS=HERE/'app_data/ncaa_matching_participants.json'
VALIDATION=HERE/'app_data/team_match_validation.json'

def participants():
    rows=json.loads(PARTICIPANTS.read_text())
    return {str(r['participant_id']):r['name'] for r in rows}

def norm(name):
    return paste_odds._norm(str(name).replace('&','and'))

def apply(name,seos,fullnames,rules,baseline=None):
    baseline=baseline or paste_odds._match_team_safe(name,seos,fullnames)
    # Existing known identities never get overwritten by an inferred rule.
    if baseline[0]:return baseline
    hits=set(rules['aliases'].get(norm(name),[]))
    text=str(name).strip()
    for suffix in rules['suffixes']:
        ending=' '+suffix
        if text.lower().endswith(ending):
            match,_=paste_odds._match_team_safe(text[:-len(ending)],seos,fullnames)
            if match:hits.add(match)
    return (next(iter(hits)),1.) if len(hits)==1 else (None,0.)

def rules_for(mapping,seos,fullnames):
    return _derive(tuple(sorted(mapping.items())),tuple(sorted(seos)),tuple(sorted((fullnames or {}).items())))

@lru_cache(maxsize=32)
def _derive(pairs,seos,full_pairs):
    full=dict(full_pairs);mapping=dict(pairs);names=participants()
    corpus=json.loads(VALIDATION.read_text())
    confirmed=defaultdict(set)
    for pid,seo in pairs:
        if pid in names and seo in seos:confirmed[norm(names[pid])].add(seo)
    cases=[]
    for row in corpus:
        expected=row['expected']
        answers=confirmed.get(norm(row['name']),set())
        # Only the owner's explicit, unambiguous answer can release a refusal.
        if expected is None and len(answers)==1:expected=next(iter(answers))
        cases.append((row['name'],expected))
    # A confirmed ID is always exact. Name-level ambiguous confirmations refuse.
    cases += [(names[pid],seo) for pid,seo in pairs if pid in names and seo in seos]
    baseline={name:paste_odds._match_team_safe(name,seos,full) for name,_ in cases}
    rules={'aliases':{},'suffixes':[],'rejected':[],'validation_cases':len(cases)}
    def gate(candidate):
        for name,expected in cases:
            got=baseline[name][0] or apply(name,seos,full,candidate,baseline[name])[0]
            if got is not None and got!=expected:return False
            # Do not lose any existing correct corpus match.
            if baseline[name][0]==expected and expected is not None and got!=expected:return False
        return True
    candidates=[('alias',n,next(iter(v))) for n,v in sorted(confirmed.items()) if len(v)==1]
    support=defaultdict(set)
    reserved={'state','university','college','tech','institute','campus','north','south','east','west','central','st'}
    for pid,seo in pairs:
        if pid not in names:continue
        words=names[pid].split()
        for count in (1,2,3):
            if len(words)<=count:continue
            suffix=' '.join(words[-count:]).lower()
            if set(re.findall(r'[a-z]+',suffix))&reserved:continue
            prefix=' '.join(words[:-count])
            if paste_odds._match_team_safe(prefix,seos,full)[0]==seo:support[suffix].add(seo)
    # A mascot must have independent confirmation from at least two schools.
    candidates += [('suffix',s,None) for s,v in sorted(support.items()) if len(v)>=2]
    for kind,value,target in candidates:
        candidate={**rules,'aliases':dict(rules['aliases']),'suffixes':list(rules['suffixes'])}
        if kind=='alias':candidate['aliases'][value]=[target]
        else:candidate['suffixes'].append(value)
        if gate(candidate):rules=candidate
        else:rules['rejected'].append({'kind':kind,'value':value})
    rules['confirmed_ids']=len(pairs)
    return rules
