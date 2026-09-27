"""Canonicalize player-name spelling variants within a team.

The NCAA feeds spell the same athlete differently across games ("Emma
McDermott" / "Emma Mcdermott", curly vs straight apostrophes, mojibake
like "Dlouhã¡"), which splits one player into several identities in the
RAPM tables and dilutes her coefficients.

Merge rule (deliberately conservative): two spellings are the same player
only when they are identical after lowercasing and dropping every
non-ascii-letter — the exact "near-certain" tier of
scripts/find_dup_players.py, reviewed and approved 2026-09-26. Accent-only
differences ("Burilović" vs "Burilovic") do NOT merge; those fold to
different keys and stay in the report's "possible" tier for manual review.

Use canonical_map() over EVERY frame that will be joined on (team, player)
— starters for all seasons plus the boxscore table — and apply_canonical()
to each, so all frames agree on one display spelling even when a feed
changed its spelling between seasons.
"""

from __future__ import annotations

import re

import pandas as pd


def fold_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", str(name).lower())


def _display_rank(name: str, count: int):
    """Best display spelling among variants: prefer interior capitals
    (feeds that flatten 'McDermott' -> 'Mcdermott' lose them), then the
    fewest mojibake-ish non-ascii chars, then the most frequent."""
    interior_caps = sum(1 for c in name[1:] if c.isupper())
    non_ascii = sum(1 for c in name if ord(c) > 127)
    return (interior_caps, -non_ascii, count, name)


def canonical_map(frames, name_col: str = "player",
                  team_col: str = "team") -> dict:
    """{(team, fold_key): display spelling} pooled over all frames, for
    every key that has more than one spelling."""
    pooled = pd.concat(
        [f[[team_col, name_col]] for f in frames if f is not None and len(f)],
        ignore_index=True)
    pooled["_key"] = pooled[name_col].map(fold_key)
    counts = (pooled.groupby([team_col, "_key", name_col], observed=True)
              .size().reset_index(name="_n"))
    cmap = {}
    for (team, key), grp in counts.groupby([team_col, "_key"],
                                           observed=True):
        if len(grp) > 1:
            variants = list(grp[[name_col, "_n"]]
                            .itertuples(index=False, name=None))
            cmap[(team, key)] = max(
                variants, key=lambda v: _display_rank(v[0], v[1]))[0]
    return cmap


def apply_canonical(df: pd.DataFrame, cmap: dict,
                    name_col: str = "player",
                    team_col: str = "team") -> pd.DataFrame:
    """Rewrite name_col per cmap. Rows stay unmerged — the caller's
    groupbys/dedupes collapse them naturally."""
    if not len(df) or not cmap:
        return df
    df = df.copy()
    keys = list(zip(df[team_col], df[name_col].map(fold_key)))
    df[name_col] = [cmap.get(k, n) for k, n in zip(keys, df[name_col])]
    return df


def canonicalize_players(df: pd.DataFrame, name_col: str = "player",
                         team_col: str = "team") -> pd.DataFrame:
    """Single-frame convenience: canonicalize within one table."""
    return apply_canonical(df, canonical_map([df], name_col, team_col),
                           name_col, team_col)
