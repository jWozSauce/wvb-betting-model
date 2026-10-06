"""Explicit batch review; suggestions never become confirmations automatically."""
import difflib
import streamlit as st
import live_team_map as lm
import learned_matching as learned

def inventory(ratings,mapping):
    seos=ratings.team.tolist();full=dict(zip(ratings.team,ratings.name_full))
    rules=learned.rules_for(mapping,seos,full)
    rows=[]
    for pid,name in learned.participants().items():
        match,score=lm.resolve({'home':name,'home_participant_id':pid},'home',seos,full,mapping)
        if match and score>=.8:continue
        words=name.split();options=[]
        # A proposal is displayed as a guess, never routed into pricing.
        for count in range(len(words),0,-1):
            found,_=learned.paste_odds._match_team_safe(' '.join(words[:count]),seos,full)
            if found:options.append(found);break
        if not options:
            target=learned.norm(name)
            options=sorted(seos,key=lambda s:difflib.SequenceMatcher(None,target,learned.norm(full.get(s,s))).ratio(),reverse=True)[:1]
        rows.append({'participant_id':pid,'Provider name':name,'Suggested school':options[0] if options else None})
    return rows,rules

def render(ratings):
    st.subheader('Review team identities')
    st.caption('Suggestions are unconfirmed. Choose a batch, check each school, then save your confirmations. Confirmed IDs always take priority over learned names.')
    seos=ratings.team.tolist();full=dict(zip(ratings.team,ratings.name_full))
    try:
        if 'bulk_mapping' not in st.session_state:
            st.session_state.bulk_mapping=lm.load_local(seos)
        if st.button('Refresh saved identities',key='bulk_refresh'):
            st.session_state.bulk_mapping=lm.refresh(seos,lm.credential())
        mapping=st.session_state.bulk_mapping
        rows,rules=inventory(ratings,mapping)
    except (lm.MappingError,OSError,ValueError,KeyError,TypeError) as e:
        st.error('Cannot load validated matching data. '+(str(e) if isinstance(e,lm.MappingError) else 'Restore the matching reference files.'))
        return
    st.caption(f'{len(rows)} names need confirmation; {len(mapping)} confirmed IDs. {len(rules["suffixes"])} learned mascot rules passed validation.')
    st.dataframe(rows,hide_index=True,use_container_width=True)
    labels={r['participant_id']:r['Provider name'] for r in rows}
    # A saved/refreshed mapping can remove choices selected on the prior render.
    previous=st.session_state.get('bulk_ids',[])
    valid=[pid for pid in previous if pid in labels]
    if previous!=valid:st.session_state.bulk_ids=valid
    chosen=st.multiselect('Participants to review',list(labels),format_func=lambda p:f'{labels.get(p,p)} · {p}',key='bulk_ids')
    if not chosen:return
    suggestions={r['participant_id']:r['Suggested school'] for r in rows}
    with st.form('bulk_confirm'):
        updates={}
        for pid in chosen:
            guess=suggestions[pid]
            updates[pid]=st.selectbox(labels[pid],seos,index=seos.index(guess) if guess in seos else None,
                format_func=lambda s:f'{s} — {full[s]}',key=f'bulk_school:{pid}')
        commit=st.form_submit_button(f'Confirm & save {len(chosen)} mappings',disabled=not all(updates.values()))
    if commit:
        try:
            saved=lm.save(updates,mapping,seos,lm.credential())
            st.session_state.bulk_mapping=saved
            st.session_state.live_mapping=saved
            st.success(f'{len(updates)} confirmed mappings saved. Refresh the review list to see remaining names.')
        except lm.MappingError as e:st.error(str(e))
