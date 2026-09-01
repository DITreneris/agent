# Tomas Critique Agent

Local CLI-first experiment for testing whether structured output validation,
focused code context, controlled retries, and human evaluation can reduce
unsupported findings from a local LLM.

This is an internal development experiment, not a product and not an
authoritative code-review system.

> **Experimental status:** the implementation passes its recorded local test
> suite, but audit judgment is not yet reliable enough for autonomous or
> authoritative code review.

## Current State

| Measure | Current evidence |
|---|---|
| Development state | Unreleased work after `v1.13.3` |
| Latest recorded local tests | `172 passed, 1 external dependency warning` |
| Decision benchmark v2 | 8 cases × 3 seeds; 24 runs |
| Correct majority decisions | `6 of 8`; overall gate failed |
| Structural validity | `24 of 24` |
| Proven defects | `3 of 3` cases; `9 of 9` runs received CHANGE |
| Safe targets | `3 of 3` correct by majority |
| Context-required targets | `0 of 2` by majority; `0 of 6` runs used INSPECT_CONTEXT |
| High-confidence false positives | `1` |
| Historical real-repository pilot | `0 of 5` audits rated useful or partially useful |
| Consecutive field sample at `4096` | `0 of 8` useful or partially useful; `6 of 8` structurally rejected |
| Context-window A/B | `4096`: `0 of 9` accepted; `8192`: `8 of 9` accepted |
| Field rerun at `8192` | `6 of 8` accepted; `1 of 8` partially useful; `0 of 8` useful |
| Current development target | Improve the evidence boundary without weakening defect recall |

The contract-grounded decision benchmark v2 produced structurally valid
outputs in all 24 runs and correct majority decisions in six of eight cases.
The benchmark still failed because neither context-required target received
`INSPECT_CONTEXT`, and one safe run produced a high-confidence false positive.

The remaining bottleneck is reviewer judgment: the model treats a reachable
exception as a confirmed defect when the visible code does not establish the
relevant caller, schema, type, or error contract.

The first consecutive eight-audit field sample at the default `4096`
context produced six structurally rejected outputs and no useful or partially
useful audits. Offline replay found zero validator drift and zero
fixture-integrity failures.

A controlled field A/B then showed that `8192` context materially improves
structural reliability: acceptance increased from `0 of 9` to `8 of 9` across
the same three cases and seeds. A consecutive eight-case rerun accepted six
outputs, including four on the first attempt.

Human review still found zero useful outputs, one partially useful output,
three low-value outputs, and four false positives. The larger context resolved
most structural failures but did not make reviewer judgment reliable.

The historical production-repository pilot has not been rerun. The current
eight-case field sample used this repository's development code.

## What We Are Testing

The project tests whether a small local audit system can:

1. inspect a focused code range, function, or direct class method;
2. include directly called top-level helpers from the same Python file;
3. request a strict seven-section audit from a local model;
4. reject structurally invalid or internally contradictory responses;
5. retry once with a compact standalone repair prompt;
6. preserve both attempts and validation errors;
7. compare model output against fixed cases and human review.

The core research problem is not output formatting. It is reviewer judgment:
distinguishing a real defect from correct or intentional code.

## Run

Start the main CLI:

```bash
python chat_agent.py
```

Run the local test suite:

```bash
python -m pytest
```

The default audit model is `gemma4:e4b` through local Ollama.

## Focused Audit Commands

```text
/audit_lines <path> <start> <end>
/audit_function <path> <function_name>
/audit_method <path> <ClassName.method_name>
```

Audit evidence and evaluation:

```text
/audit_history [limit]
/audit_stats
/evaluation_stats
/rate_audit <id> <label> [outcome] [| note]
/export_audit_case <id>
```

Focused audits preserve selected code, supplied context, prompt hashes, model
configuration, and both model attempts. `/export_audit_case <id>` writes a
schema-versioned standalone JSON fixture under `audit_exports/`.

The export directory is gitignored because fixtures may contain private code.
Offline replay revalidates captured responses; it does not rerun Ollama.

Batch replay:

```bash
python audit_case.py replay audit_exports/
```

Fixture schema v2 preserves human review together with technical evidence.
Schema v1 fixtures remain replayable and are treated as `NOT_REVIEWED`.
Batch replay returns a non-zero exit code for validator drift, integrity
failures, or an invalid fixture path.

Project inspection:

