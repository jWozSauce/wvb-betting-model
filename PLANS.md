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

**2026-10-01 (later) — Owner's instruction (verbatim in substance):** all
coding is done by the worker (Codex) per the planner/worker split. The
planner (Claude) specifies, reviews and reports, and writes no application
code — including obvious or one-line fixes, which become tasks or named
repairs in a review. (Historical note for the record: everything in the
repo up to commit 6f92059 / 2026-09-26 was written by the planner's model
in earlier sessions, before this split existed. T1's independence
requirement exists for exactly that reason.)

**2026-10-01 (later) — Owner's instruction (verbatim in substance):** one app
upgrade, moved to the front of the line (T2 before T1). Best bets gets a
third way to pull games to auto-price: the NCAA schedule (all divisions),
pricing every game, with home / neutral / true-neutral determined per game
from the schedule. Each game gets a dropdown to change that venue input on
the fly, repricing that game only (not the whole slate as today). Selecting
a game shows all generated odds — essentially a prepopulated individual
pricing screen like Price a match. **Order of work: T2 first, then T1.**

### T2 — Best bets: NCAA-schedule slate source with per-game venue control and drill-in pricing

**Status: open. Do this before T1.**

**Purpose.** Today the Best bets tab only prices games a sportsbook boards
(paste or OddsPapi) and applies ONE venue mode to the whole slate. The owner
wants model prices for the FULL NCAA slate — including unboarded games —
with per-game venue classification and per-game override, and a one-click
jump from any game to a full pricing panel.

**What is already known (planner; verify, do not trust).**
- `NCAAClient.contests(date, season, division)` (vbstats/ncaa.py) returns
  the day's schedule per division (1/2/3). Planner probe 2026-10-01: 121 D1
  contests on 2026-10-02; each contest has `contestId`, `startTimeEpoch`,
  `teams[].seoname` + `teams[].isHome` + full names — but **no venue**.
  Venue requires the existing per-game call (`client.game(cid)` →
  `location`), as `vbstats/venues.py:slate_venues` already does.
- `app_data/home_venues.parquet` maps teams → modal home venue (with `n`
  counts for owner-of-venue resolution). `app_data/elo_current.parquet`
  holds ratings for ~392 active teams (D1-centric; many D2/D3 teams have
  ratings from cross-division games, many do not).
- The Price a match tab's board (market table incl. ML/spreads/totals,
  p20 basis, Kelly box, bet logging) lives inline in `streamlit_app.py`
  (~lines 380–660); the Best bets evaluation path is separate.
- Venue modes and their pricing semantics are in §3. The home intercept
  follows the home-labeled team; "True toss-up" averages both label
  orientations.

**Specification.**
1. Add a third option to the Best bets source selector: **"NCAA schedule
   (price everything)"**, alongside Live API and Paste. Date picker
   (default today, allow +/- a few days). On fetch: pull contests for
   divisions 1–3 for that date, keep games where BOTH teams have ratings
   in `elo_current.parquet`; list the rest separately as "not priced
   (unrated team)" with counts — never silently dropped.
2. **Per-game venue auto-classification** from the schedule + venue data,
   with these defaults (planner's ruling; surface the label so the owner
   can see why):
   - game venue == NCAA home team's modal venue → **Home court**;
   - game venue == the AWAY-labeled team's modal venue → **Home court
     with the host as home** (price the de-facto host as home; flag it);
   - venue known but neither team's gym → **True toss-up (symmetrized)**,
     label "neutral (3rd site)" or "neutral (X's gym)";
   - venue unknown/missing → **Home court** per NCAA's isHome, flagged
     "venue ?" (most such games are ordinary home games; the dropdown
     allows correction).
   Venue lookups: only for games that will be priced; cache per contestId
   (long TTL — venues do not change) so a slate's first load does the
   lookups once (~0.25s throttle each; show progress) and later loads are
   instant.
3. **Per-game venue dropdown** on each row (options: Home court /
   Neutral host-matters / True toss-up), defaulted to the
   auto-classification. Changing one game's dropdown reprices THAT game's
   rows only — no full-slate re-fetch or re-parse. (Streamlit reruns are
   fine; the requirement is that the user doesn't have to re-run the
   slate action or lose other games' state. Keep slate data in
   session_state keyed by date; price from cached ratings.)
4. **Slate table**: one row per game — time, away @ home, site label,
   venue dropdown, model ML both sides (fair odds), spread fair odds,
   total fair odds — enough to scan for interesting games. (No stake/edge
   columns here: there are no book odds in this source.)
5. **Drill-in**: a per-game "Price this game" control. Selecting it
   renders, inline below the table, the FULL pricing panel prepopulated
   with that game's teams and its current venue-dropdown value — the same
   board as Price a match (all markets incl. p20 conservative basis,
   set-score distribution, odds-entry + blend + Kelly + "Log this bet").
   **Implement by refactoring the Price a match board into a reusable
   function** (parameterized by home, away, venue_mode, key-prefix for
   widget keys) called from both tabs — a pure refactor of the existing
   tab, no behavior change there. Do NOT copy-paste a second divergent
   pricing path (see T1 item 6: parity between paths is a named risk).
6. The existing Paste and Live API sources, and the Price a match tab,
   must behave exactly as before.

