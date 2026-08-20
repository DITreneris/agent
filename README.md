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
| Latest recorded local tests | `159 passed, 1 external dependency warning` |
| Fixed benchmark | 3 cases × 3 configured seeds |
| Previous repair prompt | `6 of 9` passed; retries succeeded `0 of 2` |
| Current compact repair prompt | `8 of 9` passed; retries succeeded `2 of 2` |
| Remaining unstable case | `case_003_intentional_none_contract` passed `2 of 3` |
| Historical real-repository pilot | `0 of 5` audits rated useful or partially useful |
| Consecutive field sample | `0 of 8` useful or partially useful; `6 of 8` structurally rejected |
| Current development target | Diagnose clustered structural failures in captured field audits |

The first consecutive eight-audit field sample produced six structurally
rejected outputs, one accepted low-value output, one accepted
needs-more-context output, and no useful or partially useful audits. Offline
replay found zero validator drift and zero fixture-integrity failures.

The latest benchmark improved controlled retry behavior, but it does not prove
that the agent is useful on real repositories.

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

Run the current three-case benchmark with three configured seeds:

```bash
python evaluation_runner.py \
  --model gemma4:e4b \
  --temperature 0.1 \
  --seeds 11,22,33 \
  --output /tmp/critique-agent-benchmark.json
```

### Recorded Results

| Experiment | Result | Retry result | Decision |
|---|---:|---:|---|
| Original repair prompt | `6/9` | `0/2` | Replaced |
| Compact repair prompt | `8/9` | `2/2` | Kept |
| Compact prompt + phrase-based state validator | `6/9` | `0/1` | Reverted |

Cases 001 and 002 passed `3/3` in every recorded multi-seed run.

Case 003 remains the false-positive trap. The model still invents alternative
caller or product requirements for an intentional `None` contract.

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
- per-case stability summaries;
- raw response and retry diagnostics;
- the compact standalone repair prompt;
- one retry before rejection;
- human evaluation separate from model validation.

Reject:

- the phrase-based state-distinction validator;
- additional synonym markers;
- case-specific prompt rules;
- treating `8/9` as proof of real-repository usefulness.

Next validation gate:

1. inspect the captured first responses, retry prompts, and retry responses for
   audits `58–65`;
2. group failures into missing-label, incomplete-output, and duplicated-repair
   clusters;
3. implement the smallest shared repair fix without case-specific rules;
4. rerun the same eight audit targets with unchanged model configuration;
5. require at least six of eight structurally accepted audits before investing
   in deeper judgment architecture;
6. evaluate usefulness only after the structural acceptance gate is restored.

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

## License

Private / experimental project.
