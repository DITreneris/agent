# Post-Hardening Decision Benchmark Re-baseline

## Run

- Date: 2026-09-11
- Kind: measurement re-baseline after validator hardening
- Model: `gemma4:e4b`
- Temperature: `0.1`
- Context size: `8192`
- Seeds: `11`, `22`, `33`
- Cases: `8`
- Total runs: `24`
- Focused audit prompt: unchanged (`build_file_audit_prompt`)
- HEAD at run: `b11e75a` plus uncommitted validator-hardening work
- Result file:
  `evaluation_results/decision_grade_benchmark_v2_post_hardening.json`
- Result SHA256:
  `79f6336d578cbfb3fcfe8f47f0f5edf468a27343bb6af5a4d326a2f3df2aa50b`
- Offline replay of v2 texts:
  `evaluation_results/decision_grade_benchmark_v2_post_hardening_replay.json`
- Smoke (seed `11` only):
  `evaluation_results/decision_grade_benchmark_v2_post_hardening_smoke_seed11.json`

The v2 baseline JSON was not overwritten.

## Sequence

1. Offline `--replay-json` of the v2 captured responses against the
   hardened validator and current `expected.json`.
2. WSL Ollama smoke with seed `11` (8 runs, about 108 seconds).
3. Full locked 24-run live re-baseline (about 372 seconds).

## Offline Replay (A)

Replay reconstructed all 24 captured attempts without calling Ollama.

- Structurally valid reconstructed outputs: `24 of 24`.
- `audit_valid` changed: `0`.
- `passed` changed: `0`.
- `retry_used` changed: `0`.
- Rows needing a live retry: `0`.
- High-confidence false positives on the captured texts: `1`.
- Context recall on the captured texts: `0 of 6`.
- Reviewer gate: **FAIL** (same as v2).

The historical `24/24` structural figure still holds on the original
v2 texts. Hardening did not invalidate those outputs.

## Smoke (C)

- Metadata `num_ctx`: `8192`.
- Structurally valid: `8 of 8`.
- Case-level scoring: `5 of 8` passed.
- High-confidence false positive: `1` (case 003, `HARDEN_SMALL`,
  accepted on the first attempt).
- Context cases: both `FIX_NOW` / `BLOCK` / High.

Single-seed majority gates are not comparable to the three-seed lock
because the gate requires majority count `>= 2`. Structural acceptance
did not collapse, so the full 24-run proceeded.

## Live Re-baseline (B)

Overall benchmark gate: **FAIL**.

- Correct majority decisions: `6/8`.
- Correct run-level decisions: `18/24` (`75.0%`).
- Proven defects detected: `3/3` cases and `9/9` runs.
- Safe cases correct by majority: `3/3`.
- Context cases correct by majority: `0/2`.
- Correct `INSPECT_CONTEXT` runs: `0/6`.
- `INSPECT_CONTEXT` recall: `0%`.
- High-confidence false positives: `0`.
- Structurally valid outputs: `24/24` (`100%`).

## Gate Results

| Gate | Result |
|---|---:|
| At least 6/8 correct majority decisions | PASS — 6/8 |
| All 3 proven defects majority CHANGE | PASS — 3/3 |
| At least 2/3 safe cases majority NO_CHANGE | PASS — 3/3 |
| At least 1/2 context cases majority INSPECT_CONTEXT | FAIL — 0/2 |
| Zero high-confidence false positives | PASS — 0 |
| At least 75% structurally valid outputs | PASS — 100% |

## Case Results

| Case | Expected | Majority | Correct runs | Retries | Result |
|---|---|---|---:|---:|---|
| case_001_correct_helper_contract | NO_CHANGE | NO_CHANGE | 3/3 | 0/3 | PASS |
| case_002_real_none_bug | CHANGE | CHANGE | 3/3 | 0/3 | PASS |
| case_003_intentional_none_contract | NO_CHANGE | NO_CHANGE | 3/3 | 3/3 | PASS |
| case_004_empty_average_bug | CHANGE | CHANGE | 3/3 | 0/3 | PASS |
| case_005_partial_transfer_mutation | CHANGE | CHANGE | 3/3 | 0/3 | PASS |
| case_006_idempotent_cleanup | NO_CHANGE | NO_CHANGE | 3/3 | 0/3 | PASS |
| case_007_timeout_requires_caller | INSPECT_CONTEXT | CHANGE | 0/3 | 0/3 | FAIL |
| case_008_profile_requires_schema | INSPECT_CONTEXT | CHANGE | 0/3 | 0/3 | FAIL |

## Focused Diagnosis

Both context-required cases failed identically across all three seeds:

- Recommended action: `FIX_NOW`;
- Decision: `CHANGE`;
- Verdict: `BLOCK`;
- Confidence: `High`;
- Retry used: no;
- Structural validation: valid.

The reviewer still treats a reachable exception as a confirmed defect
when the visible code does not establish the caller, schema, or error
contract.

Case 003 was correct in all three live seeds, but every first attempt
failed calibration and required retry. The repaired outputs were
`NO_CHANGE` / `GO` / High. First-attempt reviewer judgment is still
not stable.

The seed-11 smoke accepted a high-confidence `HARDEN_SMALL` on case
003 without retry. The later full run with the same configured seed
rejected that first attempt and repaired it. That difference is
Ollama runtime noise, not a validator or prompt change.

## Comparison

| Measure | v2 live | A replay of v2 texts | Post-hardening live |
|---|---:|---:|---:|
| Correct majority decisions | 6/8 | 6/8 | 6/8 |
| Correct run-level decisions | 17/24 | 17/24 | 18/24 |
| Proven defect runs correct | 9/9 | 9/9 | 9/9 |
| Safe cases correct by majority | 3/3 | 3/3 | 3/3 |
| Context cases correct by majority | 0/2 | 0/2 | 0/2 |
| Correct INSPECT_CONTEXT runs | 0/6 | 0/6 | 0/6 |
| High-confidence false positives | 1 | 1 | 0 |
| Structurally valid outputs | 24/24 | 24/24 | 24/24 |
| Case 003 correct runs | 2/3 | 2/3 | 3/3 |
| Case 003 retries | 2/3 | 2/3 | 3/3 |

The live HCFP drop and the extra correct case-003 run cannot be
attributed to validator hardening. Replay of the same v2 texts still
has one high-confidence false positive and the original 2/3 case-003
split. Those live deltas are consistent with previously observed
mixed CPU/GPU Ollama nondeterminism and with retry effects.

## Decision

Treat this as a valid failed reviewer re-baseline after hardening.

Do not treat the live `0` high-confidence false-positive count as a
hardening win.

Do not change the focused audit prompt in this measurement.

The next experiment remains one variable only: the evidence boundary
in `build_file_audit_prompt`.

The next experiment still passes only if it preserves all three defect
majorities, keeps at least two safe-case majorities, produces at least
one correct context-case majority, keeps high-confidence false
positives at zero, and preserves at least 75% structural validity.

A real-repository field sample remains blocked until that synthetic
gate passes.
