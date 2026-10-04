# T13 — replacement lineup review

Interim implementation; blocked on Q9's bench-definition ruling before final
acceptance. Review with `WVB_ENABLE_REPLACEMENT_LINEUPS=1`. Default remains off.
No fitted coefficients, fitting code, or hybrid reference construction changed.

Removed initial-lineup players keep their original smoothed playing-time share
(or equal share with weighting unchecked). Position-matched explicit additions
replace those slots first, then other additions in roster order. Otherwise use
the arithmetic mean of the fitted position bench, then overall fitted bench,
then zero. Additional selected players not filling a removed slot keep their
own weights. The existing normalization keeps six shares. The unchanged path
calls the original function with identical rows, order and selections.

The panel identifies every substitute, tier and pool, and includes the legacy
redistribution toggle. Explicit additions override synthetic slots. Current
bench interpretation is fitted roster players outside the initial lineup and
current selection. This is reviewable but needs clarification: absence from the
last lineup does not establish low playing time. Nebraska's Bergen Reilly
(40 starts) and Virginia Adriano (29) enter the overall bench under that rule.
No unapproved numeric cutoff was introduced. Q9 proposes a precise low-start
criterion for the planner to decide before acceptance.

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
roster strengths for every roster team in both weighting modes, both UI pricing
modes, exact legacy-toggle parity, explicit substitution, unrated-bench fallback,
and five displayed label checks. Protected artifacts retain their SHA256 hashes.
Evidence: `evidence/t13-20261004/run-20261004T200816.370126Z-i6y7y_vy/`.

The benchmark directional gate passes, but does not establish that all substitute
estimates are worse than all removed players. No such clamp is applied. Bench
qualification is a modeling definition, not something to silently infer from
these four favorable results. Zero paid requests, real Sheets writes or deploys.
