# Paper Trading — How It Works in the WVB Betting App

A note for setting up the same system elsewhere. The reference implementation
lives in the `wvb-betting-model` repo: `bet_log.py` (log + grading),
`streamlit_app.py` (UI hooks, Best bets tab), `paste_odds.py` (odds ingestion).

## Purpose

Paper trading answers one question honestly: **do the model's claimed edges
realize as profit?** Every qualifying bet the model produces gets tracked —
whether or not a real bet was placed — so the scoreboard measures the model,
not the bettor's selection or nerve. The real-money log is kept separate so
the two never contaminate each other.

## Architecture

- **Storage**: two worksheets in one Google Sheets spreadsheet (the same
  "Constants" sheet that holds bankroll settings):
  - `Vball_Bet_Log` — bets actually placed (logged individually, by choice)
  - `Vball_Paper_Log` — every model-qualifying bet from an evaluated slate
- **Auth**: gspread + a Google service account. Credentials come from
  `st.secrets["gcp_service_account"]` in the cloud, or a local key file on
  the dev machine. The spreadsheet is shared (Editor) with the service
  account's email. The sheet ID is a secret (`CONSTANTS_SHEET_ID`), not in
  code — the sheet is readable by anyone who has the ID.
- Both logs use the identical row schema, so all tooling works on either.

## Row schema (one row = one bet)

| column | meaning |
|---|---|
| `logged_at` | timestamp when tracked |
| `game_date` | date of the match (grading matches results within ±1 day) |
| `matchup`, `home_team`, `away_team` | teams as canonical ids (seonames), away @ home |
| `bet` | human-readable label, e.g. `georgia +1.5 sets` |
| `market`, `side`, `point` | machine-readable encoding (see below) |
| `book`, `odds` | book name and American odds taken |
| `stake` | Kelly stake at log time |
| `edge` | model prob − vig-included implied prob of `odds` |
| `model_prob`, `model_fair` | model probability and fair odds at log time |
| `status` | `pending` → `won` / `lost` / `push` |
| `profit`, `graded_at` | filled by grading |

Market encoding (volleyball; adapt per sport):
- `ml` — side `home`/`away`
- `spread` — side `home`/`away`, point = picked team's set spread (e.g. `-1.5`)
- `total` — side `over`/`under`, point = total-sets line (e.g. `4.5`)
- `five` — side `yes`/`no` (match goes 5 sets)

The key design point: **freeze everything at log time** — odds, stake, edge,
and the model's probability. Later analysis (calibration, ROI by claimed
edge) depends on knowing exactly what the model believed when the bet was
available, not what it believes after retraining.

## Logging flow

1. The app evaluates a slate (pasted sportsbook board → parsed games →
   model prices every market → Kelly gate/sizing).
2. One click ("Track full card (paper)") appends **all bets with stake > 0**
   to the paper worksheet with `status=pending`.
3. **Dedupe**: before appending, existing rows are read and any row with the
   same `(game_date, matchup, bet)` is skipped — re-pasting the same slate
   later in the day cannot double-track. (`bet_log.log_bets(..., dedupe=True)`)
4. Real bets are logged separately, one at a time, from the pricing screens
   into the real-money worksheet.

## Grading flow

1. Grading runs against the app's own **results table** (final set scores per
   match, refreshed nightly from the NCAA API by a GitHub Actions job) — no
   separate scores API needed.
2. For each `pending` row: find the match by `(home_team, away_team)` within
   ±1 day of `game_date`. Matching is **orientation-tolerant**: if the exact
   home/away orientation isn't found, the flipped fixture is used and the
   set counts are translated into the bet's frame (bets sometimes get logged
   with home/away swapped; this must not strand them as pending forever).
3. Settle from set scores per the market encoding (`bet_log._settle`):
   moneyline by match winner; spreads by set margin + point (margin exactly
   zero after the line = push); totals by total sets vs the line; `five` by
   whether 5 sets were played.
4. `profit` = stake × (odds/100) for positive odds or stake × (100/−odds)
   for negative, on wins; −stake on losses; 0 on pushes.
5. One button grades **both** worksheets. Grade after the nightly results
   update has landed (morning), so yesterday's finals are available.

## Reporting

The app's Bet log tab shows, for the paper log: tracked-bet count, W-L-P
record, total profit, and ROI (profit / total staked on settled bets). Once
10+ bets settle, it adds **ROI by claimed-edge bucket** (2–3%, 3–6%, 6–10%,
10%+). This is the main diagnostic: a calibrated model earns more at higher
claimed edges; if the buckets are flat or inverted, the claimed edges are
overconfident and the gate (min edge / conservative percentile) needs
tightening.

## Conventions that matter (easy to get wrong)

- **Edge is vig-included**: edge = model prob − implied prob of the odds
  actually taken (−110 implies 52.38%, not 50%). No de-vigging anywhere.
- **Stakes use fractional Kelly with an edge cap** (edge above the cap is
  clamped before sizing) and a **min-edge gate** (below it, stake = 0 and the
  bet doesn't qualify for tracking).
- Optionally gate/size on a **conservative percentile of the model's
  posterior** (this app uses p20 from 500 parameter draws) rather than the
  point estimate; log which basis was used.
- Team names must be **canonical ids** shared with the results source (this
  app fuzzy-matches book names → NCAA seonames at parse time, with an alias
  table for the hard cases), or grading can't find matches.
- Exhibitions / non-regulation matches are excluded from the results table,
  so bets on them would stay pending — don't track them.

## Minimum pieces to replicate for another sport

1. A results source with final scores per match, refreshed automatically.
2. Canonical team ids shared between bets and results (+ name matcher).
3. A settlement function per market type, from final scores.
4. The two worksheets + service-account auth + this row schema.
5. Freeze-at-log-time discipline, dedupe on `(game_date, matchup, bet)`,
   orientation-tolerant matching, and the ROI-by-edge report.
