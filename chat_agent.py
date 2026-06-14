from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import sqlite3
from datetime import datetime
from pathlib import Path
from project_config import PROJECT_ROOT
from project_scanner import scan_project_files, format_file_list, read_project_file
from project_context import build_project_summary
from prompt_builder import build_system_prompt, build_file_audit_prompt
from audit_runner import run_validated_audit
from code_chunker import find_python_function_range, FunctionNotFoundError
import json
import urllib.request

from memory_store import (
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

print("\nTomas Critique Agent")
print("Type 'exit' to quit.\n")

MAX_HISTORY = 10
history = load_recent_messages(MAX_HISTORY)

init_memory_db()

def run_ollama_audit(prompt: str) -> str:
    payload = {
        "model": "gemma4:e4b",
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.1,
        },
    }

    request = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))

    return data["message"]["content"]

def handle_memory_command(user_input: str):
    text = user_input.strip()

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
            "/audit_file <path>\n"
            "/audit_lines <path> <start> <end>\n"
            "/audit_function <path> <function_name>\n"
            "/audit_history [limit]\n"
            "/audit_stats\n"
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
            lines.append(
                f"#{row['id']} | {row['verdict']} | confidence: {row['confidence']} | "
                f"{row['file_path']}:{row['start_line']}-{row['end_line']} | "
                f"retry: {retry_used} | {row['created_at']}"
            )

        return "\n".join(lines)

    if text == "/audit_stats":
        stats = get_audit_stats()

        if stats["total"] == 0:
            return "No audit results found."

        lines = [
            "Audit stats:",
            f"Total audits: {stats['total']}",
        ]

        for verdict, count in stats["verdict_counts"].items():
            lines.append(f"{verdict}: {count}")

        lines.append(f"Retries used: {stats['retries_used']}")

        most_audited_file = stats["most_audited_file"]

        if most_audited_file:
            lines.append(f"Most audited file: {most_audited_file}")

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

        if end_line - start_line + 1 > 200:
            return "Maximum audit range is 200 lines."

        try:
            lines = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
        except OSError as exc:
            return f"Could not read file: {exc}"

        selected_content = "\n".join(
            f"{line_number}: {lines[line_number - 1]}"
            for line_number in range(start_line, end_line + 1)
        )

        audit_target = (
            f"{file_name}, function {function_name}, "
            f"lines {start_line}-{end_line}"
        )

        full_prompt = build_file_audit_prompt(
            audit_target,
            selected_content,
        )

        validated_result = run_validated_audit(
            initial_prompt=full_prompt,
            model_call=run_ollama_audit,
        )

        if not validated_result.success:
            error_details = "\n".join(
                f"- {error}"
                for error in validated_result.errors
            )

            return (
                "Audit output rejected after one retry.\n"
                f"{error_details}"
            )

        audit_id = create_audit_result(
            file_path=file_name,
            start_line=start_line,
            end_line=end_line,
            response=validated_result.response,
            retry_used=validated_result.retry_used,
        )

        return f"{validated_result.response}\n\nAudit saved: #{audit_id}"

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

        if start_line < 1 or end_line < start_line:
            return "Invalid line range."

        if end_line - start_line + 1 > 200:
            return "Maximum audit range is 200 lines."

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
            lines = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()
        except OSError as exc:
            return f"Could not read file: {exc}"

        if start_line > len(lines):
            return f"Start line exceeds file length: {len(lines)} lines"

        end_line = min(end_line, len(lines))

        selected_content = "\n".join(
            f"{line_number}: {lines[line_number - 1]}"
            for line_number in range(start_line, end_line + 1)
        )

        audit_target = f"{file_name}, lines {start_line}-{end_line}"
        full_prompt = build_file_audit_prompt(
            audit_target,
            selected_content,
        )

        validated_result = run_validated_audit(
            initial_prompt=full_prompt,
            model_call=run_ollama_audit,
        )


        if not validated_result.success:
            error_details = "\n".join(
                f"- {error}"
                for error in validated_result.errors
            )

            return (
                "Audit output rejected after one retry.\n"
                f"{error_details}"
            )

        audit_id = create_audit_result(
            file_path=file_name,
            start_line=start_line,
            end_line=end_line,
            response=validated_result.response,
            retry_used=validated_result.retry_used,
        )

        return f"{validated_result.response}\n\nAudit saved: #{audit_id}"

    if text.startswith("/audit_file"):
        file_name = text.removeprefix("/audit_file").strip()

        if not file_name:
            return "Usage: /audit_file <path>"

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

        file_content = read_project_file(file_path)

        full_prompt = build_file_audit_prompt(
            file_name,
            file_content,
        )
        return run_ollama_audit(full_prompt)

    if text == "/audit":
        audit_prompt = build_system_prompt(
            """
Audit this local AI agent project.

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
            "inspect <path>\n"
            "/audit\n"
            "/audit_file <path>\n"
            "/audit_lines <path> <start> <end>\n"
            "/audit_history [limit]\n"
            "/audit_stats"
      )

    return None


while True:
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

