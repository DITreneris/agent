from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import hashlib
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from project_config import PROJECT_ROOT
from project_scanner import scan_project_files, format_file_list, read_project_file
from project_context import build_project_summary
from prompt_builder import build_system_prompt, build_file_audit_prompt
from audit_runner import run_validated_audit
from audit_case import (
    AuditCaseIntegrityError,
    export_audit_case,
)

from audit_model_client import (
    DEFAULT_OLLAMA_AUDIT_CONFIG,
    OllamaAuditConfig,
    call_ollama_audit,
)

from audit_context import (
    build_same_file_context,
    build_same_file_context_names,
)

from code_chunker import (
    find_python_function_range,
    find_python_method_range,
    FunctionNotFoundError,
    MethodNotFoundError,
)


from memory_store import (
    AuditEvidence,
    init_memory_db,
    create_memory,
    read_memories,
    update_memory,
    delete_memory,
    clear_memories,
    format_memories_for_user,
    format_memories_for_prompt,
    create_audit_result,
    get_recent_audit_results,
    get_audit_stats,
    rate_audit,
    VALID_HUMAN_LABELS,
    VALID_HUMAN_OUTCOMES,
    get_human_evaluation_stats,
    AuditCaseNotFoundError,
    AuditEvidenceNotFoundError,
)

client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

model = OpenAIChatModel(
    "gemma4:e4b",
    provider=OpenAIProvider(openai_client=client),
)

SYSTEM_PROMPT = """
You are Tomas Critique Agent, a local strategy-and-execution and technical audit assistant.

Runtime facts:
- You run locally through Pydantic AI.
- Ollama is the local model backend.
- Ollama API endpoint: localhost:11434.
- Current model: gemma4:e4b.
- Do not claim you run on Google, OpenAI, Anthropic, or any cloud infrastructure.

Core role:
- You are a senior strategy-and-execution practitioner.
- Your job is to improve real-world outcomes, not agreement.
- Be concise, practical, and execution-focused.
- Prefer fixes, commands, patches, and next actions over theory.

Response modes:
1. Simple facts, names, preferences, or personal context:
   - Reply with one short acknowledgement.
   - Do not critique simple facts.
   - Never treat names mentioned by the user as the user's name unless the user explicitly says "my name is".
   - When the user provides a fact about another person, acknowledge the fact in third person.

2. Plans, ideas, strategies, decisions, or prioritization:
   - Use structured critique.
   - Structure:
     1. Bottom line
     2. Direct critique
     3. Better option
     4. Next steps
     5. Top 3 pitfalls
   - Identify weak assumptions, logic gaps, risks, feasibility issues, and low-ROI activities.

3. Code, repo, or project audits:
   - Do not invent file contents.
   - Use PROJECT CONTEXT when it is provided.
   - Never say project file access is unavailable when PROJECT CONTEXT is present.
   - If full file contents are needed, tell the user to run /inspect <path> or /read_file <path>.
   - When the current prompt provides a specific output structure, follow that structure exactly.
   - Do not replace, rename, reorder, or expand command-specific output sections.
   - When no command-specific structure is provided, return:
     1. Bottom line
     2. Direct critique
     3. Risk level
     4. Recommended fix
     5. Next command

Project context rules:
- Compact project context is enough for high-level reasoning.
- Full file content is required for line-level code critique.
- If evidence is insufficient, say exactly what is missing and what command should be run next.

Style:
- English by default.
- Short, direct, and operational.
- No motivational filler.
- No fake certainty.
"""

agent = Agent(
    model,
    system_prompt=SYSTEM_PROMPT,
    model_settings=ModelSettings(
        temperature=0.1,
    ),
)

DB_PATH = "memory.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")

conn.commit()


def save_message(role: str, content: str):
    cursor.execute(
        "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
        (role, content, datetime.now().isoformat())
    )
    conn.commit()


def load_recent_messages(limit: int = 10):
    cursor.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    rows.reverse()
    return [f"{role}: {content}" for role, content in rows]

MAX_HISTORY = 10
MAX_AUDIT_LINES = 200
history = load_recent_messages(MAX_HISTORY)

