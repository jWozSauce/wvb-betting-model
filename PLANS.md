# PLANS.md — shared plan file

## 1. How this file works

Roles per PLANNER.md / WORKER.md: the **owner** (Josh) sets goals and approves
spending and anything irreversible; the **planner** specifies and reviews; the
**worker** executes and reports. The agents communicate only through this file.

Reading order for the worker: this section, then §7 (standing restrictions),
then the task queue (§6), then the worker log and open questions for state.

Working rules:
- Append and date entries; never rewrite history. A changed decision is a new
  dated entry naming what it replaces.
- Numbered references: tasks T1…, suspected defects S1…, questions Q1….
- Verdicts are one of: confirmed / bug / risk / cannot verify, with severity
  and size where measurable.
- Worker branch policy: work on `main` is **allowed for this project** (owner
  has operated that way throughout; the Streamlit Cloud app deploys from
  `main`), but anything that changes app behavior is production — see §7.
  Rebase before push (`git pull --rebase`); the ratings bot pushes every 3h.

## 2. Inventory (planner, 2026-10-01)

Repo: github.com/jWozSauce/wvb-betting-model (public). App: Streamlit Cloud,
deployed from `main`. Purpose: NCAA D1 women's volleyball betting — model,
pricing app, bet/paper logs, injury intelligence.

- **Data pipeline** (GitHub Actions, `.github/workflows/update-ratings.yml`,
  cron 17 */3 * * *): `scripts/backfill.py` (NCAA GraphQL; raw games under
  `data/raw/<season>/games`, Actions-cached) → `build_points.py` →
  `build_elo.py` (serve/receive Elo; exports `app_data/elo_current.parquet`,
  `home_venues.parquet`, `results_current.parquet`) → `build_players.py`
  (availability) → `build_rapm_tables.py` + `fit_rapm.py --save-production`
  (`app_data/rapm.parquet`). Commits results to `main`.
- **Models**: `vbstats/elo.py` (per-point K=1.0, carryover 0.8, conf anchor
  0.1); `vbstats/model.py` Bayesian set model (6-outcome set-score dist →
  ML / ±1.5 / ±2.5 spreads / total-sets markets; params in
  `app_data/model_params.json`, fit on 2021–2025); `vbstats/rapm_price.py`
  (set-level ridge RAPM, exact set-win DP); hybrid = Elo + RAPM lineup delta.
- **App** (`streamlit_app.py`, ~1,250 lines): tabs Price a match / Best bets
  (paste board or OddsPapi live API) / Rankings / Player ranks / Results /
  Bet log. Kelly staking, market blend, venue modes, AI injury analysis
  (claude-sonnet-5), availability flags.
- **Odds**: `paste_odds.py` (board parser + team matcher), `oddspapi.py`
  (live NCAA W board, tournament 43847; books pinnacle/draftkings/fanduel/
  betonline.ag; 1 billable request per book, free tier 250/month),
  `scripts/backfill_odds.py` (free historical endpoint; 5s/fixture cooldown)
  → `data/processed/odds_hist_2026.parquet`, `scripts/backtest_odds.py`.
- **Logs**: Google Sheets worksheets Vball_Bet_Log (real bets) and
  Vball_Paper_Log (tracked model bets) via `bet_log.py`; auto-grading from
  `results_current.parquet`; 29-column schema incl. full pricing context and
  game_time.
- **Data state at writing**: 2,287 results through 2026-10-01; 6,552 RAPM
  roster rows; 77 fixtures with historical closing lines (through 09-26,
  resumable sweep); duplicate-name merge live since commit 6f92059.

## 3. Methodology (planner, 2026-10-01)

- p(set win, home serving-phase aware) from serve/receive Elo diffs + venue:
  sigmoid(b0 + b1·serve_edge/100 + b2·receive_edge/100 + b3·home) with a
  latent per-match strength shock (GH quadrature, 21 nodes) and a fifth-set
  shrink; best-of-5 combinatorics → 6-outcome distribution → all markets.
  The +b0 home intercept follows the *home-labeled* team even at flagged
  neutral sites; the app offers three venue modes (home / neutral-host /
  true toss-up = symmetrized).
- Pricing gate: edge = p_basis − vig-included implied of the odds taken
  (never devigged for the gate). p_basis = logit-space blend of model prob
  (w_model, default 0.30) and the devigged (WPO) market prob. Kelly stake
  with edge cap, from Constants sheet row "Vball".
- RAPM: two-phase ridge (set × serving-phase; receive coefs positive-good),
  recency 0.75/yr, alpha 1000; playtime-weighted 6-slot lineups.

## 4. Results on record (planner, 2026-10-01)

Provenance key: [M] = measured by planner in-session; [W] = would need
re-verification; sample sizes stated.

