# Blend strictness review — October 1, 2026

**Interim recommendation: keep the deployed defaults while resolving data provenance and collecting the fresh increment. This review is blocked on T3's historical extension, not complete.** The existing sample generally penalizes relaxing the blend at the same 2% gate. One diagnostic cell, 40% model weight with a 3% gate, looks better but rests on only two additional winning bets. There are no post-September-26 fixtures in the available backtest, so that finding has no fresh confirmation.

The plan prohibits billable requests in T3. `scripts/backfill_odds.py:102` enumerates fixtures before fetching history; `/v4/fixtures` costs one quota request according to [OddsPapi's quota documentation](https://oddspapi.io/en/docs/requests-and-quota). Historical-odds calls are free. No sweep was started and no quota was spent. The project has no cached fixture enumeration covering the requested extension. Q2 in PLANS.md requests either a cached enumeration or a one-request exception. “New boarded fixtures added” is **not measured**, rather than zero.

## Evidence and a provenance discrepancy

The cached backtest has 294 rows covering 75 fixtures (70 with moneylines), August 28–September 25. Recomputing its own statistics reproduces the planner's 29 bets, 18–11, +9.365 units, **+32.2931% ROI** at weight .30 / gate .02. Its .50 and 1.00 weight results are +3.4846% and −5.6213%.

Running the unchanged backtest script on current inputs, with its output redirected to a new evidence file, still yields 294 rows and 75 fixtures but changes 14 probabilities across four fixtures. The rebuilt .30/.02 result is **28 bets, 17–11, +8.265 units, +29.5179% ROI**, with a bet-bootstrap 90% interval of **−4.85% to +63.63%**. The original files and model parameters are unchanged, verified by SHA-256 before/after.

Every changed cached probability is reproduced by using the opposite home/neutral flag from the current result record. Florida–North Texas is decisive: Florida −2.5 changes from model probability .615579 and blended edge .021477 to .609215 and .019466. The cached winning bet therefore fails the rebuilt 2% gate. The historical result snapshot at the cached backtest's commit already has the same neutral flag as today for this game; the cached artifact's generation provenance is unresolved. This is **not established as drift in its Elo inputs**. `neutral_provenance.json`, `florida_input_drift.json` (shows unchanged inputs), and `backtest_comparison.csv` preserve the evidence.

The following tables use the rebuilt rows. Both views are diagnostic: the earlier sample was already inspected during model-weight selection. No model was fit or production default changed here.

## Disagreement buckets: model probability minus market devig

Flat one-unit stakes, no pushes in this sample. “Pass” means recomputed point-model logit blend at .30 clears a .02 edge against vig-included taken price. It is not necessarily the live conservative-p20 gate.

| Disagreement | Gate result | Bets | W–L | ROI |
|---|---|---:|---:|---:|
| 2–5 pp | Fail | 30 | 15–15 | −22.83% |
| 2–5 pp | Pass | 0 | 0–0 | — |
| 5–8 pp | Fail | 20 | 10–10 | −8.13% |
| 5–8 pp | Pass | 0 | 0–0 | — |
| 8–12 pp | Fail | 21 | 5–16 | −46.25% |
| 8–12 pp | Pass | 0 | 0–0 | — |
| 12+ pp | Fail | 16 | 6–10 | −1.21% |
| 12+ pp | Pass | 28 | 17–11 | +29.52% |

Counts reconcile: 115 bucketed rows + 179 rows with disagreement below 2 pp = 294 priced rows. Failure at a large disagreement can reflect the cost of vig as well as the market blend; raw model disagreement alone is not the edge being staked.

## Weight × gate grid

Seed **20261001**, **10,000** resamples of bets with replacement per cell, percentile 90% interval. Unit profit and all 20 cells are also in `full_grid.csv`.

| Model weight | Gate | Bets | W–L | Profit (u) | ROI | 90% interval |
|---:|---:|---:|---:|---:|---:|---|
| 30% | 1% | 34 | 19–15 | +6.965 | +20.49% | -11.57% to +52.84% |
| 30% | 2% | 28 | 17–11 | +8.265 | +29.52% | -4.85% to +63.63% |
| 30% | 3% | 21 | 13–8 | +6.904 | +32.88% | -7.29% to +74.17% |
| 30% | 4% | 14 | 8–6 | +2.624 | +18.74% | -30.71% to +67.67% |
| 30% | 6% | 7 | 3–4 | -0.317 | -4.53% | -73.81% to +67.14% |
| 35% | 1% | 47 | 23–24 | +1.612 | +3.43% | -23.20% to +30.03% |
| 35% | 2% | 33 | 19–14 | +7.965 | +24.14% | -7.39% to +56.47% |
| 35% | 3% | 27 | 17–10 | +9.265 | +34.31% | -1.41% to +69.56% |
| 35% | 4% | 20 | 12–8 | +5.904 | +29.52% | -13.59% to +72.25% |
| 35% | 6% | 12 | 6–6 | +1.653 | +13.77% | -41.92% to +70.44% |
| 40% | 1% | 51 | 24–27 | +2.812 | +5.51% | -22.69% to +34.86% |
| 40% | 2% | 41 | 20–21 | +1.798 | +4.39% | -24.13% to +33.65% |
| 40% | 3% | 30 | 19–11 | +10.965 | +36.55% | +3.05% to +69.91% |
| 40% | 4% | 27 | 17–10 | +9.265 | +34.31% | -1.41% to +69.56% |
| 40% | 6% | 14 | 8–6 | +2.624 | +18.74% | -30.71% to +67.67% |
| 50% | 1% | 66 | 29–37 | -0.442 | -0.67% | -25.21% to +24.96% |
| 50% | 2% | 52 | 24–28 | +1.812 | +3.48% | -23.97% to +32.26% |
| 50% | 3% | 44 | 22–22 | +2.871 | +6.53% | -21.22% to +34.94% |
| 50% | 4% | 33 | 19–14 | +7.965 | +24.14% | -7.39% to +56.47% |
| 50% | 6% | 23 | 14–9 | +7.254 | +31.54% | -7.47% to +70.71% |

These intervals treat bets as independent even though markets on the same game are correlated. That is the requested bootstrap, not a robust uncertainty model for a portfolio. No multiplicity correction is applied to the 20 inspected cells.

## Marginal bets admitted

Compared with rebuilt .30/.02, at a fixed 2% gate:

| New weight | Added bets | W–L | Marginal profit | Marginal ROI | 90% interval |
|---|---:|---:|---:|---:|---|
| .35 | 5 | 2–3 | −.300u | −6.00% | −100.00% to +88.00% |
| .40 | 13 | 3–10 | −6.467u | −49.75% | −85.90% to −5.39% |
| .50 | 24 | 7–17 | −6.453u | −26.89% | −67.03% to +18.62% |

`full_marginal.csv` covers additions and removals for every grid cell; `full_marginal_bets.csv` names each admitted public closing-line bet. Higher weights are not assumed to select a nested superset in general.

The .40/.03 cell deserves explicit mention rather than being hidden by the fixed-gate summary. It adds **two bets, both winners**, +2.7 units, without removing any baseline bets. Total profit rises from 8.265 to 10.965 units; its nominal total-ROI interval is +3.05% to +69.91%. This passes the numerical part of the planner's proposed decision screen on the diagnostic sample. But a two-winner empirical bootstrap cannot represent unobserved losing bets, the sample has already been used for selection, and there is no fresh increment. It is a candidate for a predeclared forward check, not a supported immediate default change.

## Moneyline logloss

One home-side moneyline per fixture, n=70; lower is better.

| Model weight | Logloss |
|---:|---:|
| 0 (market) | .519108 |
| .30 | .519125 |
| .35 | .519686 |
| .40 | .520408 |
| .50 | .522333 |
| 1 (raw model) | .541522 |

The small differences among low weights do not establish a stable optimum. This sample gives no calibration argument for putting substantially more weight on the model.

## Paper-log cross-check at taken prices

Read the existing paper worksheet with a **read-only Google Sheets OAuth scope**, without calling the application's migration-capable `read_log` wrapper. Raw records are cached privately outside Git; only aggregates enter the report.

159 total rows = 156 settled + 3 unsettled. Of the settled rows, **125 lack valid recorded model/market probabilities or prices needed for this paired-probability comparison**, leaving **31 usable rows**. Missing market probabilities are not reconstructed or silently treated as a successful devig. All 31 fall into the two largest disagreement buckets:

| Disagreement | Recomputed .30/.02 gate | Bets | W–L | Taken-price ROI |
|---|---|---:|---:|---:|
| 8–12 pp | Fail | 6 | 4–2 | +5.59% |
| 8–12 pp | Pass | 0 | 0–0 | — |
| 12+ pp | Fail | 13 | 4–9 | −37.05% |
| 12+ pp | Pass | 12 | 9–3 | +53.52% |

The 2–5 and 5–8 pp buckets contain zero usable paper rows. Counts reconcile: 6 + 13 + 12 = 31. The largest failed disagreements lose in both sources, while the 8–12 pp bucket disagrees (paper +5.59%, closing −46.25%). Samples, time of odds capture, and logging selection differ; these are not paired fixture estimates of line movement. The selected paper log cannot establish how all rejected opportunities performed. Stored point probabilities permit a recomputed point-model gate, not reconstruction of historical p20 decisions.

## Fresh increment and next decision

Post-September-26 rows: **0 available**. Separate grid, marginal, bucket, and logloss CSVs are emitted with n=0 and undefined ROI/intervals; zero profit on an empty set is not evidence of break-even performance. The extension must finish before T3 can pass its acceptance gate or make a final recommendation.

Proposed reopening point: at least **100 new usable, settled bet opportunities from roughly 250 additional boarded fixtures**, with the strategy and comparison cell frozen before evaluation. This is a planning threshold, not a power guarantee: game clustering and variance may require more. A forward comparison should retain all rejected opportunities and assess marginal bets and total profit at taken prices, not merely optimize a closing-line grid.

Reproduce diagnostic work with `./.venv/bin/python scripts/audit/blend_review.py --output evidence/t3-20261001/new-run --paper /tmp/volleyball-t3-paper-20261001.json`. Omit `--paper` if the private cache is unavailable; report that component unverified rather than substituting data. Main evidence is under `evidence/t3-20261001/run-1/`. The backtest stdout names its original output path, but the harness redirects the actual write to `rebuilt_backtest.parquet` inside that evidence directory. Source hashes in `summary.json` verify the originals were preserved.