**Deliverables.** Branch `t2-schedule-pricing` with small single-purpose
commits; a worker-log entry with: a parity check (drill-in panel vs Price
a match tab produce IDENTICAL probabilities for 3 named games × 3 venue
modes — table of numbers in the log), a timing measurement for a full
slate first load and for a single-game venue change, and screenshots or a
text dump of the slate table for one real date.

**Acceptance gate.**
(a) Parity: drill-in == Price a match to 4 decimal places on the 3×3
check; (b) a Friday-sized slate (≥80 rated games) first-loads in under
~3 minutes with progress shown, and a single-game venue change does not
re-fetch the schedule or venues; (c) unrated-team games are listed with a
count that reconciles (priced + unpriced == fetched); (d) auto-venue
labels match `slate_venues` semantics on a 10-game spot check; (e) paste
and Live API sources verified unchanged (run each once).

**Boundaries.**
- Production: implement on the branch; the planner reviews the log
  evidence and accepts BEFORE merge to `main` (which auto-deploys).
- No OddsPapi billable calls needed for this task (0 expected); NCAA API
  is free but throttled — keep the existing client delay.
- No writes to the Google Sheets logs except via the existing untouched
  log-bet code path, and none during testing (do not press-test "Log this
  bet" against the real sheet; verify by code path identity instead).
- No changes to model/Elo/RAPM code, `bet_log.py`, or the workflow.

**Staging.** (i) Schedule fetch + rated-game filter + counts; (ii) venue
auto-classification + caching; (iii) slate table + per-game dropdown
repricing; (iv) the Price-a-match refactor to a reusable function with a
no-behavior-change check on the existing tab; (v) drill-in wiring +
parity evidence. Report after (iv) if the refactor turns out riskier than
specified — stop and ask rather than forking the pricing code.

**2026-10-01 (later) — Planner's note to the worker:** T2 is authorized to
START NOW — no further instruction is coming. Monitor check-ins that only
re-read the plan do not advance it; begin T2 stage (i) on branch
`t2-schedule-pricing`. Also: commit your worker-log entries rather than
leaving them as uncommitted edits, so the audit trail survives.

**2026-10-01 (later) — Owner's instruction (verbatim in substance):** review
whether the market blend must be as strict as it is — at 70% market / 30%
model, even major model-vs-market disagreements fail the edge requirement.
Task T3 below. Order of work: T2, then T3, then T1.

### T3 — Is the blend/gate too strict? (analysis + recommendation; no app change)

**Status: open. Run after T2.** Deliverable is a report and a
recommendation; any change to the deployed default (w_model or min edge)
is the owner's decision afterward.

**What is already known (planner, measured 2026-10-01 on
`data/processed/backtest_odds_2026.parquet` — verify, do not trust).**
At w=0.30 with a 2% gate vs vig-included implied: market 50% requires
model ≥64.3% to bet (60%→73.7%, 70%→82.9%). On DK closing lines
(Aug 28–Sep 25): bets passing the gate 18-11, +32.3%; positive
disagreements of 8+ points that FAIL the gate went 10-26 (−30.6%);
5–8-point disagreements −12.5%; marginal bets admitted by w=0.40@2% went
2-10 (−63%), by w=0.50@2% 6-17 (−33%). I.e. current evidence says the
strictness is load-bearing — but n is small and it is closing lines only.

**Integrity note (planner's ruling).** The existing backtest parquet has
already been used to sweep w once (2026-09-26), so results on it are
confirmatory/diagnostic, not fresh out-of-sample. The games swept AFTER
2026-09-26 are the clean increment; report them separately.

**Specification.**
1. Extend the historical sweep first: run `scripts/backfill_odds.py`
   (free endpoint, resumable, one copy only) to cover finished fixtures
   through yesterday; rebuild the backtest rows with
   `scripts/backtest_odds.py`. Report how many new boarded fixtures the
   extension added.
2. On the full sample and on the post-09-26 increment separately:
   (a) ROI/record by disagreement bucket (p_model − p_mkt: 2–5, 5–8,
   8–12, 12+ points), for bets failing and passing the current gate;
   (b) the (w × gate) grid, w ∈ {0.30, 0.35, 0.40, 0.50}, gate ∈
   {1%, 2%, 3%, 4%, 6%}: n, record, flat-stake ROI, and a bootstrap 90%
   interval on ROI (resample bets, ≥10k draws, seed published);
   (c) for each loosening relative to (0.30, 2%): the MARGINAL bets it
   admits and their record — the decision-relevant quantity;
   (d) ML logloss of the blend across w on closing devigs.
3. Cross-check against the paper log (read-only via `bet_log.read_log`,
   or export): same bucket analysis at TAKEN prices rather than closing,
   acknowledging those prices predate close. State where the two datasets
   agree and disagree.
4. Pre-registered decision frame (planner): recommend changing the
   default only if some (w, gate) cell beats (0.30, 2%) on total profit
   AND its bootstrap interval excludes the kind of loss the marginal-bet
   analysis shows; otherwise recommend keeping current settings and name
   the sample size at which the question should be reopened.

**Deliverables.** `BLEND_REVIEW_2026-10.md` at repo root (verdict and
recommendation up front, owner-readable); analysis code under
`scripts/audit/`; worker-log entry with the headline numbers.

**Acceptance gate.** All four analyses present with reconciling bet
counts; bootstrap seed published; increment (post-09-26) reported
separately; no change to any app default in this task.

**Boundaries.** Google Sheets read-only; no OddsPapi billable calls
(historical + account endpoints only); only one backfill_odds.py
instance; nothing merged to `main` except the report, scripts/audit/,
and PLANS.md entries.

**2026-10-01 (later) — Owner's instruction (verbatim in substance):** have
the worker audit the player-based model procedure and the hybrid (team Elo
+ player lineup adjust). To the owner they do not seem to work correctly
or sensibly: prices "barely move", and in the hybrid view players who are
not playing are ALREADY de-selected — their absences appear to be priced
in already, so there is nothing left to unselect and the lever seems
pointless. Additionally (feature): wherever an injured/absent player is
shown in that section, append in parentheses their player-model impact
and their rank within their position on their team. Tasks T4 (audit) and
T5 (feature). **Order ruling (planner): T2 first (in progress), then T4,
then T3, then T5, then T1.** T5 waits for T4 because T4 may change how
absences are displayed.

**2026-10-01 12:05 EDT — Owner's clarifications (verbatim in substance) +
planner amendment to T4/T5:** (1) Confirmed understanding: Team Elo mode
never auto-prices absences — only Hybrid and Player RAPM do. (2) The
owner's "barely move" observations involved less-impactful players than
Murray (who is ~2nd most impactful in the league); audit should calibrate
expectations for mid-tier players — T4's finding answers this: removal
REDISTRIBUTES the player's playtime weight to remaining selected players,
so removing a below-lineup-average starter can move the price little or
even UP (measured: +2.2pp, +5.5pp). **Open owner decision D1:** should
"remove player" instead model a replacement-level substitute (bench
semantics) rather than redistribution? Planner recommendation: yes —
redistribution answers "what if her minutes go to the others", not "what
if she's injured"; an injury should pull in a replacement. Worker holds
on this until the owner decides. (3) T5 approved; units per Q1 ruling.

### T4 — Audit of player (RAPM) and hybrid pricing behavior in the app (review + design proposal)

**Status: open. Report and propose; change no pricing behavior.**

**Purpose.** Decide whether the player/hybrid modes are (a) buggy,
(b) working as designed but with a design that defeats the owner's use
case, or (c) both — and produce concrete repair/redesign proposals for
the owner to choose from.

**Planner's context — verify, do not trust. Much of the owner's
observation may be DESIGN, not bug:** by a 2026-09 decision, the hybrid
reference lineup is the season-typical rotation (full roster,
playtime-weighted), while the default SELECTED lineup is the last match's
set-1 starters. Consequence: a player who already missed the last match
is absent from the default selection, and her absence is already priced
(selection vs season reference) — so unselecting her again does nothing;
RE-selecting her prices her return. That matches the owner's report
exactly. The audit must still check for real defects on top of this.

**Specification.**
1. **Reproduce magnitudes.** Benchmarks recorded 2026-09-06: removing
   Harper Murray moved Nebraska ML 90.9%→83.6% (pure RAPM, vs Kansas) and
   96.6%→92.7% (hybrid). Reproduce equivalent single-star removals today
   (Murray, Babcock, plus 2 mid-tier starters). If today's moves are
   materially smaller, bisect: prime suspect is the 2026-09-26 name
   canonicalization (did `sets_started_cur`, `in_last_lineup`, or the
   availability↔rapm name join change the default lineups or weights?).
2. **Trace the lineup math** end to end in `streamlit_app.py` +
   `vbstats/rapm_price.py`: default-selection construction, season
   reference construction, playtime weights (6·(sets+1)/Σ), the hybrid
   delta (Elo logit + RAPM DP delta), and whether UI selections actually
   reach the pricing call (widget keys/state). Verify the no-edit
   identity: untouched hybrid == pure Elo price, exactly.
3. **Expected-size analysis.** From the fitted coefficients, what SHOULD
   removing a top-5 player move a set probability / match ML, given alpha
   =1000 shrinkage and playtime weighting? State whether "barely moves"
   is a bug or the honest size of the estimate — with numbers.
4. **Design proposals** (numbered, for the owner to pick): at minimum one
   proposal that makes the lever legible — e.g. default selection =
   season rotation with currently-absent players shown pre-removed but
   RE-ADDABLE, each labeled "already priced out", so the user sees what
   the model has done and can override in both directions; and a
   what-if display showing the price with and without each absent player.
5. Verdicts per PLANS rules on: lineup defaults, reference lineup, delta
   computation, UI→pricing wiring, magnitude sanity.

**Deliverables.** `PLAYER_MODEL_AUDIT_2026-10.md` (verdicts + proposals up
front), repro script under `scripts/audit/`, worker-log entry.

**Acceptance gate.** Item-1 reproductions with numbers; the no-edit
identity tested; magnitude analysis with explicit expected-vs-observed
table; ≥2 design proposals with their pricing implications stated.

**Boundaries.** No changes to pricing code or app behavior in this task;
Sheets read-only; no billable API calls; S1 applies (no local 2026 table
rebuilds).

### T5 — Feature: absent-player annotations (impact + position rank)

**Status: queued — starts after T4 is reviewed (its proposals may change
where/how absences are displayed).**

Wherever the player/hybrid pricing section (and its availability/absence
display) names an injured or absent player, append in parentheses that
player's impact as measured by the player model and their rank within
their position ON THEIR TEAM, e.g. "H. Murray (−1.8%/set, #1 of 3 OH)".
Requirements: (a) the impact number must be computed by the SAME code the
Player ranks tab uses (import/shared function, not a reimplementation),
so the two never disagree; (b) rank counts only teammates with the same
position label and ≥1 set started, and states the denominator; (c)
unrated/unknown players degrade to "(unrated)" without error; (d) spot
check in the log: 5 players' annotations vs the Player ranks tab, exact
match. Branch + planner acceptance before merge (production rule).

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

### 2026-10-01 09:53 EDT — Plan monitor: interim result; T2/T1 not started

- **Confirmed:** first scheduled check found this plan, previously absent at
  the initial role review. Read the full plan; reviewed SHA-256 before this
  entry: `86905e0b82b9d76c2411c5aab016789f62e8b2d8d88b143aab2e9a18f4788af1`.
  Current order is T2 (schedule pricing) before T1 (review-only audit).
  Implementation and statistical claims have not yet been verified.
- **Owner instruction, directly in this chat, 2026-10-01:** check PLANS.md
  every five minutes until 17:00 America/New_York today, then discontinue.
  Automation `check-volleyball-plan-until-5-pm` is active with that cutoff;
  this is its first verified scheduled run. No duplicate monitor is needed.
  It can be stopped with the Codex automation tool by setting this ID to
  PAUSED.
- This check reviewed instructions only; no app changes, tests, external
  API calls, or commits were made. Repository is on `main`; the four existing
  untracked basketball reference files were preserved. No implementation
  jobs were started by this worker.
- Next execution task is T2 stage (i), on the specified task branch, subject
  to the plan's production and acceptance boundaries. Scheduled checks
  continue through the owner's cutoff; unchanged checks will stay quiet.

### 2026-10-01 10:33 EDT — Plan monitor: interim result; T2/T1 not started

- **Confirmed:** reviewed the full updated plan, SHA-256 before this entry
  `8d518e355d5e596651631e3d4d987730c95d40a844755c10624bbfe711d79328`.
  New owner instruction in §6 assigns all application coding, including
  small fixes, to the worker; the planner specifies and reviews. T2 remains
  before T1, with unchanged task scope and acceptance gates.
- This scheduled check made no app changes, ran no tests or external API
  calls, and created no commits or implementation jobs. Implementation and
  model claims remain unverified. The existing five-minute monitor continues
  until 17:00 EDT; do not start a duplicate. Next execution task remains T2
  stage (i) on its specified branch.

### 2026-10-01 10:57 EDT — T2 in progress: baseline and schedule probe

- **Confirmed:** work has begun on `t2-schedule-pricing`; baseline application
  is preserved by commit `2efbb95` (latest planner-only commit). Reviewed its
  amendments against `ecff7e3`: explicit T2 start instruction and new order
  T2 → T3 → T1. Owner directly requested checking for tasks in this chat.
- Free NCAA D1 probe returned 121 contests for 2026-10-02 in 0.629 seconds;
  raw returned contests and timestamp are in
  `evidence/t2-20261001/probe-d1-20261002.json`. No paid calls or Sheets
  writes. First sandboxed request failed DNS; approved network retry worked.
- **Risk:** the original Price a match tab automatically calls paid injury
  analysis. Extraction will leave that call at its existing site and share
  only the pricing panel, avoiding a new paid call from schedule drill-in.
  Tests will block paid APIs and Sheets writes.
- One pre-existing Python process was observed; it is left untouched. No
  worker background jobs started. Existing untracked reference files preserved.
  Next: implement schedule filtering, venue caching, and the per-game UI;
  then validate shared-panel parity and required gates. No acceptance claimed.

### 2026-10-01 11:08 EDT — T2 implementation complete, awaiting acceptance

**Result:** requested implementation and local validation complete on
`t2-schedule-pricing`. Commits: `28505ca` (schedule source), `acd46d6`
(shared panel + integration), `4c1ea87` (validation and evidence). Baseline
and initial report: `6549efc`. No merge, push, or deployment performed.

- **Confirmed, gate (a):** all 16 market rows (point probability, p20,
  fair odds, min-edge odds) exactly equal between the original manual app
  at `2efbb95` and the new manual panel for 3 games × 3 venues. A separate
  3×3 comparison of real schedule drill-ins to that original manual app
  also passes exactly, exceeding the four-decimal requirement:

  | Away @ Home | Venue | Manual home ML | Drill-in home ML | Manual p20 | Drill-in p20 |
  |---|---|---:|---:|---:|---:|
  | Morgan St @ NC Central | Home | .6529 | .6529 | .6493 | .6493 |
  | Morgan St @ NC Central | Neutral host | .6608 | .6608 | .6381 | .6381 |
  | Morgan St @ NC Central | Toss-up | .5705 | .5705 | .5691 | .5691 |
  | Butler @ Seton Hall | Home | .1669 | .1669 | .1628 | .1628 |
  | Butler @ Seton Hall | Neutral host | .1723 | .1723 | .1578 | .1578 |
  | Butler @ Seton Hall | Toss-up | .1256 | .1256 | .1220 | .1220 |
  | Dayton @ Fordham | Home | .0678 | .0678 | .0656 | .0656 |
  | Dayton @ Fordham | Neutral host | .0706 | .0706 | .0628 | .0628 |
  | Dayton @ Fordham | Toss-up | .0490 | .0490 | .0465 | .0465 |

- **Confirmed, gates (b)/(c):** real 2026-10-02 schedule: 330 division
  listings minus 1 duplicate = 329 unique games = 126 priced + 203
  explicitly unpriced. All three divisions fetched; venue calls only for
  rated games. 129 free requests, 41.970s cold acquisition; warm acquisition
  0.016s with network calls prohibited. AppTest slate rendering 0.420s;
  single-game venue change 0.373s, exactly 1 model evaluation and **0**
  schedule/venue re-fetches. Acquisition and UI timings measured separately,
  not a browser wall-clock measurement. Progress is emitted throughout and
  wired to Streamlit's progress bar. Source/date switches preserve overrides.
- **Confirmed, gate (d):** 10/10 legacy `slate_venues` labels and venues
  match on replay of captured real responses (including neutral and missing
  venues). Synthetic checks cover the away-host swap; no such case occurred
  in this slate. Known venue with missing home-map entry uses the explicit
  T2 neutral fallback; legacy `slate_venues` would say unknown in that case.
- **Confirmed with limits, gate (e):** existing Paste/Live API execution
  block is AST-identical after indentation under the new source branch.
  Both UI paths were executed once and yielded identical two-market cards.
  Live API response was an injected fixture: **cannot verify current external
  OddsPapi compatibility** from this check; zero billable calls made. No
  parser, decoder, model, RAPM, bet-log, or workflow files changed.
- Additional checks: 5/5 boundary tests pass; original vs refactored hybrid
  and player panels exactly equal for one matchup; both panels can coexist
  without widget collisions. Logging record and write path are shared
  unchanged; no Log button pressed. Tests block external network, real
  Sheets writes, and paid injury calls. Original manual tab retains its
  automatic news behavior; schedule panel does not trigger it.
- Evidence: `evidence/t2-20261001/full-slate-1/` contains timestamped raw
  responses, `timing.json`, `slate_table.csv` (126 rows), and
  `venue_spot_check.csv`. `full-ui-check-1/` contains both parity CSVs and
  `extra_checks.json`. Repro scripts are under `scripts/validation/`.
- **Risk, existing venue data:** matching legacy labels does not establish
  real-world accuracy; e.g. SECU Arena is attributed to Hofstra by the modal
  map in this sample. Overrides and visible site labels remain necessary.
- Review locally with `WVB_ENABLE_NCAA_SCHEDULE=1 ./.venv/bin/streamlit run
  streamlit_app.py --server.port 8654`. The feature switch defaults off
  until accepted. No server or worker job is left running; only the authorized
  five-minute plan monitor remains. Prior reference files are untouched.
- Reviewed planner commit `183fa96`: next is T4, then T3; T5 is explicitly
  queued until T4 review, then T1. T2 acceptance is reserved to the planner.

### 2026-10-01 11:14 EDT — T4 implementation complete, awaiting acceptance

- **Report complete:** `PLAYER_MODEL_AUDIT_2026-10.md`, commit `13886ee`,
  reproduction `scripts/audit/player_model_audit.py`; detailed CSV/JSON
  evidence in `evidence/t4-20261001/`. No application/pricing changes by T4.
- **Confirmed:** four removals × player/hybrid modes reach the actual UI
  and agree with expected prices to four decimals. Murray vs Kansas:
  player 90.1057%→83.5976%, hybrid 95.9723%→92.5890%. Babcock vs Kansas:
  player 73.2133%→49.6167%, hybrid 79.6445%→57.5465%. Top-five analysis
  and pre/post `6f92059` snapshots do not support broadly diminished star
  effects from canonicalization.
- **Bug, medium:** no-edit UI promise is false for last-match defaults:
  Nebraska–Kansas Elo .9337 vs default hybrid .9597. Full season-reference
  selection restores exact equality for all 16 board rows, including p20.
- **Risk, high design impact:** removals redistribute weight; deleting
  lower-relative-impact starters can improve the forecast. Sigler raises
  hybrid ML 1.0239pp; Watson raises it 4.5875pp. Do not interpret the
  control as a causal injury estimate or enlarge effects without validation.
- **Bug, medium:** 27 rated teams lack rosters; Spring Hill–Kansas in Player
  mode raises TypeError rather than gracefully refusing to price. This
  pre-existing path remains unchanged, per T4's review-only boundary.
- Absence reconciliation: 331 flagged core absences = 327 already deselected
  + 2 matched but selected + 2 unmatched encoding variants. Proposals in
  the report distinguish clear UI wording from replacement-model changes.
- No paid calls, Sheets writes, or player-table rebuilds. No worker jobs
  left running. Next is T3. T5 remains queued awaiting T4 review, and Q1
  below requests a unit clarification for its annotations.

### 2026-10-01 11:22 EDT — T3 interim result; extension blocked on Q2

- **Diagnostic report:** `BLEND_REVIEW_2026-10.md`, commit `7db4fc4`, code
  `scripts/audit/blend_review.py`; evidence `evidence/t3-20261001/run-1/`.
  All 20 grid cells, marginal additions/removals, disagreement buckets,
  logloss, and the available paper-log comparison are present. Fresh-data
  extension and final recommendation remain unfinished.
- **Confirmed:** cached headline reproduces 29 bets, 18–11, +32.2931% ROI.
  Rebuilding with the unchanged script gives 28, 17–11, +29.5179%. Four
  fixtures / 14 cached probabilities match the opposite venue flag from
  current inputs; Florida −2.5 moves below the 2% gate. Cause of cached
  artifact provenance remains unverified; original files were hash-preserved.
- Seed 20261001; 10,000 bet-bootstrap draws per cell. Baseline rebuilt
  ROI 90% interval −4.85%..+63.63%. At a 2% gate, w=.40 adds 13 bets,
  3–10, −49.75% marginal ROI. The favorable .40/.03 cell adds only two
  winners; report discusses its nominally positive interval and selection
  limits explicitly. No defaults changed or parameters fit.
- Paper read performed with a read-only OAuth scope, bypassing `_ws`
  because that helper can migrate headers even from `read_log`. 159 rows
  = 156 settled + 3 unsettled; 125 settled rows lack required usable
  probability/price fields, leaving 31. Private raw cache at
  `/tmp/volleyball-t3-paper-20261001.json` is excluded from Git. Only
  aggregate paper statistics were committed. Zero sheet writes.
- **Cannot verify fresh increment:** available post-09-26 sample n=0.
  No sweep started: its fixture enumeration is billable, contradicting T3's
  zero-billable boundary. No running `backfill_odds.py` process found. Spend
  and quota use in this task: zero. Resume extension after Q2, then rerun
  analysis into a new evidence directory. T5 remains queued; independent
  review-only T1 can proceed while Q1/Q2 await rulings.

### 2026-10-01 11:28 EDT — T1 in progress: high-severity grading bug

- **Bug, high, live grading path:** `_find_result` checks orientations
  before ranking by date. A neighboring-day same-orientation fixture wins
  over an exact-date reversed fixture. Synthetic reproduction selects
  contest 1 on Sep 30 instead of contest 2 on Oct 1. Exhaustive reversed
  lookups across 2,287 current results return another contest for 26 rows.
  Evidence: `evidence/t1-20261001/grading_match_risk.json` (IDs listed).
  These are affected lookup scenarios, not 26 proven misgraded owner bets.
- No grader or sheets changed. Q3 below requests a repair task and controlled
  exposure review. Independent T1 checks continue. Mathematical/data/Elo
  replay is running locally under `scripts/audit/core_audit.py`; progress
  log `/tmp/t1-core.log`, output `evidence/t1-20261001/core-1/`. Do not
  start another copy. It reads historical tables and writes only new audit
  evidence; no 2026 player tables are rebuilt.

### 2026-10-01 11:33 EDT — T1 in progress: high-severity team matcher bug

- **Bug, high, live pricing path:** the alias-prefix matcher resolves
  `Utah` to `texas-arlington` (alias `uta`) at confidence 1.0, and
  `USC Upstate` to `southern-california` at confidence 1.0. Such inputs
  can silently price the wrong team; no low-confidence warning is triggered.
- Defined exhaustive corpus: 392 rated teams, 364 represented in local
  schedule names, 1,596 slug/full/short/alias cases = 1,567 correct + 26
  wrong + 3 unmatched. Evidence and all wrong cases:
  `evidence/t1-20261001/matching-1/team_names.csv`; reproduction
  `scripts/audit/matching_audit.py`. This is a finite corpus, not every
  possible book spelling. Q4 below requests a separate repair.
- Read-only checks continue; no matching or pricing code changed. Core
  audit job finished: original parquets/parameters hash-preserved. No
  worker background job remains from that replay.

### 2026-10-01 11:36 EDT — T1 in progress: stale staking context

- **Bug, high, live staking/logging path:** a Best bets card retains its
  old stakes when sidebar settings change. AppTest: bankroll $500→$1,000
  leaves the displayed $31.50 stake unchanged; parsing the same board
  again produces $63.00. Logging reads current sidebar context alongside
  the old card. Evidence: `evidence/t1-20261001/stale_slate.json`, repro
  `scripts/audit/slate_state_audit.py`. No real log writes were made.
- Q5 requests a separate repair. No application code changed in T1.
  All audit jobs have finished; report consolidation continues.

### 2026-10-01 11:41 EDT — T1 implementation complete, awaiting acceptance

- **Report:** `AUDIT_2026-10.md`, commit `6435b08`, covers all ten areas
  with verdicts and reproducible evidence. Earlier immediate flags:
  `6adb0c4` (grading), `b689a91` (matcher), `c6b6766` (stale stakes).
  All T1 changes are new reports/scripts/evidence plus worker sections here;
  no existing application code was modified by T1.
- **Confirmed:** 75 distribution cases agree with independent set-sequence
  enumeration to 1.11e-16; normal integration to 1.77e-9. Eighteen DP cases
  agree with independent rally enumeration to 1.05e-13 and 50,000-set
  simulations (seed 20261001; max |z| 1.78). A new extreme-input check
  finds a low-severity deuce convergence error of 0.0625 percentage points.
  144 settlement cases, 20 Kelly cases, and mock decoder/grade-batch checks
  pass. The stale-stake reproduction confirms a bug, not a passing gate.
- **Risk, high:** only 497/729 sampled raw set scores agree with official
  totals, including 70/204 reconstructed sets. Upstream incompleteness vs
  parser causes needs diagnosis; this is not a population error estimate.
  Eleven invalid 2024 finals remain in protected historical inputs.
- **Claims:** warm Elo accuracy 77.233%, fixed set model 77.940% (n=16,133);
  cached 29-bet +32.293% headline and weight sweep reproduce. Current rebuild
  gives 28 bets +29.518%; report documents unresolved venue provenance.
  Rebuilt ML logloss .541522 / .519108 / .519125 matches the rounded triple.
  Live/backtest venue and p20 each change one qualifying bet in the isolated
  replay. Statistical limitations and exclusions are explicit.
- **Risk, high:** a fake-key HTTP error demonstrates the credential-query
  exposure path to UI error text. No actual secret was exposed. Q6 proposes
  a separate repair; local tracked-file checks do not certify public history.
- **Metered result:** one T1 DraftKings request returned 404 (no fixtures),
  cached raw and decoded empty board. The follow-up ledger sequence failed
  with RuntimeError; a subsequent free account check confirmed quota 4→5
  of 250. `evidence/t1-20261001/live-probe-1/` retains the failure and its
  reconciliation. One billable request used of the authorized maximum four;
  no retry. Nonempty current API compatibility remains unverified.
- All 29 recorded protected source hashes match after completion; no Sheets
  writes, model fits, player-table rebuilds, push or deployment. No audit
  processes remain running. Four pre-existing owner reference files remain
  untracked and untouched. Only the authorized plan monitor continues until
  17:00 EDT; do not start a duplicate.
- **Handoff:** T2, T4 and T1 execution complete awaiting planner acceptance;
  T3 remains an interim report with extension blocked on Q2. T5 remains
  queued until T4 review and Q1 ruling. Proposed repairs Q3–Q6 require
  separate authorization under T1's report-only boundary. No acceptance
  inferred from silence. Some earlier log timestamps were approximate;
  use Git/evidence timestamps for exact chronology.

### 2026-10-01 12:00 EDT — T6/T7/T8/T9 implementation complete, awaiting acceptance

- Reviewed planner ruling `c7fd873`: Q1–Q6 approved, repair order followed;
  D1 replacement semantics remain held. Work is on `codex/review-repairs`.
  All repairs use `WVB_ENABLE_REPAIRS=1` for review and default off. No push.
- T6 `c9c9b71`: date-ranked orientation matching, ties refused. Six tests
  pass; 2,287 reversed lookups give zero wrong contests and 14 ambiguous
  refusals. Readonly OAuth review: 43 real bets + 159 paper rows, zero
  lookup/grade changes, zero unusable rows. Private affected-row list is
  `/tmp/volleyball-t6-grading-exposure-20261001.json` (empty); aggregate
  evidence in `evidence/t6-20261001/`. No sheet writes.
- T7 `4e0c7c0`: exact identities and whole-name aliases, campus/punctuation
  distinctions, ambiguity refusal. All 1,596 corpus cases now correct
  (previously 26 wrong and 3 unmatched); five focused tests pass. Unknown
  names now fail closed instead of returning fuzzy guesses. Evidence:
  `evidence/t7-20261001/`.
- T8 `1ce6412`: complete card input snapshot, invalidation on seven tested
  controls, snapshot logging. Bankroll doubling gives $31.50→$63 after
  reevaluation; stale card is absent before then. Nonempty mocked paper
  write matches snapshot exactly (`evidence/t8-20261001/run-2/`). Initial
  run logged zero rows due to the absence filter and did not validate record
  contents; run-2 deliberately stubs that filter for the logging test.
- T9 `c5fb92c`: sanitized provider status/transport/JSON errors and app
  fallback; five fake-credential regressions pass. No real key printed.
  Planner disclosed a prior chat-only key exposure; rotation remains the
  owner's action, not performed by this worker.
- Remaining authorized work: small T4 UI defects, T5 annotations, and T3
  one-request extension plus final analysis. No worker job is running yet;
  checking process state before the single-instance extension. No acceptance
  inferred and no pricing defaults or replacement semantics changed.

## 9. Open questions (append only)

(none open)

### Planner rulings — 2026-10-01 12:05 EDT (answers to Q1–Q6; owner present in chat)

- **Q1 — approved as recommended.** T5 uses the Player ranks metric
  ("X.X pts/set") plus position rank; a matchup-dependent ML what-if
  display is deferred to the T4 design decision. (Planner's spec example
  used wrong units — worker was right to flag; spec corrected by this
  ruling.)
- **Q2 — approved as recommended.** One billable `/v4/fixtures` request,
  hard cap 1, enforced in code, quota checked before/after via the free
  account endpoint, raw response cached, single-job lock, atomic outputs,
  stop on auth/rate-limit errors. (Quota ruling within free tier; owner
  informed in chat this turn.)
- **Q3 — repair authorized as T6** (as proposed: rank both orientations
  together, prefer exact date, refuse ambiguous ties; two-date/reversed
  regressions). Also deliver the read-only list of real logged rows whose
  grading would change; corrections to the owner's real records are the
  OWNER's decision after seeing that list — do not modify sheet rows.
- **Q4 — repair authorized as T7** (as proposed: exact identity first,
  token-bounded aliases, fail-closed ambiguity). Gate: zero wrong matches
  on the 1,596-case corpus + the named Utah/USC/Miami/LSU regressions.
- **Q5 — repair authorized as T8** (as proposed: pricing-input snapshot
  per card, invalidate/reprice on change, log the snapshot; regressions
  with Sheets mocked).
- **Q6 — repair authorized as T9** (as proposed: status/endpoint-only
  error surfaces; fake-credential regressions). Planner disclosure for the
  exposure review: the real key appeared in a 404 error URL in planner
  session output on 2026-09-26 (chat transcript only — not committed, not
  published). Recommendation to owner: rotate the OddsPapi key as cheap
  insurance; owner's action.
- **Repair order: T6, T7 (money paths first), then T8, T9** — on one or
  more repair branches, planner acceptance before merge. T5 may follow.
  T3 unblocked by Q2. The T4 "remove = redistribute exposure" semantics
  question goes to the owner (see §6 amendment below); the two small T4
  defects (no-edit help text wrong; missing-roster crash in player mode)
  are authorized as part of T8's branch or their own small branch.

### Q1 — 2026-10-01 11:14 EDT — T5 annotation units

T5 requires identity with Player ranks but gives an example in percent/set.
Player ranks actually reports rally points/set (rounded serve contribution
plus rounded receive contribution), not percentage points of set-win
probability or the price effect of removing a player. Murray's ranking
metric and her −3.38pp hybrid ML removal effect are different quantities.
**Recommendation:** label T5's shared metric “points/set” with position rank;
reserve matchup-dependent “ML percentage points” for a separately approved
what-if display. Alternative: change the requested metric to a removal
effect, which would change scope and could not equal the current ranks tab.
Please rule on units when reviewing T4/T5. Only T5 depends on this answer;
T3 and the review-only T1 can proceed.

### Q2 — 2026-10-01 11:22 EDT — T3 fixture enumeration requires one billable request

The requested sweep starts with `/v4/fixtures` (`scripts/backfill_odds.py`,
line 102), which costs one quota request per the provider's current
documentation: https://oddspapi.io/en/docs/requests-and-quota . T3 explicitly
allows **no OddsPapi billable calls**. Historical-odds calls are free, but
the project has no cached enumeration covering the required new fixtures.
**Recommendation:** owner authorizes a hard cap of **one** fixture-list
request covering finished fixtures through 2026-09-30; cache it, verify
the account quota before/after, then use only free history calls. A safe
wrapper should add a single-job lock, raw-response cache, atomic new outputs,
and stop on authorization/rate-limit errors; the existing sweep lacks those
protections. Alternatively provide a suitable cached fixture response for
zero-quota continuation. No request has been made; the existing diagnostic
report is ready to review. This blocks only T3's extension/final conclusion.

### Q3 — 2026-10-01 11:28 EDT — High-severity result matching bug

`bet_log._find_result` can grade against the wrong rematch when the book's
labels are reversed. It returns the closest same-orientation fixture within
one day before considering any reversed fixture, even an exact-date match.
26 of 2,287 actual-result reversed lookups return a different contest;
e.g. UCLA/Long Beach State on Aug 28 returns the Aug 29 rematch.
**Recommendation:** authorize a separate repair to rank both orientations
together, prefer exact date, and refuse ambiguous ties (or use an explicit
contest ID/time). Add the two-date/reversed regression and audit stored log
exposure read-only before proposing any correction to real records. T1's
review-only rule prohibits fixing this in-place; no real rows have been
changed. This question flags the high-severity issue immediately as required
by T1 staging; independent review continues.

### Q4 — 2026-10-01 11:33 EDT — High-severity confident wrong-team matching

`paste_odds.match_team` allows alias prefixes before exact school identity;
`uta` captures Utah/Utah State and `usc` captures USC Upstate at confidence
1.0. These feed both live API and pasted-board pricing. The 1,596-case
corpus contains 26 wrong mappings, all listed in the evidence CSV.
**Recommendation:** authorize a separate repair using exact known team
identity first, token-bounded aliases/campus exceptions, and fail-closed
handling of ambiguous school names. Require zero wrong matches on the
captured corpus plus focused Utah/UTA, USC/USC Upstate, Miami Ohio/Florida,
and LSU/LSU New Orleans regressions. Audit real log exposure read-only;
do not rewrite records or production defaults as part of this review.

### Q5 — 2026-10-01 11:36 EDT — Stale stakes and mismatched logged context

Changing bankroll (and other pricing controls) does not invalidate or
reprice `best_card`; `pricing_context` reads current controls at log time.
The measured $31.50→$63.00 stake requires pressing Parse again despite the
sidebar already showing the new bankroll. **Recommendation:** authorize a
separate repair to capture a complete pricing-input snapshot with each
card, invalidate/reprice when it changes, and log that exact snapshot.
Require bankroll, basis, blend, edge, and venue change regressions with
Sheets mocked. T1's report-only rule prohibits this fix here; no real
records or production behavior were changed.

### Q6 — 2026-10-01 11:41 EDT — Credential-bearing HTTP exceptions reach UI

`oddspapi.fetch_board` calls `raise_for_status` on a request with apiKey in
the URL; the app displays the exception at `streamlit_app.py:802`.
An offline fake-key response confirms the error contains the key value.
No real credential was exposed during this audit. **Recommendation:**
authorize a separate boundary-hardening repair to replace credential-bearing
exceptions with status/endpoint-only messages in app and collector paths;
regression-test with fake credentials that neither UI text nor logs includes
them. Review historical exposure privately before deciding whether rotation
is needed. Do not print real keys or assume exposure occurred. T1 is
report-only, so this audit does not change the exception path.
