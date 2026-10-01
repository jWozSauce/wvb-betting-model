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

**2026-10-01 — Owner's instruction (verbatim in substance):** review what the
app does and how it is set up, then have the worker do a full audit of the
app and its statistical methods. Planner's review is §2–§4 of this file;
the audit is T1 below.

### T1 — Full audit of the app and its statistical methods (review only)

**Status: open. Report first; change nothing under review** (WORKER.md §3,
"In a review task, report first"). This is the independent review that
PLANNER.md §3 calls for: the planner wrote most of this system's
specifications, so treat §2–§5 of this file as *claims to verify, not
facts* — refuting an entry there is a successful outcome.

**Purpose.** The owner is staking real money on this system. This audit
decides (a) whether any live pricing, staking, logging or grading path has
a correctness bug, and (b) whether the statistical claims in §4 survive
independent scrutiny. Findings feed a follow-up repair queue.

**Scope — audit each area, with a verdict (confirmed / bug / risk /
cannot verify + severity + size) per numbered item:**

1. **Data pipeline integrity.** `scripts/backfill.py`, `build_points.py`,
   `vbstats/parse.py`. Reconstruction of scoreless feeds (dedup rule),
   exhibition/non-regulation exclusion, daily-file staleness handling.
   Reconcile counts: matches per season vs points rows vs
   `results_current.parquet` (2,287 rows at 2026-10-01).
2. **Elo correctness, especially leakage.** `vbstats/elo.py`,
   `build_elo.py`. Verify pre-game snapshots truly precede the game
   (chronological ordering incl. same-day ties), conference-anchor updates
   only on cross-conference points, carryover application, and the
   rated-games identity (total team-games = 2 × matches).
3. **Bayesian set model.** `vbstats/model.py`, `scripts/fit_model.py`.
   GH-quadrature integration correctness, 6-outcome distribution sums to 1
   over a parameter grid, fifth-set shrink, home/venue term, best-of-5
   combinatorics vs a brute-force enumeration, Laplace draws usage for the
   p20 basis. Confirm params were fit on 2021–2025 only (planner probe
   2026-10-01: `model_params.json` unchanged since commit da67757 and the
   workflow never runs `fit_model.py` — verify independently).
4. **RAPM.** `scripts/fit_rapm.py`, `vbstats/rapm_price.py`,
   `vbstats/names.py`. Design-matrix sign conventions (receive coefs
   positive-good), phase table vs raw points spot-check, recency weights,
   set-win DP vs Monte Carlo simulation (incl. deuce fixed point, race to
   15 in the fifth), playtime-weighted lineup normalization, and that the
   2026-09-26 name canonicalization did not merge distinct athletes
   (sample near-certain merges against boxscore jersey numbers).
5. **Pricing, staking, blending.** `kelly.py`, pricing paths in
   `streamlit_app.py`, `paste_odds.py` (`market_devig`, `price_market`),
   `oddspapi.py` (decoding: sides, points, best-line, anchor devig).
   Verify: edge gate uses vig-included implied; WPO devig matches the
   NCAAF reference implementation; logit blend; Kelly with edge cap;
   p20-vs-point basis used consistently between display, gate and stake.
6. **Live-vs-tested parity (highest-value item).** Compare the pricing
   path `scripts/backtest_odds.py` exercised against the path the Best
   bets tab executes live, feature by feature (venue/neutral handling,
   basis, anchor book, dedup of best line). Name every difference and
   quantify any that could change which bets clear the gate.
7. **Bet logging and grading.** `bet_log.py`. `_settle` per market incl.
   pushes and the five-sets market; orientation-tolerant `_find_result`
   (could the ±1-day window or flipped matching ever grade against the
   wrong fixture — e.g. rematches?); dedupe keys; half-written-row repair;
   header migration. Read-only on the real sheets: verify logic against
   `results_current.parquet` and synthetic rows, not by writing.
8. **Team/player matching.** `paste_odds.match_team` (aliases, acronym
   rules, mascot stripping, `_school_core`): adversarial cases, and an
   exhaustive pass — every 2026 D1 team's plausible book spellings resolve
   to the right seoname or to None (never silently to a wrong team).
9. **Statistical claims in §4.** Reproduce independently: warm accuracy
   77–78%; backtest headline (29 bets, 18-11, +32.3%, and the w-sweep);
   ML logloss triple (0.542 / 0.519 / 0.519). Scrutinize the backtest
   itself for selection effects (join losses, fixture matching, the
   dedup-best-line step, post-start "closing" prices leaking in-play
   odds). State what the evidence can and cannot support at n=29.
10. **App/runtime risks.** Cache staleness patterns, session-state guards,
    secrets handling (nothing secret reachable from the public repo),
    Sheets quota discipline, OddsPapi quota math.

**Deliverables.**
- `AUDIT_2026-10.md` at repo root: verdict table up front (one row per
  numbered item above), then per-area findings, each claim with file:line
  or a command + output. Written for the owner.
- Any reproduction scripts under `scripts/audit/` (new directory; nothing
  existing modified).
- A dated worker-log entry in §8 summarising state and pointing at the
  report.

**Acceptance gate.** (a) Every item 1–10 has a verdict with evidence;
(b) the four §4 reproductions in item 9 are attempted and each either
matches within stated tolerance or the discrepancy is explained with
evidence; (c) at least the probability-distribution and DP checks (items
3, 4) are validated against brute force, not against the code under test;
(d) zero modifications to existing files other than PLANS.md §8/§9.

**Boundaries.**
- Report only — no fixes, no behavior changes, even obvious ones; propose
  them as numbered follow-ups in the report.
- Google Sheets: read-only. No writes of any kind to the bet/paper logs.
- OddsPapi: free endpoints (historical, account) freely; at most 4
  billable requests total if live-board verification needs them.
- No Anthropic API calls.
- Do not rebuild 2026 player tables locally (S1) and do not start a second
  `backfill_odds.py` sweep.
- Committing the audit report + PLANS.md entries to `main` is authorized;
  nothing else.

**Staging.** Items 1–5 and 7–8 are independent — any order. Do item 6
after 5. Do item 9 last (it depends on understanding from 3/5/6). If a
**bug verdict with severity high** appears in any live money path
(pricing, staking, grading), write an open question flagging it
immediately rather than waiting for the full report.

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
