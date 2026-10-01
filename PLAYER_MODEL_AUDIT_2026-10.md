# Player and hybrid pricing audit — October 1, 2026

**Verdict: the controls reach the model, and star removals do move prices. The main confusion is a design mismatch: the default selected lineup differs from the hybrid reference, and removing a player reallocates her playing time to everyone still selected. Two reproducible defects also need repair: inaccurate no-edit guidance and a crash for teams without roster data. No pricing behavior was changed.**

| Area | Verdict | Severity and measured size |
|---|---|---|
| Lineup defaults | Confirmed design; risk | Medium. Last-match starters, not the season rotation; 327 of 331 flagged core absences already deselected; 2 still selected; 2 fail the exact name join. |
| Reference lineup | Confirmed implementation; bug in UI promise | Medium. Untouched Nebraska–Kansas hybrid 95.97%, Elo 93.37%, a 2.60 percentage-point difference. Selecting the season reference restores exact equality across all 16 displayed market rows, including p20. |
| Delta computation | Confirmed arithmetic; risk in interpretation | High design risk if interpreted as causal injury impact. Removing two positive-coefficient starters **raises** hybrid ML by 1.02 and 4.59 points because their weight is redistributed. |
| UI → pricing | Confirmed for four removals × two models; bug for missing rosters | Medium. All eight UI cases equal expected prices to the displayed four decimals. 27 rated teams have no roster rows; Spring Hill–Kansas crashes in player mode. |
| Magnitude sanity | Confirmed under this fitted model; predictive accuracy cannot verify here | Top-five removals lower pure RAPM ML by 5.30–23.60 points vs Kansas. There is no general “barely moves” defect in this sample. Estimates are conditional and are not validated causal player values. |

**Recommendation:** first correct the no-edit wording and missing-roster handling; then adopt proposal 1 below to make already-applied adjustments visible. Decide separately whether removal should redistribute exposure or model an explicit replacement. Do not silently change the pricing model while adding T5 labels.

## Reproduced behavior

All comparisons hold Kansas as the away opponent, use Home court, current committed ratings, playtime weighting, and the default last-match lineup. A removal deselects the named home-team player and leaves all other choices fixed. These are model predictions, not actual match outcomes.

| Player (team) | Pure RAPM, with → without | Change (pp) | Hybrid, with → without | Change (pp) |
|---|---:|---:|---:|---:|
| Harper Murray (Nebraska) | 90.1057% → 83.5976% | −6.5081 | 95.9723% → 92.5890% | −3.3833 |
| Olivia Babcock (Pittsburgh) | 73.2133% → 49.6167% | −23.5966 | 79.6445% → 57.5465% | −22.0980 |
| Teraya Sigler (Nebraska) | 90.1057% → 92.2957% | +2.1901 | 95.9723% → 96.9962% | +1.0239 |
| Ayanna Watson (Pittsburgh) | 73.2133% → 78.6654% | +5.4521 | 79.6445% → 84.2320% | +4.5875 |

Murray's current result is comparable to the planner's September benchmark of 90.9%→83.6% pure and 96.6%→92.7% hybrid; the direction and order of magnitude survive. Babcock's effect is larger. This does not justify increasing coefficient magnitudes to make the lever feel stronger.

Evidence: `evidence/t4-20261001/run-1/removals.csv` and `ui_wiring.csv`. The expected-price calculation independently constructs lineup changes and invokes the existing model; AppTest operates the actual multiselects and reads the actual board. Agreement validates UI wiring and arithmetic, not the underlying statistical model.

## What “remove” currently means

`streamlit_app.py:361` sorts roster rows by current sets and receive coefficient. The default is every player marked `in_last_lineup`; only when none are marked does it fall back to the first six. All roster names remain selectable, so an already-absent player can be re-added. `scripts/fit_rapm.py:167` constructs the current participation fields from canonicalized starter tables; its last-lineup flags come from set 1 of the latest game represented in those tables.

