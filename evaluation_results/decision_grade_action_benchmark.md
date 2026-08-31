# Decision-Grade Action Benchmark Baseline

## Run

- Date: 2026-08-31
- Model: gemma4:e4b
- Temperature: 0.1
- Context size: 8192
- Seeds: 11, 22, 33
- Cases: 8
- Total runs: 24
- Runtime: 5m 12s
- Model-run commit: fad2d98

The context-metric names were clarified after the model run. Aggregate
metrics were recomputed from the stored 24 case results without calling the
model again.

## Outcome

Overall benchmark gate: FAIL.

- Correct majority decisions: 5/8; required 6/8.
- Correct run-level decisions: 16/24 (66.7%).
- Proven defects detected: 3/3 cases and 9/9 runs.
- Safe cases correct by majority: 2/3.
- High-confidence false positives: 2.
- Structurally valid outputs: 24/24 (100%).
- Context-required runs: 6.
- Actual INSPECT_CONTEXT decisions: 0.
- INSPECT_CONTEXT recall: 0%.

## Gate Results

| Gate | Result |
|---|---:|
| At least 6/8 correct majority decisions | FAIL — 5/8 |
| All 3 proven defects majority CHANGE | PASS — 3/3 |
| At least 2/3 safe cases majority NO_CHANGE | PASS — 2/3 |
| Zero high-confidence false positives | FAIL — 2 |
| At least 75% structurally valid outputs | PASS — 100% |

## Case Results

| Case | Expected | Majority | Runs | Result |
|---|---|---|---:|---|
| case_001_correct_helper_contract | NO_CHANGE | NO_CHANGE | 3/3 | PASS |
| case_002_real_none_bug | CHANGE | CHANGE | 3/3 | PASS |
| case_003_intentional_none_contract | NO_CHANGE | CHANGE | 1/3 | FAIL |
| case_004_empty_average_bug | CHANGE | CHANGE | 3/3 | PASS |
| case_005_partial_transfer_mutation | CHANGE | CHANGE | 3/3 | PASS |
| case_006_idempotent_cleanup | NO_CHANGE | NO_CHANGE | 3/3 | PASS |
| case_007_timeout_requires_caller | INSPECT_CONTEXT | CHANGE | 0/3 | FAIL |
| case_008_profile_requires_schema | INSPECT_CONTEXT | CHANGE | 0/3 | FAIL |

## Diagnosis

The model reliably detects visible failure paths, but treats reachable
exceptions as confirmed defects even when the visible code does not establish
the caller, schema, or error-handling contract.

Both context-required cases were classified as REAL_BUG with FIX_NOW and High
confidence in every seed. The model did not use INSPECT_CONTEXT once.

Case 003 also exposed decision instability. All three initial responses needed
structural retry. The repaired decisions ranged from NO_CHANGE to HARDEN_SMALL
to FIX_NOW, producing two high-confidence false positives.

The limiting factor is judgment and confidence calibration, not structural
validation or context-window capacity.

## Next Experiment

Change one variable only: add an explicit evidence rule to the audit prompt.

A CHANGE decision requires visible evidence that the code violates an
established contract, caller expectation, schema, type, or test. A reachable
exception alone is not sufficient. When the decision depends on an unseen
caller, schema, or error-handling contract, use NEEDS_CONTEXT,
INSPECT_CONTEXT, and Medium or Low confidence.

Keep the model, temperature, context size, corpus, validator, retry logic, and
seeds unchanged. Re-run the same 24-case matrix and compare against this
baseline.
