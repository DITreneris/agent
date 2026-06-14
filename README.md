
Critique Agent

Local CLI-first code critique agent built with Python, Pydantic AI, Ollama, and SQLite persistence.

## Current Status

Current baseline: v1.1 — Function-Aware Chunking MVP

The agent can:

- audit selected code line ranges;
- audit Python functions by name;
- validate structured audit output;
- retry once if output is invalid;
- persist accepted audit results to SQLite;
- show recent audit history;
- show basic audit statistics.

## Core Commands

```text
/help
/audit_lines <path> <start> <end>
/audit_function <path> <function_name>
/audit_history [limit]
/audit_stats
Example
/audit_function prompt_builder.py build_file_audit_prompt
Verified


## Latest local verification:

27 passed, 1 warning

The remaining warning comes from the external pydantic_ai dependency.

## Roadmap

Next recommended step:

v1.2 — Extract shared audit execution logic

Do not add dashboards, RAG, embeddings, or multi-agent orchestration yet.

## License

Private / experimental project.