`vbstats/rapm_price.py:80` gives selected player i weight `6 × (sets_i + 1) / sum_selected(sets + 1)`. Weights total six even when only five people are selected. Thus deselecting a player is an exposure redistribution, not substituting an average reserve or subtracting a fixed individual impact. Murray has weight 1.1878 in Nebraska's default selection: these are exposure weights, not literal people on court.

For coefficient c (serve or receive), let C be the selected lineup's weighted coefficient sum, u the removed player's sets+1, and U the selected total. The exact change on removal is:

`C_after − C_before = 6u / (U − u) × (C_before / 6 − c_removed)`.

This algebra agrees with `lineup_strength` to numerical precision. A player below the selected lineup's weighted mean produces a positive change on removal, even if her absolute coefficient is positive. Sigler and Watson demonstrate this; it is a design consequence, not broken widget state.

## Hybrid reference and the failed no-edit claim

`streamlit_app.py:452` defines the reference as **every roster player**, weighted by season sets+1. The selected lineup is usually only the last-match starters. `streamlit_app.py:459` subtracts the reference lineup's RAPM-derived 25-point set logit from the selected lineup's logit, then adds that delta to the Elo set logit. Toss-up mode reverses the delta in the reversed orientation.

The identity test is **false for untouched UI defaults**: Nebraska–Kansas Elo .9337, default hybrid .9597. The UI help at `streamlit_app.py:353` says untouched lineups price exactly like Elo, which contradicts this behavior. With both teams explicitly set to their full roster and playtime weighting enabled, the entire board equals Elo exactly. The math is consistent with its reference, while the default selection and wording describe different baselines. Disabling playtime weighting also prevents equality with the weighted reference even when every player is selected.

Core absence join: 331 flagged absent rows = 327 matched and deselected + 2 matched but still selected + 2 unmatched. The still-selected names are Ava Grevengoed (Northern Illinois) and Antonie Kelnárová (st-marys-ca). The unmatched names are the mojibake spellings of Dalia Vîrlan (Oregon) and Geovanna Gonçalves Rocha (Hofstra), preserved in `absent_join.csv`. This audit establishes the disagreement, not which feed is correct. An absent flag is not proof of injury, and set-1 starters are not proof of participation across the full match.

## Expected versus observed magnitude

Current metadata: alpha 1000; annual recency factor .75. Ridge shrinkage is already reflected in the coefficients. Alpha alone cannot be translated into a percentage haircut without the weighted design matrix and its eigenstructure. The Player ranks value is **expected rally points per set**, approximately `20.4 × (serve + receive)`, not percentage points of set-win probability and not a marginal absence effect.

The top five by current serve+receive among players with at least one current set are below. All use the same Kansas comparison and the exact redistribution formula followed by the production DP and match integration. “Set change” is the raw 25-point DP probability, before match-level latent uncertainty.

| Player | Set win with → without | Expected pure ML drop (pp) | Expected hybrid drop (pp) |
|---|---:|---:|---:|
| Olivia Babcock | 69.1823% → 49.6870% | 23.5966 | 22.0980 |
| Harper Murray | 84.4692% → 78.2689% | 6.5081 | 3.3833 |
| Caroline Kerr | 55.4869% → 37.1558% | 22.3569 | 22.8414 |
| Bergen Reilly | 84.4692% → 79.3745% | 5.3035 | 2.7144 |
| Brooklyn DeLeye | 72.0580% → 60.6340% | 13.5963 | 12.3013 |

Expected vs observed UI removal drops for the four required checks:

| Player | Expected pure / hybrid drop (pp, rounded board) | Observed UI pure / hybrid drop (pp) |
|---|---:|---:|
| Murray | 6.51 / 3.38 | 6.51 / 3.38 |
| Babcock | 23.59 / 22.09 | 23.59 / 22.09 |
| Sigler | −2.19 / −1.03 | −2.19 / −1.03 |
| Watson | −5.46 / −4.59 | −5.46 / −4.59 |

