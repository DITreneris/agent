# Tomas Critique Agent

Local CLI-first code-audit experiment designed to test whether structured output validation, same-file context, and human evaluation can reduce unsupported findings from a local LLM.

Built with Python, Pydantic AI, Ollama, and SQLite. The project is intentionally small, local, and focused on practical development-session audits.

> **Experimental status:** the implementation passes its verified automated test suite, but audit judgment is not validated for authoritative code review.

## Current State

| Measure | Verified state |
|---|---|
| Version | `v1.13.1 — Audit Calibration Guardrails` |
| Automated tests | `116 passed, 1 warning` |
| Calibration benchmark | `2 of 3 cases passed` |
| Production-repository pilot | `0 of 5 audits rated useful or partially useful` |
| Development target | Collect real development-session failures and add only repeated cases to the fixed benchmark |

The remaining test warning comes from the external `pydantic_ai` dependency, not from project code.

---

## How It Works

1. Select a manual line range, top-level Python function, or direct class method.
2. Add directly called top-level helpers from the same file as context.
3. Ask the local model for a strict seven-section audit.
4. Validate structure and semantic consistency between classification, evidence, action, test status, verdict, and confidence.
5. Regenerate one standalone audit if validation fails; reject it if the second response remains invalid.
6. Save accepted and rejected attempts to SQLite for history, statistics, and human evaluation.

Audit prompts mark paths and code as untrusted input and instruct the model not to follow embedded instructions, fake headings, or copied verdicts.

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

Project and context commands:

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

`/audit_file` remains available but is unreliable for larger files.

---

## Example Audit Workflow

Audit a top-level function:

```bash
/audit_function prompt_builder.py build_file_audit_prompt
```

Every accepted audit follows this contract:

```text
1. Bottom line
2. Direct critique
   Classification: <allowed classification>
   Evidence: <allowed evidence level>
   Why: <grounded explanation>
   Missing context: <specific artifact or none>
3. Better option
4. Next steps
   Recommended action: <allowed action>
   Test status: <allowed test status>
   Reason: <smallest justified next step>
5. Top 3 pitfalls
6. Verdict
   GO | GO_WITH_NOTES | BLOCK
7. Confidence
   High | Medium | Low
```

Then record whether the result was useful:

```bash
/rate_audit 41 USEFUL TEST_ADDED | Added regression coverage
/rate_audit 42 FALSE_POSITIVE NO_ACTION | Caller already handles the exception
/rate_audit 43 NEEDS_MORE_CONTEXT | Caller context is required
```

View the accumulated evidence:

```bash
/audit_history 5
/audit_stats
/evaluation_stats
```

---

## Capabilities and Boundaries

| Capability | Current boundary |
|---|---|
| Manual line-range audits | Maximum 200 lines; ranges must stay inside file bounds |
| Function audits | Top-level Python functions only |
| Method audits | Direct class methods only |
| Same-file context | Directly called top-level helpers discovered through Python AST |
| Cross-file context | Cross-file callers and helper implementations are not automatically resolved |
| Output contract | Seven deterministic, non-empty sections in a fixed order |
| Evidence guardrails | Selected low-evidence patterns are rejected when they recommend code changes or introduce unsupported requirements |
| Calibration checks | Known contradictory combinations between classification, action, test status, verdict, and confidence are rejected |
| Regeneration | One standalone retry before rejection |
| Persistence | Accepted and rejected attempts, validation errors, retries, status, and human evaluation are stored in SQLite |
| Audit reliability | Experimental; structural validity does not guarantee useful judgment |

Additional boundaries:

- nested and inherited methods are not resolved;
- duplicate names in nested scopes remain out of scope;
- only directly called helpers are included, not transitive dependencies;
- prompt construction is still mostly string-based;
- the local model can restate speculative findings in language not covered by validator rules;
- phrase-based and synonym-based validation has reached diminishing returns.

---

## Human Evaluation

Supported labels:

- `USEFUL`
- `PARTIALLY_USEFUL`
- `LOW_VALUE`
- `FALSE_POSITIVE`
- `NEEDS_MORE_CONTEXT`

Supported outcomes:

- `TEST_ADDED`
- `CODE_CHANGED`
- `INVESTIGATED_NO_CHANGE`
- `NO_ACTION`

Human evaluation remains separate from model validation. A structurally accepted audit can still be low-value, false-positive, or dependent on missing context.

---

## Quality Evidence

### Production-Repository Pilot

Five focused audits were evaluated:

| Human result | Count |
|---|---:|
| `USEFUL` | 0 |
| `PARTIALLY_USEFUL` | 0 |
| `LOW_VALUE` | 2 |
| `FALSE_POSITIVE` | 3 |
| `NO_ACTION` outcome | 5 |

The pilot showed that structural validation and prompt compliance do not guarantee useful reviewer judgment.

**Critique Agent must not currently be treated as an authoritative code reviewer.**

### v1.13.1 Calibration Benchmark

The fixed benchmark used three focused cases with Gemma 4 E4B:

- passed: 2 of 3 cases;
- failed: `case_003_intentional_none_contract`;
- the model incorrectly classified an intentional `None` fallback after one regeneration;
- the validator rejected the contradictory audit instead of accepting it.

The failed case is treated as a local-model judgment limitation. Further case-specific prompt tuning was stopped.

---

## Run and Test

```bash
python chat_agent.py
python -m pytest
```

Latest verified test result:

```text
116 passed, 1 warning
```

---

## Next Validation Step

Do not add new audit features unless they solve a measured failure or repeated real CLI friction.

Use the tool during real development sessions. Convert only repeated, evidence-backed failures into representative benchmark cases, then re-run the fixed benchmark before changing the audit architecture. Measure:

- useful audit rate;
- false-positive rate;
- unsupported-claim rate;
- correct verdict rate;
- validator rejection rate.

Only failures repeated across benchmark cases or real audits should trigger implementation changes. Until audit usefulness is validated, the project should remain local, CLI-first, deliberately small, and experimental.

---

## Explicit Non-Goals

Do not add unless repeated real CLI usage proves the need:

- web UI;
- dashboards;
- embeddings;
- RAG;
- vector databases;
- multi-agent orchestration;
- autonomous code patching;
- complex audit analytics;
- prompt template engine;
- full repository autonomous review.

---

## License

Private / experimental project.