- [M] Warm-season match-winner accuracy (10+ prior games), chained
  2021–2025: 77–78%. Elo beats pure RAPM out-of-sample (77% vs 66–70%).
- [M] Closing-line backtest (2026 season, DK only, 75 fixtures, Aug 28 –
  Sep 25; out-of-sample w.r.t. params): ML logloss market 0.519 ≈ blend
  0.519 < model 0.542 (n=70). Deployed strategy (w=0.30, gate ≥2%): 29 bets
  18-11, **+32.3% ± 20.6%** flat-stake ROI (t≈1.56 — suggestive, not
  conclusive). Raw model edges (no blend) negative at every gate.
  Script: `scripts/backtest_odds.py`; rows in
  `data/processed/backtest_odds_2026.parquet`.
- [M] Blend-weight sweep on same data: ROI at gate 2% — w=0.30 +32.3%,
  w=0.50 +3.5%, w=1.0 −5.6%. ML logloss minimized near w≈0.15, flat to
  0.30, degrades beyond. Decision (owner, 2026-09-26): stay at w=0.30.
- [M] Paper log (n≈160): unblended model was overconfident; dogs 8-27;
  bets against shorthanded teams −33% ROI (now auto-excluded from paper
  tracking). Owner's real bets ran ~+20% ROI by skipping model dogs.
- [M] Home court ≈ +0.25 set logit ≈ 57.9% ML for even teams.

## 5. Known limitations / suspected defects

- S1 (risk, confirmed 2026-09-26): local `data/raw/2026` is stale vs the
  Actions cache (~half of boxscores missing locally). Local rebuilds of
  2026 player tables produce undercounted data — rebuild only in CI, or
  backfill locally first.
- S2 (open): 10 "possible"-tier duplicate player pairs (accent/typo
  variants, e.g. Burilović/Burilovic) remain split, awaiting owner review.
  `scripts/find_dup_players.py`; report `data/processed/dup_players_review.csv`.
- S3 (limitation): historical closing lines are DraftKings only, ML +
  spreads only (no totals anywhere historical); FanDuel/BetOnline return no
  historical trails; OddsPapi history begins Jan 2026.
- S4 (limitation): w_model=0.30 was fit on the paper log, not on closing
  lines; refit planned when the historical-lines sample reaches ~100+
  boarded games.
- S5 (risk): OddsPapi participant map (`app_data/oddspapi_participants_vb.json`)
  is a static snapshot; new teams/IDs would surface as raw numeric IDs.
- S6 (limitation): total-sets market has never been backtested against real
  lines (none exist historically; DK does not board totals for NCAA W).
- S7 (risk): `vbstats/venues.py` home-venue classification depends on NCAA
  schedule venue strings; special-event games carry placeholder venues —
  mitigated by the ⚠home-mismatch flag, not eliminated.

## 6. Task queue

(No open tasks. Owner is about to state new work — 2026-10-01.)

## 7. How to run things / standing restrictions

Run:
- Force data update: `gh workflow run update-ratings.yml` (then pull).
- Historical odds sweep (free, resumable, ~5s/fixture):
  `python scripts/backfill_odds.py` — do not run two copies.
- Backtest: `python scripts/backtest_odds.py`.
- Dup check: `python scripts/find_dup_players.py` (report only).
- Local app: `./.venv/bin/streamlit run streamlit_app.py --server.port 8654`.

Standing restrictions (planner, 2026-10-01):
- **Secrets** — never in this file, logs, reports or commits:
  `sheet_id.txt`, `oddspapi_key.txt`, `odds papi API.rtf`, the Google
  service-account JSON (outside repo), `ANTHROPIC_API_KEY` /
  `ODDSPAPI_KEY` in Streamlit secrets. All are gitignored; keep it so.
- **Quotas** — OddsPapi: 250 billable requests/month (live board = 1 per
  book per fetch; historical + account endpoints free). Google Sheets API:
  batch writes only (60 writes/min trap). Anthropic API (injury AI): owner
  pays per call; no new call sites without owner approval.
- **Production** — pushes to `main` deploy the live app. App-behavior
  changes need planner acceptance before push unless the owner directed
  otherwise for that task.
- **Irreplaceable / read-only** — the Google Sheets bet & paper logs (the
  owner's real records; append/grade via existing code paths only),
  `data/raw/` seasons (expensive to re-pull), committed historical season
  parquets (2021–2025). New artifacts go beside, not over.
- **Evaluation integrity** — 2026 closing-line data is the out-of-sample
  set for strategy claims; no fitting/tuning on it without a dated planner
  ruling that states what becomes in-sample as a result.

## 8. Worker log (append only)

(empty — no worker entries yet)

## 9. Open questions (append only)

(none open)