init_memory_db()

def run_ollama_audit(
    prompt: str,
    config: OllamaAuditConfig = DEFAULT_OLLAMA_AUDIT_CONFIG,
) -> str:
    return call_ollama_audit(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        config=config,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class SelectedCodeAuditPreparation:
    file_path: Path
    relative_path: str
    selected_content: str
    context_content: str
    context_names: set[str]
    start_line: int
    end_line: int


def prepare_selected_code_audit(
    project_root: Path,
    file_name: str,
    start_line: int,
    end_line: int,
) -> SelectedCodeAuditPreparation:
    if start_line < 1 or end_line < start_line:
        raise ValueError("Invalid line range.")

    if end_line - start_line + 1 > MAX_AUDIT_LINES:
        raise ValueError(f"Maximum audit range is {MAX_AUDIT_LINES} lines.")

    resolved_project_root = project_root.resolve()
    file_path = (resolved_project_root / file_name).resolve()

    try:
        file_path.relative_to(resolved_project_root)
    except ValueError:
        raise ValueError(f"Access denied: {file_name}")

    if not file_path.exists():
        raise ValueError(f"File not found: {file_name}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_name}")

    try:
        lines = file_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError as exc:
        raise ValueError(f"Could not read file: {exc}")

    if start_line > len(lines):
        raise ValueError(f"Start line exceeds file length: {len(lines)} lines")

    if end_line > len(lines):
        raise ValueError(f"End line exceeds file length: {len(lines)} lines")

    selected_content = "\n".join(
        f"{line_number}: {lines[line_number - 1]}"
        for line_number in range(start_line, end_line + 1)
    )

    context_content = build_same_file_context(
        file_path=file_path,
        target_start_line=start_line,
        target_end_line=end_line,
    )

    context_names = build_same_file_context_names(
        file_path=file_path,
        target_start_line=start_line,
        target_end_line=end_line,
    )

    return SelectedCodeAuditPreparation(
        file_path=file_path,
        relative_path=file_name,
        selected_content=selected_content,
        context_content=context_content,
        context_names=context_names,
        start_line=start_line,
        end_line=end_line,
    )

def run_selected_code_audit(
    file_name: str,
    audit_target: str,
    start_line: int,
    end_line: int,
    selected_content: str,
    context_content: str = "",
    context_names: set[str] | None = None,
    config: OllamaAuditConfig = DEFAULT_OLLAMA_AUDIT_CONFIG,
) -> str:
    full_prompt = build_file_audit_prompt(
        audit_target,
        selected_content,
        context_content,
    )

    validated_result = run_validated_audit(
        initial_prompt=full_prompt,
        model_call=lambda prompt: run_ollama_audit(
            prompt,
            config=config,
        ),
        available_context_names=context_names,
    )

    retry_prompt_sha256 = (
        _sha256_text(validated_result.retry_prompt)
        if validated_result.retry_prompt is not None
        else None
    )

    evidence = AuditEvidence(
        audit_target=audit_target,
        selected_content=selected_content,
        context_content=context_content,
        context_names=sorted(context_names or set()),
        initial_prompt=full_prompt,
        initial_prompt_sha256=_sha256_text(full_prompt),
        system_prompt_sha256=_sha256_text(SYSTEM_PROMPT),
        model_config=asdict(config),
        first_response=validated_result.first_response or "",
        first_validation_errors=list(
            validated_result.first_validation_errors
        ),
        retry_prompt=validated_result.retry_prompt,
        retry_prompt_sha256=retry_prompt_sha256,
        retry_response=validated_result.retry_response,
        retry_validation_errors=list(
            validated_result.retry_validation_errors
        ),
    )

    if not validated_result.success:
        audit_id = create_audit_result(
            file_path=file_name,
            start_line=start_line,
            end_line=end_line,
            response=validated_result.response or "",
            retry_used=validated_result.retry_used,
            status="rejected",
            validation_errors=validated_result.errors,
            evidence=evidence,
        )

        if validated_result.errors:
            error_details = "\n".join(
                f"- {error}"
                for error in validated_result.errors
            )
        else:
            error_details = "- No validation error details were returned."

        return (
            "Audit output rejected after one retry.\n"
            f"Rejected attempt saved: #{audit_id}\n"
            f"{error_details}"
        )

    audit_id = create_audit_result(
        file_path=file_name,
        start_line=start_line,
        end_line=end_line,
        response=validated_result.response,
        retry_used=validated_result.retry_used,
        evidence=evidence,
    )

    return f"{validated_result.response}\n\nAudit saved: #{audit_id}"


def contains_multiple_slash_commands(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    slash_command_lines = [line for line in lines if line.startswith("/")]
    return len(slash_command_lines) > 1


def handle_memory_command(user_input: str):
    text = user_input.strip()

    if contains_multiple_slash_commands(text):
        return "Please run one command at a time.\nNo audit started."

    if text in ["/memory", "/show_memory"]:
        return format_memories_for_user()

    if text.startswith("/remember "):
        content = text.replace("/remember ", "", 1).strip()

        if not content:
            return "Usage: /remember <fact>"

        memory_id = create_memory(content)
        return f"Saved memory #{memory_id}: {content}"

    if text.startswith("/delete_memory "):
        raw_id = text.replace("/delete_memory ", "", 1).strip()

        if not raw_id.isdigit():
            return "Usage: /delete_memory <id>"

        memory_id = int(raw_id)
        deleted = delete_memory(memory_id)

        if deleted:
            return f"Deleted memory #{memory_id}."

        return f"Memory #{memory_id} not found."

    if text.startswith("/update_memory "):
        payload = text.replace("/update_memory ", "", 1).strip()

        if "|" not in payload:
            return "Usage: /update_memory <id> | <new content>"

        raw_id, new_content = payload.split("|", 1)

        raw_id = raw_id.strip()
        new_content = new_content.strip()

        if not raw_id.isdigit():
            return "Memory ID must be a number."

        if not new_content:
            return "New content cannot be empty."

        memory_id = int(raw_id)
        updated = update_memory(memory_id, new_content)

        if updated:
            return f"Updated memory #{memory_id}: {new_content}"

        return f"Memory #{memory_id} not found."

    if text.startswith("/forget "):
        search_text = text.replace("/forget ", "", 1).strip().lower()

        if not search_text:
            return "Usage: /forget <text>"

        memories = read_memories()

        matched = [
            memory for memory in memories
            if search_text in memory["content"].lower()
        ]

        if not matched:
            return "No matching memory found."

        if len(matched) > 1:
            lines = ["Multiple matching memories found. Delete by ID:"]
            for memory in matched:
                lines.append(f"{memory['id']}. {memory['content']}")
            return "\n".join(lines)

        memory_id = matched[0]["id"]
        delete_memory(memory_id)

        return f"Forgot memory #{memory_id}: {matched[0]['content']}"

    if text == "/clear_memory":
        count = clear_memories()
        return f"Cleared {count} memory item(s)."

    if text == "/help":
        return (
            "Available commands:\n"
            "/help\n"
            "/memory\n"
            "/remember <fact>\n"
            "/update_memory <id> | <new content>\n"
            "/delete_memory <id>\n"
            "/forget <text>\n"
            "/clear_memory\n"
            "/project\n"
            "/project_summary\n"
            "/project_files\n"
            "/read_file <path>\n"
            "/context\n"
            "/inspect <path>\n"
            "/audit\n"
            "/audit_file <path>  [legacy: use /audit_lines, /audit_function, or /audit_method]\n"
            "/audit_lines <path> <start> <end>\n"
            "/audit_function <path> <function_name>\n"
            "/audit_method <path> <ClassName.method_name>\n"
            "/audit_history [limit]\n"
            "/audit_stats\n"
            "/export_audit_case <id>\n"
            "/evaluation_stats\n"
            "/rate_audit <id> <label> [outcome] [| note]\n"
        )


    if text == "/project":
        files = scan_project_files(PROJECT_ROOT)
        root_path = PROJECT_ROOT.resolve()

        lines = [
            f"Project root: {root_path}",
            f"Files indexed: {len(files)}",
            "",
            "Main files:",
        ]

        for index, file_path in enumerate(files, start=1):
            relative_path = file_path.relative_to(root_path)
            lines.append(f"{index}. {relative_path}")

        return "\n".join(lines)


    if text.startswith("/rate_audit"):
        raw_arguments = text.removeprefix("/rate_audit").strip()

        if not raw_arguments:
            return (
                "Usage: /rate_audit <id> <label> "
                "[outcome] [| note]"
            )

        command_part, separator, note_part = raw_arguments.partition("|")
        arguments = command_part.strip().split()

        if len(arguments) < 2 or len(arguments) > 3:
            return (
                "Usage: /rate_audit <id> <label> "
                "[outcome] [| note]"
            )

        audit_id_text = arguments[0]
        human_label = arguments[1].upper()
        human_outcome = None
        human_note = note_part.strip() if separator else None

        if not audit_id_text.isdigit():
            return "Audit ID must be a number."

        audit_id = int(audit_id_text)

        if human_label not in VALID_HUMAN_LABELS:
            return (
                f"Invalid label: {human_label}\n"
                "Allowed labels: "
                + ", ".join(sorted(VALID_HUMAN_LABELS))
            )

        if len(arguments) == 3:
            human_outcome = arguments[2].upper()

            if human_outcome not in VALID_HUMAN_OUTCOMES:
                return (
                    f"Invalid outcome: {human_outcome}\n"
                    "Allowed outcomes: "
                    + ", ".join(sorted(VALID_HUMAN_OUTCOMES))
                )

        updated = rate_audit(
            audit_id,
            human_label,
            human_outcome,
            human_note,
        )

        if not updated:
            return f"Unknown audit ID: {audit_id}"

        lines = [
            f"Audit #{audit_id} rated:",
            f"Label: {human_label}",
        ]

        if human_outcome:
            lines.append(f"Outcome: {human_outcome}")

        if human_note:
            lines.append(f"Note: {human_note}")

        return "\n".join(lines)


    if text.startswith("/export_audit_case"):
        arguments = (
            text.removeprefix("/export_audit_case")
            .strip()
            .split()
        )

        if (
            len(arguments) != 1
            or not arguments[0].isdigit()
            or int(arguments[0]) < 1
        ):
            return "Usage: /export_audit_case <id>"

        audit_id = int(arguments[0])

        try:
            exported_path = export_audit_case(audit_id)
        except (
            AuditCaseNotFoundError,
            AuditEvidenceNotFoundError,
        ) as exc:
            return str(exc)
        except (AuditCaseIntegrityError, OSError) as exc:
            return f"Audit case export failed: {exc}"

        return (
            f"Audit case #{audit_id} exported:\n"
            f"{exported_path}"
        )


    if text.startswith("/audit_history"):
        arguments = text.removeprefix("/audit_history").strip().split()

        if len(arguments) > 1:
            return "Usage: /audit_history [limit]"

        limit = 10

        if arguments:
            if not arguments[0].isdigit():
                return "Limit must be a number."

            limit = int(arguments[0])

        rows = get_recent_audit_results(limit)

        if not rows:
            return "No audit results found."

        lines = ["Latest audit results:"]
        for row in rows:
            retry_used = "true" if row["retry_used"] else "false"

            human_parts = []

            if row["human_label"] != "NOT_REVIEWED":
                human_parts.append(
                    f"human: {row['human_label']}"
                )

            if row["human_outcome"]:
                human_parts.append(
                    f"outcome: {row['human_outcome']}"
                )

            human_text = ""

            if human_parts:
                human_text = " | " + " | ".join(human_parts)

            if row["status"] == "rejected":
                lines.append(
                    f"#{row['id']} | REJECTED"
                    f"{human_text} | "
                    f"{row['file_path']}:"
                    f"{row['start_line']}-{row['end_line']} | "
                    f"retry: {retry_used} | "
                    f"attempts: {row['attempt_count']} | "
                    f"{row['created_at']}"
                )

                if row["validation_errors"]:
                    lines.append(
                        f"  Reason: {row['validation_errors']}"
                    )
            else:
                lines.append(
                    f"#{row['id']} | {row['verdict']} | "
                    f"confidence: {row['confidence']}"
                    f"{human_text} | "
                    f"{row['file_path']}:"
                    f"{row['start_line']}-{row['end_line']} | "
                    f"retry: {retry_used} | "
                    f"attempts: {row['attempt_count']} | "
                    f"{row['created_at']}"
                )

        return "\n".join(lines)


    if text == "/audit_stats":
        stats = get_audit_stats()

        if stats["total"] == 0:
            return "No audit results found."

        lines = [
            "Audit stats:",
            f"Total attempts: {stats['total']}",
            f"Accepted: {stats['status_counts'].get('accepted', 0)}",
            f"Rejected: {stats['status_counts'].get('rejected', 0)}",
        ]

        for verdict, count in stats["verdict_counts"].items():
            lines.append(f"{verdict}: {count}")

        lines.append(f"Retries used: {stats['retries_used']}")

        most_audited_file = stats["most_audited_file"]

        if most_audited_file:
            lines.append(f"Most audited file: {most_audited_file}")

        return "\n".join(lines)


    if text == "/evaluation_stats":
        stats = get_human_evaluation_stats()

        if stats["total"] == 0:
            return "No audit results found."

        lines = [
            "Human evaluation stats:",
            "",
            f"Total audits: {stats['total']}",
            f"Reviewed: {stats['reviewed']}",
            f"Not reviewed: {stats['not_reviewed']}",
        ]

        if stats["reviewed"] == 0:
            lines.append("")
            lines.append("No audits have been reviewed yet.")
            return "\n".join(lines)

        lines.append("")
        lines.append("Labels:")

        label_order = [
            "USEFUL",
            "PARTIALLY_USEFUL",
            "LOW_VALUE",
            "FALSE_POSITIVE",
            "NEEDS_MORE_CONTEXT",
        ]

        for label in label_order:
            count = stats["label_counts"].get(label, 0)
            percentage = count / stats["reviewed"] * 100

            lines.append(
                f"{label}: {count} ({percentage:.1f}%)"
            )

        lines.append("")
        lines.append("Outcomes:")

        outcome_order = [
            "TEST_ADDED",
            "CODE_CHANGED",
            "INVESTIGATED_NO_CHANGE",
            "NO_ACTION",
        ]

        for outcome in outcome_order:
            count = stats["outcome_counts"].get(outcome, 0)
            lines.append(f"{outcome}: {count}")

        return "\n".join(lines)


    if text == "/context":
        files = scan_project_files(PROJECT_ROOT)

        return (
            "Runtime context:\n"
            "- Memory injection: enabled\n"
            "- Project context injection: enabled\n"
            f"- Project root: {PROJECT_ROOT.resolve()}\n"
            f"- Indexed files: {len(files)}\n"
            "- Auto full-file injection: disabled\n"
            "- Full file reading: explicit only via /read_file\n"
        )

    if text == "/project_summary":
        return build_project_summary(PROJECT_ROOT)

    if text == "/project_files":
        files = scan_project_files(PROJECT_ROOT)
        return format_file_list(files, PROJECT_ROOT)

    if text.startswith("/inspect "):
        file_name = text.replace("/inspect ", "", 1).strip()

        if not file_name:
            return "Usage: /inspect <path>"

        project_root = PROJECT_ROOT.resolve()
        file_path = (project_root / file_name).resolve()

        if not str(file_path).startswith(str(project_root)):
            return f"Access denied: {file_name}"

        if not file_path.exists():
            return f"File not found: {file_name}"

        if file_path.is_dir():
            return f"Path is a directory, not a file: {file_name}"

        return read_project_file(file_path)

    if text.startswith("/audit_function"):
        arguments = text.removeprefix("/audit_function").strip().split()

        if len(arguments) != 2:
            return "Usage: /audit_function <path> <function_name>"

        file_name, function_name = arguments

        project_root = PROJECT_ROOT.resolve()
        file_path = (project_root / file_name).resolve()

        try:
            file_path.relative_to(project_root)
        except ValueError:
            return f"Access denied: {file_name}"

        if not file_path.exists():
            return f"File not found: {file_name}"

        if not file_path.is_file():
            return f"Path is not a file: {file_name}"

        try:
            start_line, end_line = find_python_function_range(
                file_path,
                function_name,
            )
        except FunctionNotFoundError:
            return f"Function not found: {function_name}"
        except SyntaxError:
            return f"Cannot parse Python file: {file_name}"
        except OSError as exc:
            return f"Could not read file: {exc}"

        try:
            prepared = prepare_selected_code_audit(
                project_root=PROJECT_ROOT,
                file_name=file_name,
                start_line=start_line,
                end_line=end_line,
            )
        except ValueError as exc:
            return str(exc)

        audit_target = (
            f"{file_name}, function {function_name}, "
            f"lines {prepared.start_line}-{prepared.end_line}"
        )

        return run_selected_code_audit(
            file_name=file_name,
            audit_target=audit_target,
            start_line=prepared.start_line,
            end_line=prepared.end_line,
            selected_content=prepared.selected_content,
            context_content=prepared.context_content,
            context_names=prepared.context_names,
        )

    if text.startswith("/audit_method"):
        arguments = text.removeprefix("/audit_method").strip().split()

        if len(arguments) != 2:
            return "Usage: /audit_method <path> <ClassName.method_name>"

        file_name, method_target = arguments

        if "." not in method_target:
            return "Usage: /audit_method <path> <ClassName.method_name>"

        class_name, method_name = method_target.split(".", 1)

        if not class_name or not method_name:
            return "Usage: /audit_method <path> <ClassName.method_name>"

        project_root = PROJECT_ROOT.resolve()
        file_path = (project_root / file_name).resolve()

        try:
            file_path.relative_to(project_root)
        except ValueError:
            return f"Access denied: {file_name}"

        if not file_path.exists():
            return f"File not found: {file_name}"

        if not file_path.is_file():
            return f"Path is not a file: {file_name}"

        try:
            start_line, end_line = find_python_method_range(
                file_path,
                class_name,
                method_name,
            )
        except MethodNotFoundError:
            return f"Method not found: {class_name}.{method_name}"
        except SyntaxError:
            return f"Cannot parse Python file: {file_name}"
        except OSError as exc:
            return f"Could not read file: {exc}"

        try:
            prepared = prepare_selected_code_audit(
                project_root=PROJECT_ROOT,
                file_name=file_name,
                start_line=start_line,
                end_line=end_line,
            )
        except ValueError as exc:
            return str(exc)

        audit_target = (
            f"{file_name}, method {class_name}.{method_name}, "
            f"lines {prepared.start_line}-{prepared.end_line}"
        )

        return run_selected_code_audit(
            file_name=file_name,
            audit_target=audit_target,
            start_line=prepared.start_line,
            end_line=prepared.end_line,
            selected_content=prepared.selected_content,
            context_content=prepared.context_content,
            context_names=prepared.context_names,
        )

    if text.startswith("/audit_lines"):
        arguments = text.removeprefix("/audit_lines").strip().split()

        if len(arguments) != 3:
            return "Usage: /audit_lines <path> <start> <end>"

        file_name, start_text, end_text = arguments

        try:
            start_line = int(start_text)
            end_line = int(end_text)
        except ValueError:
            return "Line numbers must be integers."

        try:
            prepared = prepare_selected_code_audit(
                project_root=PROJECT_ROOT,
                file_name=file_name,
                start_line=start_line,
                end_line=end_line,
            )
        except ValueError as exc:
            return str(exc)

        audit_target = (
            f"{file_name}, lines {prepared.start_line}-{prepared.end_line}"
        )

        return run_selected_code_audit(
            file_name=file_name,
            audit_target=audit_target,
            start_line=prepared.start_line,
            end_line=prepared.end_line,
            selected_content=prepared.selected_content,
            context_content=prepared.context_content,
            context_names=prepared.context_names,
        )


    if text.startswith("/audit_file"):
        file_name = text.removeprefix("/audit_file").strip()

        if not file_name:
            return "Usage: /audit_file <path>"

        return (
            "/audit_file is legacy and unreliable for larger or complex files.\n\n"
            "Use focused audit commands instead:\n\n"
            "/audit_lines <path> <start> <end>\n"
            "/audit_function <path> <function_name>\n"
            "/audit_method <path> <ClassName.method_name>"
        )

    if text == "/audit":
        audit_prompt = build_system_prompt(
            """
Audit this local AI agent project at a high level.

Important:
- Do not recommend /audit_file.
- /audit_file is legacy and unreliable for larger or complex files.
- Do not invent function names.
- If exact code-level evidence is needed, recommend /project_files first or ask the user to choose a focused audit target.
- Recommend focused audit commands only:
  - /audit_lines <path> <start> <end>
  - /audit_function <path> <function_name>
  - /audit_method <path> <ClassName.method_name>

Return only:
1. What works
2. What is weak
3. Highest ROI next improvement
4. Risks
5. Suggested next version
"""
        )

        result = agent.run_sync(audit_prompt)
        return result.output

    if text.startswith("/read_file "):
        file_name = text.replace("/read_file ", "", 1).strip()

        if not file_name:
            return "Usage: /read_file <path>"

        project_root = PROJECT_ROOT.resolve()
        file_path = (project_root / file_name).resolve()

        if not str(file_path).startswith(str(project_root)):
            return f"Access denied: {file_name}"

        if not file_path.exists():
            return f"File not found: {file_name}"

        if file_path.is_dir():
            return f"Path is a directory, not a file: {file_name}"

        return read_project_file(file_path)

    if text.startswith("/"):
        return (
            "Unknown command.\n"
            "Available commands:\n"
            "/help\n"
            "/memory\n"
            "/remember <fact>\n"
            "/update_memory <id> | <new content>\n"
            "/delete_memory <id>\n"
            "/forget <text>\n"
            "/clear_memory\n"
            "/project\n"
            "/project_summary\n"
            "/project_files\n"
            "/read_file <path>\n"
            "/context\n"
            "/inspect <path>\n"
            "/audit\n"
            "/audit_file <path>  [legacy: use /audit_lines, /audit_function, or /audit_method]\n"
            "/audit_lines <path> <start> <end>\n"
            "/audit_function <path> <function_name>\n"
            "/audit_method <path> <ClassName.method_name>\n"
            "/audit_history [limit]\n"
            "/audit_stats\n"
            "/export_audit_case <id>\n"
            "/evaluation_stats\n"
            "/rate_audit <id> <label> [outcome] [| note]\n"
      )

    return None


def main() -> None:
    global history

    while True:
        try:
            user_input = input("You> ").strip()

            if user_input.lower() in ["exit", "quit"]:
                break

            command_response = handle_memory_command(user_input)

            if command_response is not None:
                print("\nAgent>")
                print(command_response)
                print("\n" + "-" * 60 + "\n")
                continue

            history.append(f"User: {user_input}")
            save_message("User", user_input)
            history = history[-MAX_HISTORY:]

            stored_memory = format_memories_for_prompt()

            prompt = f"""Recent conversation:
{chr(10).join(history)}

Current user message:
{user_input}
"""

            full_prompt = build_system_prompt(prompt)
            result = agent.run_sync(full_prompt)

            answer = result.output

            history.append(f"Assistant: {answer}")
            save_message("Assistant", answer)
            history = history[-MAX_HISTORY:]

            print("\nAgent>")
            print(answer)
            print("\n" + "-" * 60 + "\n")

        except KeyboardInterrupt:
            print("\nAudit interrupted by user.")
            print("No audit saved.")
            print("Returning to prompt...")
            print("\n" + "-" * 60 + "\n")
            continue

if __name__ == "__main__":
    print("\nTomas Critique Agent")
    print("Type 'exit' to quit.\n")
    main()


