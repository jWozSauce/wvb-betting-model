# Volleyball RAPM — Design Notes (2026-09-06)

Goal: a RAPM-style player impact model for NCAA W volleyball, feeding the
betting app (lineup-projected ratings, quantified absence costs).

## Why not NBA-style stints

NBA RAPM regresses point margin on lineups over substitution-free "stints."
Our NCAA pbp substitution lines name ONLY the entering player (10,271/10,271
sampled), so rally-level lineups cannot be reconstructed. Literature hits the
same wall in low-substitution sports (soccer possession-sequence RAPM,
arxiv 2407.17832; team-sports RAPM survey, Springer 978-3-031-98588-1_8).

## The volleyball version: set-level, two-phase

- **Unit** = one set. Lineups are stable within sets; participation is known
  from pbp starter lines + boxscore `gamesPlayed` (= sets played),
  `starter`, `participated`, `position`.
- **Outcomes** = two binomials per set, matching the team model's structure:
  points won while serving (of serve rallies) and while receiving. Rally
  winners + serving team already exist in the points tables.
- **Design matrix** = classic RAPM coding: +1 home participants, -1 away
  participants, per set.
- **Fit** = ridge logistic (or Bayesian normal priors). Output per player:
  serve-phase and receive-phase impact per 100 rallies — the player-level
  decomposition of the team serve/receive Elo split.
- **Scale**: ~20k sets/season, ~100k sets across 2021-2025, ~4.5k D1
  players/season.

## Main risk: collinearity (worse than NBA)

Stable starting sixes make teammates near-inseparable. Mitigations:
1. Multi-season stacking with recency decay (roster turnover separates).
2. Absences/subs are the identifying variation — the availability tracker
   (scripts/build_players.py) already detects these.
3. **Box-score prior** (xRAPM-style): shrink each player toward a prediction
   from their box stats (kill eff, ace/error rates, digs, reception errors)
   instead of toward zero. Biggest quality lever.

## Data plan

Boxscores are the only missing input. `backfill.py --season YYYY
--boxscores` adds them into existing raw game files (1 request/game,
resumable). Boxscore schema per player: position, number, gamesPlayed (sets),
kills/attackErrors/attackAttempts/hittingPercentage, assists/setErrors,
serviceAces/serviceErrors/serveAttempts, digs, receptionAttempts/
receptionErrors, blockSolos/blockAssists/blockingErrors, ballHandlingErrors,
points, starter, participated.

## Phases

1. Boxscore backfill 2021-2026 (running).
2. Build set-participation + player-season stat tables.
3. Fit two-phase ridge RAPM on 2021-2024; validate by predicting 2025 match
   outcomes from summed player impacts vs team Elo baseline.
4. Add box-score prior; re-validate.
5. App integration: player rankings tab; absence-adjusted match pricing
   (tie into availability flags); eventually RAPM-based season-start priors
   replacing the flat 0.8 Elo carryover.

## Betting rationale

Team ratings can't see roster changes — the source of the paper log's
underdog losses (-43% ROI on dogs). Player-level impacts turn detected
absences into quantified rating adjustments instead of unpriced risk.
