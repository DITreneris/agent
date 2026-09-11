# Evidence-Boundary Last-Shot Benchmark

## Run

- Date: 2026-09-11
- Kind: last-shot reviewer experiment; one variable only
- Variable: evidence boundary in `build_file_audit_prompt`
- Model: `gemma4:e4b`
- Temperature: `0.1`
- Context size: `8192`
- Seeds: `11`, `22`, `33`
- Cases: `8`
- Total runs: `24`
- Validator, retry, corpus, and seeds: unchanged
- Result file:
  `evaluation_results/decision_grade_benchmark_v2_evidence_boundary.json`
- Result SHA256:
  `25be46ee687a929444ce4e2cd3be06eb821d93ea33e65fbefaac6758ac4b2428`
- Smoke (seed `11` only):
  `evaluation_results/decision_grade_benchmark_v2_evidence_boundary_smoke_seed11.json`

Comparison baseline: post-hardening re-baseline
`evaluation_results/decision_grade_benchmark_v2_post_hardening.json`.

## What Changed

The focused audit prompt now distinguishes:

- a visible contract violation justifying `CHANGE`;
- an observable exception path without that contract, which should
  use `INSPECT_CONTEXT`;
- a proven safe path justifying `NO_CHANGE`.

BLOCK and High confidence were tightened so a reachable raise is not
enough without a visible type, docstring, or named contract.

No case names were added to the prompt.

## Outcome

Overall benchmark gate: **FAIL**.

- Correct majority decisions: `5/8`.
- Correct run-level decisions: `16/24` (`66.7%`).
- Proven defects detected: `3/3` cases and `9/9` runs.
- Safe cases correct by majority: `2/3`.
- Context cases correct by majority: `0/2`.
- Correct `INSPECT_CONTEXT` runs: `0/6`.
- `INSPECT_CONTEXT` recall: `0%`.
- High-confidence false positives: `2`.
- Structurally valid outputs: `24/24` (`100%`).

## Gate Results

| Gate | Result |
|---|---:|
| At least 6/8 correct majority decisions | FAIL — 5/8 |
| All 3 proven defects majority CHANGE | PASS — 3/3 |
| At least 2/3 safe cases majority NO_CHANGE | PASS — 2/3 |
| At least 1/2 context cases majority INSPECT_CONTEXT | FAIL — 0/2 |
| Zero high-confidence false positives | FAIL — 2 |
| At least 75% structurally valid outputs | PASS — 100% |

## Case Results

| Case | Expected | Majority | Correct runs | Retries | Result |
|---|---|---|---:|---:|---|
| case_001_correct_helper_contract | NO_CHANGE | NO_CHANGE | 3/3 | 0/3 | PASS |
| case_002_real_none_bug | CHANGE | CHANGE | 3/3 | 0/3 | PASS |
| case_003_intentional_none_contract | NO_CHANGE | CHANGE | 1/3 | 2/3 | FAIL |
| case_004_empty_average_bug | CHANGE | CHANGE | 3/3 | 0/3 | PASS |
| case_005_partial_transfer_mutation | CHANGE | CHANGE | 3/3 | 0/3 | PASS |
| case_006_idempotent_cleanup | NO_CHANGE | NO_CHANGE | 3/3 | 0/3 | PASS |
| case_007_timeout_requires_caller | INSPECT_CONTEXT | CHANGE | 0/3 | 0/3 | FAIL |
| case_008_profile_requires_schema | INSPECT_CONTEXT | CHANGE | 0/3 | 0/3 | FAIL |

## Focused Diagnosis

Context cases 007 and 008 still received `FIX_NOW` or equivalent
`CHANGE`, `BLOCK`, and High in every seed. `INSPECT_CONTEXT` was never
used. The evidence-boundary wording did not move the reviewer off a
reachable exception as a confirmed defect.

Case 003 got worse versus the post-hardening re-baseline: majority
flipped to `CHANGE`, with two high-confidence false positives. Defect
recall stayed `9/9`.

The seed-11 smoke was structurally `8/8`, with `0` `INSPECT_CONTEXT`
runs and one case-003 HCFP. Single-seed majority gates are not
comparable to the three-seed lock.

## Comparison

| Measure | v2 live | Post-hardening live | Evidence-boundary live |
|---|---:|---:|---:|
| Correct majority decisions | 6/8 | 6/8 | 5/8 |
| Correct run-level decisions | 17/24 | 18/24 | 16/24 |
| Proven defect runs correct | 9/9 | 9/9 | 9/9 |
| Safe cases correct by majority | 3/3 | 3/3 | 2/3 |
| Context cases correct by majority | 0/2 | 0/2 | 0/2 |
| Correct INSPECT_CONTEXT runs | 0/6 | 0/6 | 0/6 |
| High-confidence false positives | 1 | 0 | 2 |
| Structurally valid outputs | 24/24 | 24/24 | 24/24 |
| Case 003 correct runs | 2/3 | 3/3 | 1/3 |

The last-shot did not improve context recall. It weakened case 003
and the majority gate. Live HCFP counts remain noisy across Ollama
runs; the durable finding is still `0/6` `INSPECT_CONTEXT`.

## Decision

The locked one-variable experiment is complete and failed.

Close the reviewer program. Keep the repository, validator,
`--replay-json`, eight-case lock, and CLI as a negative result and
measurement tool.

Do not run a field sample. Do not productize. Do not start another
prompt, validator, or model experiment unless a new written
hypothesis exists.
