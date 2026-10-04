# T13 — replacement lineup review

Implementation complete, awaiting planner acceptance. Q9 approved the precise
bench criterion on October 4; implemented and revalidated below. Review with
`WVB_ENABLE_REPLACEMENT_LINEUPS=1`. Default remains off.
No fitted coefficients, fitting code, or hybrid reference construction changed.

Removed initial-lineup players keep their original smoothed playing-time share
(or equal share with weighting unchecked). Position-matched explicit additions
replace those slots first, then other additions in roster order. Otherwise use
the arithmetic mean of the fitted position bench, then overall fitted bench,
then zero. Additional selected players not filling a removed slot keep their
own weights. The existing normalization keeps six shares. The unchanged path
calls the original function with identical rows, order and selections.

The panel identifies every substitute, tier and pool, and includes the legacy
redistribution toggle. Explicit additions override synthetic slots. Per Q9,
eligible bench players have fitted coefficients, are outside the initial and
current selected lineups, and have starts strictly below half the team's maximum.
Removed players are excluded. The boundary is strict; exactly-half players do
not qualify. Nebraska's Reilly (40 starts) and Adriano (29) are now excluded.
No-edit behavior, including already-absent players in the initial lineup,
remains unchanged. Explicit added replacements may override the synthetic pool.

Same-setting benchmarks vs Kansas, home court, playtime weighted, current
October 4 snapshots; values are home match-win probabilities. Both old and new
use the identical snapshot (earlier T4 numbers used older data).

| Removed | Player before | Redistribution | Replacement | Hybrid before | Redistribution | Replacement |
|---|---:|---:|---:|---:|---:|---:|
| Murray | .881897 | .771336 | .622239 | .951979 | .891003 | .788312 |
| Babcock | .765506 | .518869 | .481156 | .822149 | .594147 | .556218 |
| Sigler | .881897 | .898772 | .779731 | .951979 | .960097 | .896190 |
| Watson | .765506 | .814679 | .743631 | .822149 | .862909 | .803412 |

`PYTHONPATH=. .venv/bin/python scripts/validation/test_replacement_lineups.py`
passes independent slot-weight arithmetic, exact untouched selection and full
roster strengths for all 365 roster teams in both weighting modes, both UI pricing
modes, exact legacy-toggle parity, explicit substitution, unrated-bench fallback,
and five displayed label checks. Protected artifacts retain their SHA256 hashes.
Evidence: `evidence/t13-20261004/run-20261004T201407.708539Z-eg98tbg0/`.

The benchmark directional gate passes, but does not establish that all substitute
estimates are worse than all removed players. No such clamp is applied. Bench
qualification follows the recorded planner ruling; no further modeling cutoff
was inferred from these benchmark results. Zero paid requests, real Sheets
writes or deploys. The four same-position pools are unchanged by Q9; the
fifth (Ryan Hunter, overall bench) drops to +0.148172 points/set and excludes
the two absent regulars. All five displayed labels match their computed values.
