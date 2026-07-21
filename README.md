# Tomas Critique Agent

Local CLI-first code audit assistant built with Python, Pydantic AI, Ollama, and SQLite persistence.

The project is intentionally small, local, and focused on practical development-session code audits.

---

## Current Version

Current version:

v1.13.1 — Audit Calibration Guardrails

Latest verified state:

```text
116 passed, 1 warning

The remaining warning comes from the external `pydantic_ai` dependency, not from project code.

---

## What It Does

The agent can:

* audit selected manual line ranges;
* audit top-level Python functions by name;
* audit direct Python class methods by `ClassName.method_name`;
* validate audit output into a strict 7-section structure;
* retry once if the model output is malformed;
* reject malformed output after a failed retry;
* persist accepted audit results to SQLite;
* show recent audit history;
* show basic audit statistics;
* protect selected-code prompts with explicit untrusted input boundaries.
* validate semantic consistency between classification, evidence, recommended action, test status, and verdict;
* regenerate one standalone audit if the first response fails validation;
* reject the audit if the regenerated response remains invalid;

---

## Core Commands

```text
/help
/audit_lines <path> <start> <end>
/audit_function <path> <function_name>
/audit_method <path> <ClassName.method_name>
/audit_history [limit]
/audit_stats
/evaluation_stats
/rate_audit <id> <label> [outcome] [| note]
```

Additional project/context commands:

```text
/project
/project_summary
/project_files
/read_file <path>
/context
/inspect <path>
```

Memory commands:

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

`/audit_file` remains available but is considered legacy and unreliable for larger files.

---

## Example Usage

Audit a manual line range:

```bash
/audit_lines chat_agent.py 196 240
```

Audit a top-level function:

```bash
/audit_function prompt_builder.py build_file_audit_prompt
```

Audit a direct class method:

```bash
/audit_method chat_agent.py SomeClass.some_method
```

View recent audit results:

```bash
/audit_history 5
```

View audit statistics:

```bash
/audit_stats
/evaluation_stats
/rate_audit 41 USEFUL TEST_ADDED | Added regression coverage
/rate_audit 42 FALSE_POSITIVE NO_ACTION | Caller already handles the exception
/rate_audit 43 NEEDS_MORE_CONTEXT | Caller context is required
```

---

## Run

```bash
python chat_agent.py
```

---

## Test

```bash
python -m pytest
```

Latest verified result:

```text
97 passed, 1 warning
```

---

## Current Verified Capabilities

### Selected-Code Audits

* Manual line-range audits via `/audit_lines`.
* Top-level Python function audits via `/audit_function`.
* Direct Python class method audits via `/audit_method`.
* Maximum selected audit range: 200 lines.
* Selected audit ranges must be inside file bounds.
* Out-of-bounds `end_line` values are rejected with a clear error.

### Same-File Context

* Selected function, method, and line audits automatically include directly called top-level helper functions from the same Python file.
* Helper discovery uses Python AST.
* Helper names are propagated through audit preparation, prompt construction, execution, and semantic validation.
* Claims that an included helper definition or contract is missing are rejected.

### Evidence Hardening

* `EVIDENCE_LOW` findings cannot recommend code changes.
* Audits containing only `EVIDENCE_LOW` findings must use the `GO` verdict.
* Low-evidence findings cannot invent caller expectations, product requirements, business rules, or unstated contracts.
* Validator protections remain guardrails rather than a substitute for reliable model judgment.

### Audit Calibration Guardrails

* Contradictory classification, action, test-status, and verdict combinations are rejected.
* `MAINTAINABILITY_HARDENING` cannot recommend `NO_CHANGE`.
* Findings that require no code change must use a compatible classification.
* Retry generation produces a new standalone audit from the original request and visible code.
* Retry output must not refer to the previous response, validation errors, retry, repair, or formatting correction.
* Semantic validation remains a safety boundary; it does not guarantee correct local-model judgment.

### Output Reliability

* Enforces a deterministic 7-section audit output.
* Retries once when model output is malformed.
* Rejects invalid audit output after a failed retry.
* Separates verified defects, risks, assumptions, and future improvements.

### Persistence

* Accepted and rejected audit attempts are saved to SQLite.
* Stored data includes validation errors, retry usage, attempt count, final status, and optional human evaluation.
* `/audit_history [limit]` shows recent accepted and rejected audit attempts.
* `/audit_stats` shows total attempts, verdict counts, retries, rejection status, and most audited file.
* `/rate_audit <id> <label> [outcome] [| note]` stores a human evaluation for an accepted or rejected audit.
* `/evaluation_stats` shows reviewed and unreviewed audit counts, human-label percentages, and recorded outcomes.
* Human evaluation is separate from model validation. A structurally accepted audit can still be marked as low-value, false-positive, or requiring more context.

### Human Audit Evaluation

Supported labels:

* `USEFUL`
* `PARTIALLY_USEFUL`
* `LOW_VALUE`
* `FALSE_POSITIVE`
* `NEEDS_MORE_CONTEXT`

Supported outcomes:

* `TEST_ADDED`
* `CODE_CHANGED`
* `INVESTIGATED_NO_CHANGE`
* `NO_ACTION`

Use `|` before an optional note:

```text
/rate_audit 41 PARTIALLY_USEFUL INVESTIGATED_NO_CHANGE | Finding was valid but required no code change
```

### Prompt Boundary Hardening

* Audited file paths and code content are marked as untrusted.
* Embedded instructions inside audited code are not followed.
* Fake markdown headings, fake audit verdicts, and copied required-output headings inside code are guarded against.

### Testability

* `chat_agent.py` is import-safe.
* Importing `chat_agent.py` no longer starts the CLI loop.
* `prepare_selected_code_audit()` has direct unit test coverage.

---

## Current Quality Evidence

A production-repository evaluation pilot completed five focused audits.

* `USEFUL`: 0
* `PARTIALLY_USEFUL`: 0
* `LOW_VALUE`: 2
* `FALSE_POSITIVE`: 3
* `NO_ACTION`: 5

The pilot showed that structural validation and prompt compliance do not guarantee useful reviewer judgment.

Critique Agent must not currently be treated as an authoritative code reviewer.

---

### Latest Calibration Benchmark

The v1.13.1 calibration benchmark used three focused evaluation cases with Gemma 4 E4B.

* Passed: 2 of 3 cases.
* Failed: `case_003_intentional_none_contract`.
* The model incorrectly classified an intentional `None` fallback after one retry.
* The validator rejected the contradictory audit instead of accepting it.

This result is treated as a local-model judgment limitation. Further case-specific prompt tuning was stopped.


## Known Limitations

* `/audit_file` remains legacy and unreliable for larger files.
* `/audit_function` supports top-level Python functions only.
* `/audit_method` supports direct class methods only.
* Nested classes are not supported.
* Inherited methods are not resolved.
* Duplicate names in nested scopes remain out of scope.
* Only directly called top-level same-file helpers are extracted.
* Cross-file callers and helper implementations are not automatically resolved.
* Audit quality still depends on local LLM judgment.
* Structural validity does not guarantee useful reviewer judgment.
* The local model may restate speculative findings using wording not covered by validator rules.
* Phrase-based and synonym-based validation has reached diminishing returns.
* Current real-project evaluation showed a high false-positive and low-value rate.
* Future improvement may require a stronger model or different audit architecture.
* The prompt construction is still mostly string-based.
* The remaining warning comes from `pydantic_ai`, not project code.
* A structurally correct local-model response may still misclassify intentional or business-defined behavior.
* The current Gemma 4 E4B calibration benchmark passes 2 of 3 focused cases.

---

## Explicit Non-Goals

Do not add unless repeated real CLI usage proves the need:

* web UI;
* dashboards;
* embeddings;
* RAG;
* vector databases;
* multi-agent orchestration;
* autonomous code patching;
* complex audit analytics;
* prompt template engine;
* full repository autonomous review.

---

## Future Work Rule

No new audit feature work unless it solves a measured failure or repeated real CLI friction.

The next development step is a fixed evaluation benchmark, not another prompt rule or validator marker.

The benchmark should measure:

* useful audit rate;
* false-positive rate;
* unsupported-claim rate;
* correct verdict rate.

Until audit usefulness is validated, the project should remain local, CLI-first, deliberately small, and experimental.

---

## Project Status

```text
Status: Technically stable experimental audit tool

Current version: v1.12 — Same-File Context and Evidence Hardening

Audit quality status: Not validated for authoritative code review

Current development target: Fixed evaluation benchmark

Recommended next action: Re-run controlled audit cases before adding new audit features
```

---

## License

Private / experimental project.