Rounding the endpoints before subtracting explains hundredth-point differences from the unrounded table. Strong-favorite probabilities compress movement near 100%; a similar logit change has a larger percentage-point effect near 50%. Opponent, venue, remaining players, and current selection all matter. Babcock and Murray are the top two in the current ranking, so this directly tests high-impact players rather than arbitrary small coefficients.

## Canonicalization hypothesis

Read-only snapshots immediately before and at `6f92059` do not support a collapse in star effects. Murray's pure removal drop is 7.2207 pp before, 6.8900 pp after, and 6.5081 pp today; hybrid drops are 3.7958, 3.7255, and 3.3833 pp. Babcock's pure drop increases 22.1420→22.9985 pp at the merge. Murray and Babcock retain their sets counts and selected flags across that commit. Sigler is not selected in either snapshot; she is selected today, reflecting later participation updates.

These are observed snapshots, not an isolated coefficient refit: the merge also changes fitted coefficients. They refute a broad “canonicalization disabled the lever” hypothesis for these players, while not excluding errors affecting other athletes. No local 2026 player tables were rebuilt. Historical results are in `canonicalization_comparison.csv`.

## Additional reproducible defect

For 27 rated teams, there is no RAPM roster. The UI says no roster exists and returns `(None, [])` at `streamlit_app.py:367`, then calls `lineup_strength(None, ...)`, whose iteration at `vbstats/rapm_price.py:89` raises `TypeError`. Spring Hill–Kansas in Player mode reproduces this in AppTest (`evidence/t4-20261001/missing_roster_ui.json`). It is pre-existing logic preserved by the T2 refactor and now easier to encounter with cross-division schedule games. This is a medium-severity failure to price; it does not produce a misleading stake because execution stops. Repair proposal: disable unavailable player/hybrid modes with a clear message; do not silently invent a roster.

## Design proposals for owner selection

1. **Preserve pricing, expose the existing adjustment.** Label the two baselines “season reference” and “selected expected lineup”; explicitly label absent players “already excluded from selection” only after checking the actual selection. Show Elo-only, current hybrid, and each absent player's re-add what-if. Keep all names re-addable. Replace the false no-edit wording. Price implications: none; what-if values vary by opponent and lineup and must be recomputed with the same pricing function.
2. **Use explicit replacement scenarios.** Ask which player takes the missing player's exposure, or allow an explicitly labeled average replacement. Preserve the missing player's exposure slot instead of redistributing it across every selected player. Show current redistribution separately for comparison. Price implications: can materially change both signs and magnitudes; requires owner approval, new validation, and a defined reference lineup. This is a model change, not an annotation fix.
3. **Make pure Elo the initial hybrid baseline.** Start from the full season-weighted reference and explicitly apply visible absence adjustments, each toggle recording whether it is enabled. The untouched reference then equals Elo, while an automatically applied absence still changes the displayed price. Price implications: differs from last-set-starting-lineup defaults; distinguish unselected reserves from verified absences and avoid double-counting adjustments already partly absorbed by Elo.

For T5, retain the Player ranks units and rounding exactly (rally points/set). A label such as “1.42 points/set, #1 of 3 OH” conveys a ranking metric. A removal effect such as “−3.38 percentage points match ML” is a separate, matchup-dependent what-if. The plan's example “−1.8%/set” mixes these quantities and needs a ruling before implementation.

## Reproduction and limits

Run `./.venv/bin/python scripts/audit/player_model_audit.py --output evidence/t4-20261001/new-run` with a new output directory. The script reads committed/current artifacts, checks expected prices against the real AppTest widgets, and blocks HTTP, Sheets writes, grading, and paid injury calls using the T2 validation harness. No production file was modified by T4. Evidence was produced on the branch containing `82f5ae1`; line references above refer to that T2 version.

This is a behavior/design audit. It does not validate causal injury effects, player-coefficient uncertainty, all historical name merges, or out-of-sample match prediction. Those remain T1 questions. Pure RAPM's p20 equals its point estimate because it has no posterior draws; hybrid's parameter draws do not incorporate RAPM lineup-estimation uncertainty. These are material limits when interpreting confidence.