```text
/project
/project_summary
/project_files
/read_file <path>
/context
/inspect <path>
```

Memory:

```text
/memory
/remember <fact>
/update_memory <id> | <new content>
/delete_memory <id>
/forget <text>
/clear_memory
```

Legacy command:

```text
/audit_file <path>
```

`/audit_file` remains available but is unreliable for larger or more complex
files. Prefer a focused line, function, or method audit.

## Fixed Benchmark

Run the current eight-case decision benchmark with three configured seeds:

```bash
python evaluation_runner.py \
  --model gemma4:e4b \
  --temperature 0.1 \
  --num-ctx 8192 \
  --seeds 11,22,33 \
  --output /tmp/decision-grade-benchmark.json
```

### Contract-Grounded v2 Baseline

| Gate | Result |
|---|---:|
| At least 6/8 correct majority decisions | PASS — `6/8` |
| All 3 proven defects majority CHANGE | PASS — `3/3` |
| At least 2/3 safe cases majority NO_CHANGE | PASS — `3/3` |
| At least 1/2 context cases majority INSPECT_CONTEXT | FAIL — `0/2` |
| Zero high-confidence false positives | FAIL — `1` |
| At least 75% structurally valid outputs | PASS — `100%` |

The overall benchmark gate failed. A `6/8` majority score is not sufficient
when context recall remains zero.

Case 003 passed by majority, but only two of three runs were correct and both
correct runs required structural retry. Cases 007 and 008 received
`FIX_NOW`, `BLOCK`, and High confidence in every seed instead of requesting
caller or schema context.

Configured seeds did not produce identical first responses in the mixed
CPU/GPU Ollama runtime. Seed transmission was verified, but deterministic model
output was not established.

## Current Boundaries

- Manual line-range audits are limited to 200 lines.
- Function audits support top-level Python functions.
- Method audits support direct class methods.
- Same-file context includes directly called top-level helpers.
- Transitive dependencies are not included.
- Cross-file callers and helper implementations are not automatically resolved.
- Nested and inherited methods are not resolved.
- Prompt construction remains mostly string-based.
- The validator catches known structural and calibration contradictions.
- Structural validity does not guarantee useful engineering judgment.
- Offline replay checks validator behavior against captured attempts; it does
  not reproduce nondeterministic model generation.
- A local model can restate speculative findings in wording not covered by
  validator rules.

## Current Decisions

Keep:

- the multi-seed benchmark CLI;
- configurable context size and Ollama attempt diagnostics;
- per-case stability summaries;
- raw response and retry diagnostics;
- the compact standalone repair prompt;
- one retry before rejection;
- human evaluation separate from model validation.

Reject:

- the phrase-based state-distinction validator;
- additional synonym markers;
- case-specific prompt rules;
- treating structural acceptance as proof of real-repository usefulness;
- an immediate typed-output renderer before judgment improves.

Next validation gate:

1. keep the contract-grounded eight-case corpus, `gemma4:e4b`, `8192`
   context, temperature `0.1`, and seeds `11`, `22`, and `33`;
2. change one variable only: the evidence boundary in the focused audit
   prompt;
3. preserve all three defect majorities and at least two safe-case
   majorities;
4. require at least one of two context cases to receive
   `INSPECT_CONTEXT` by majority;
5. require zero high-confidence false positives and at least 75% structural
   validity;
6. run a real-repository field sample only after the synthetic gate passes.

## Explicit Non-Goals

Do not add unless repeated real usage proves the need:

- web UI;
- dashboards;
- embeddings;
- RAG;
- vector databases;
- multi-agent orchestration;
- autonomous code patching;
- full-repository autonomous review;
- complex audit analytics;
- product packaging.

## Evidence

- [Changelog](001_changelog.md.txt)
- [Historical audit quality log](002_audit_quality_log.md)
- [Original multi-seed benchmark](evaluation_results/gemma4_e4b_t01_seeds_11_22_33.json)
- [Compact-retry benchmark](evaluation_results/gemma4_e4b_t01_seeds_11_22_33_compact_retry.json)
- [Reverted validator experiment](evaluation_results/gemma4_e4b_t01_seeds_11_22_33_compact_retry_state_validator.json)
- [Contract-grounded benchmark v2 report](evaluation_results/decision_grade_benchmark_v2_baseline.md)
- [Contract-grounded benchmark v2 evidence](evaluation_results/decision_grade_benchmark_v2_baseline.json)

## License

Private / experimental project.
