# Tomas Critique Agent

Local CLI-first code audit assistant built with Python, Pydantic AI, Ollama, and SQLite persistence.

The project is intentionally small, local, and focused on practical development-session code audits.

---

## Stable Baseline

Current stable baseline:

```text
v1.8 — Stable Local Audit Tool Baseline
```

Implementation baseline:

```text
v1.7 — Strict Selected Range Bounds
```

Latest verified state:

```text
44 passed, 1 warning
```

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
44 passed, 1 warning
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

### Output Reliability

* Enforces a deterministic 7-section audit output.
* Retries once when model output is malformed.
* Rejects invalid audit output after a failed retry.
* Separates verified defects, risks, assumptions, and future improvements.

### Persistence

* Validated audits are saved to SQLite.
* `/audit_history [limit]` shows recent saved audits.
* `/audit_stats` shows total audits, verdict counts, retry count, and most audited file.
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

## Known Limitations

* `/audit_file` remains legacy and unreliable for larger files.
* `/audit_function` supports top-level Python functions only.
* `/audit_method` supports direct class methods only.
* Nested classes are not supported.
* Inherited methods are not resolved.
* Duplicate names in nested scopes remain out of scope.
* Audit quality still depends on local LLM judgment.
* The prompt construction is still mostly string-based.
* The remaining warning comes from `pydantic_ai`, not project code.

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

No new feature work unless it solves repeated friction from real CLI usage.

Future development should be triggered only by observed usage pain, for example:

* `/audit_file` is repeatedly needed and unreliable;
* nested class methods are repeatedly needed;
* target discovery becomes a real bottleneck;
* audit output becomes too generic in repeated real use;
* SQLite history needs practical filtering after enough real audit data exists.

Until then, the project should remain stable, local, CLI-first, and deliberately small.

---

## Project Status

```text
Status: Stable local audit tool
Active next feature target: None
Recommended next action: Use in real development sessions before adding features
```

---

## License

Private / experimental project.



