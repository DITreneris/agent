# Decision-Grade Audit Benchmark

## Purpose

Measure whether the audit agent chooses the correct practical decision, not
merely whether its output passes structural validation.

## Decision Classes

- CHANGE: visible evidence justifies a code or test change.
- NO_CHANGE: visible code is correct or intentionally designed.
- INSPECT_CONTEXT: a specific missing caller, schema, type, helper, or test is
  required before a responsible decision can be made.

## Corpus

The benchmark contains eight cases:

- 3 proven actionable defects;
- 3 correct or intentionally safe targets;
- 2 targets that genuinely require additional context.

## Locked Configuration

- Model: gemma4:e4b
- Temperature: 0.1
- Context size: 8192
- Seeds: 11, 22, 33
- Validator, retry logic, and seven-section output contract remain frozen
- The focused audit prompt last-shot (evidence boundary) is complete and failed
- The reviewer program is closed; this corpus remains a measurement lock

## Quality Gate

The reviewer passes when:

- at least 6 of 8 cases have the correct majority decision;
- all 3 proven defects receive CHANGE in at least 2 of 3 runs;
- at least 2 of 3 safe cases receive NO_CHANGE by majority;
- at least 1 of 2 context-required cases receives INSPECT_CONTEXT
  in at least 2 of 3 runs;
- no safe case produces a high-confidence false positive;
- at least 75% of outputs pass structural validation.

A benchmark cannot pass with zero INSPECT_CONTEXT recall.

A failed reviewer result does not invalidate the benchmark itself.
