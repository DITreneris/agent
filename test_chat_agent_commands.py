import sqlite3

import chat_agent
import memory_store
from audit_runner import ValidatedAuditResult
from chat_agent import contains_multiple_slash_commands, handle_memory_command

def test_contains_multiple_slash_commands_detects_multiple_commands():
    user_input = "/audit_lines chat_agent.py 1 20\n/audit_lines chat_agent.py 21 40"

    assert contains_multiple_slash_commands(user_input) is True


def test_contains_multiple_slash_commands_allows_single_command():
    user_input = "/audit_lines chat_agent.py 1 20"

    assert contains_multiple_slash_commands(user_input) is False


def test_multi_command_input_is_rejected():
    user_input = "/audit_lines chat_agent.py 1 20\n/audit_lines chat_agent.py 21 40"

    result = handle_memory_command(user_input)

    assert result == "Please run one command at a time.\nNo audit started."

def test_run_selected_code_audit_saves_rejected_attempt(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    monkeypatch.setattr(
        chat_agent,
        "run_validated_audit",
        lambda initial_prompt, model_call: ValidatedAuditResult(
            success=False,
            response="Invalid audit response",
            errors=[
                "EVIDENCE_LOW findings cannot use High confidence."
            ],
            retry_used=True,
        ),
    )

    result = chat_agent.run_selected_code_audit(
        file_name="audit_runner.py",
        audit_target="run_validated_audit",
        start_line=61,
        end_line=97,
        selected_content="def run_validated_audit():\n    pass",
    )

    assert "Audit output rejected after one retry." in result
    assert "Rejected attempt saved: #1" in result
    assert (
        "EVIDENCE_LOW findings cannot use High confidence."
        in result
    )

    conn = sqlite3.connect(test_db)
    row = conn.execute(
        """
        SELECT
            status,
            retry_used,
            attempt_count,
            validation_errors,
            response
        FROM audit_results
        WHERE id = 1
        """
    ).fetchone()

    assert row is not None
    assert row[0] == "rejected"
    assert row[1] == 1
    assert row[2] == 2
    assert row[3] == (
        "EVIDENCE_LOW findings cannot use High confidence."
    )
    assert row[4] == "Invalid audit response"
