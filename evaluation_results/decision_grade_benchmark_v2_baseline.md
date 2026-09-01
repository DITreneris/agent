# Contract-Grounded Decision Benchmark v2 Baseline

## Run

- Date: 2026-09-01
- Model: `gemma4:e4b`
- Temperature: `0.1`
- Context size: `8192`
- Seeds: `11`, `22`, `33`
- Cases: `8`
- Total runs: `24`
- Model-run commit: `cb08a96`
- Result file:
  `evaluation_results/decision_grade_benchmark_v2_baseline.json`
- Result SHA256:
  `2de3bb230892692184711d5582c508bb9a39518aa33f0e6c793e005f72294508`

## What Changed

Benchmark v2 changed the measurement contract without changing reviewer
behavior:

- added a dedicated context-decision gate;
- required at least one of two context cases to receive
  `INSPECT_CONTEXT` by majority;
- made the intended behavior of the three actionable defect fixtures
  explicit in the visible target code;
- added regression coverage preventing a `6/8` result with zero
  context recall from passing.

The audit prompt, validator, retry logic, model, context size, output
contract, and seeds were not changed.

## Outcome

Overall benchmark gate: **FAIL**.

- Correct majority decisions: `6/8`.
- Correct run-level decisions: `17/24` (`70.8%`).
- Proven defects detected: `3/3` cases and `9/9` runs.
- Safe cases correct by majority: `3/3`.
- Context cases correct by majority: `0/2`.
- Correct `INSPECT_CONTEXT` runs: `0/6`.
- `INSPECT_CONTEXT` recall: `0%`.
- High-confidence false positives: `1`.
- Structurally valid outputs: `24/24` (`100%`).

## Gate Results

| Gate | Result |
|---|---:|
| At least 6/8 correct majority decisions | PASS — 6/8 |
| All 3 proven defects majority CHANGE | PASS — 3/3 |
| At least 2/3 safe cases majority NO_CHANGE | PASS — 3/3 |
| At least 1/2 context cases majority INSPECT_CONTEXT | FAIL — 0/2 |
| Zero high-confidence false positives | FAIL — 1 |
| At least 75% structurally valid outputs | PASS — 100% |

## Case Results

| Case | Expected | Majority | Correct runs | Result |
|---|---|---|---:|---|
| case_001_correct_helper_contract | NO_CHANGE | NO_CHANGE | 3/3 | PASS |
| case_002_real_none_bug | CHANGE | CHANGE | 3/3 | PASS |
| case_003_intentional_none_contract | NO_CHANGE | NO_CHANGE | 2/3 | PASS |
| case_004_empty_average_bug | CHANGE | CHANGE | 3/3 | PASS |
| case_005_partial_transfer_mutation | CHANGE | CHANGE | 3/3 | PASS |
| case_006_idempotent_cleanup | NO_CHANGE | NO_CHANGE | 3/3 | PASS |
| case_007_timeout_requires_caller | INSPECT_CONTEXT | CHANGE | 0/3 | FAIL |
| case_008_profile_requires_schema | INSPECT_CONTEXT | CHANGE | 0/3 | FAIL |

## Focused Diagnosis

Both context-required cases failed identically across all three seeds:

- Recommended action: `FIX_NOW`;
- Decision: `CHANGE`;
- Verdict: `BLOCK`;
- Confidence: `High`;
- Retry used: no;
- Structural validation: valid.

The model treats a reachable exception as a confirmed defect even when the
visible code does not establish whether the caller, schema, or error contract
permits that behavior.

Case 003 remained unstable:

- seed 11 returned `HARDEN_SMALL`, `GO_WITH_NOTES`, and `High`;
- seeds 22 and 33 reached `NO_CHANGE` only after structural retry;
- both first attempts contained calibration contradictions.

The repaired majority is correct, but the first-attempt reviewer judgment is
not stable.

## Comparison With v1

| Measure | v1 | v2 |
|---|---:|---:|
| Correct majority decisions | 5/8 | 6/8 |
| Correct run-level decisions | 16/24 | 17/24 |
| Proven defect runs correct | 9/9 | 9/9 |
| Safe cases correct by majority | 2/3 | 3/3 |
| Context cases correct by majority | 0/2 | 0/2 |
| Correct INSPECT_CONTEXT runs | 0/6 | 0/6 |
| High-confidence false positives | 2 | 1 |
| Structurally valid outputs | 24/24 | 24/24 |

The apparent improvement on case 003 cannot be attributed to the
contract-grounded fixture changes because case 003 was not changed. It is
consistent with the previously observed nondeterminism of the local Ollama
runtime and with retry effects.

## Decision

Keep benchmark v2 and its context-decision gate.

Do not treat the `6/8` majority score as a reviewer pass. The new gate
correctly prevents a green result while context recall remains zero.

Do not change the validator, retry logic, model, seeds, or context size for
the next experiment.

## Next Experiment

Change one variable only: the evidence boundary in the focused audit prompt.

The rule should distinguish between:

- an observable exception path;
- a visible contract violation justifying `CHANGE`;
- missing caller, schema, type, or error-contract evidence requiring
  `INSPECT_CONTEXT`.

The next experiment passes only if it preserves all three defect majorities,
keeps at least two safe-case majorities, produces at least one correct
context-case majority, eliminates high-confidence false positives, and
preserves at least 75% structural validity.
