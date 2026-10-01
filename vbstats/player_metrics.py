"""Shared Player ranks metrics and display-only absence annotations."""
import pandas as pd
from vbstats.names import fold_key

PHASE_RALLIES_PER_SET = 20.4


def add_metrics(roster):
    rows = roster.copy()
    rows['serve_per_set'] = (PHASE_RALLIES_PER_SET * rows.serve).round(2)
    rows['recv_per_set'] = (PHASE_RALLIES_PER_SET * rows.recv).round(2)
    rows['impact_per_set'] = (rows.serve_per_set + rows.recv_per_set).round(2)
    rows['season_impact'] = (rows.impact_per_set * rows.sets_started_cur).round(1)
    return rows


def annotation_index(roster):
    rows = add_metrics(roster)
    eligible = rows[(rows.sets_started_cur >= 1) & rows.position.notna()
                    & rows.position.astype(str).str.strip().ne('')].copy()
    groups = eligible.groupby(['team', 'position'])
    eligible['position_rank'] = groups.impact_per_set.rank(method='min', ascending=False)
    eligible['position_count'] = groups.player.transform('size')
    index = {}
    for row in eligible.itertuples():
        key = (row.team, fold_key(row.player))
        value = (f'{row.impact_per_set:+.2f} pts/set, '
                 f'#{int(row.position_rank)} of {int(row.position_count)} {row.position}')
        # Refuse collisions rather than assigning another athlete's metric.
        index[key] = None if key in index else value
    return index


def annotate(team, label, index):
    player = label.split(' (')[0]
    value = index.get((team, fold_key(player)))
    return f'{label} ({value or "unrated"})'
