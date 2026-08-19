import json
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
        lambda initial_prompt, model_call, available_context_names=None: ValidatedAuditResult(
            success=False,
            response="Invalid audit response",
            errors=[
                "EVIDENCE_LOW findings cannot use High confidence."
            ],
            retry_used=True,
            first_response="Invalid first response",
            first_validation_errors=["Missing sections"],
            retry_response="Invalid audit response",
            retry_validation_errors=[
                "EVIDENCE_LOW findings cannot use High confidence."
            ],
            retry_prompt="Repair prompt",
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

    evidence_row = conn.execute(
        """
        SELECT
            audit_target,
            selected_content,
            context_content,
            context_names_json,
            initial_prompt,
            initial_prompt_sha256,
            system_prompt_sha256,
            model_config_json,
            first_response,
            first_validation_errors_json,
            retry_prompt,
            retry_prompt_sha256,
            retry_response,
            retry_validation_errors_json
        FROM audit_evidence
        WHERE audit_id = 1
        """
    ).fetchone()

    assert evidence_row is not None
    assert evidence_row[0] == "run_validated_audit"
    assert evidence_row[1].startswith(
        "def run_validated_audit"
    )
    assert evidence_row[2] == ""
    assert json.loads(evidence_row[3]) == []
    assert "focused code audit" in evidence_row[4]
    assert len(evidence_row[5]) == 64
    assert len(evidence_row[6]) == 64
    assert json.loads(evidence_row[7])["model"] == "gemma4:e4b"
    assert evidence_row[8] == "Invalid first response"
    assert json.loads(evidence_row[9]) == ["Missing sections"]
    assert evidence_row[10] == "Repair prompt"
    assert len(evidence_row[11]) == 64
    assert evidence_row[12] == "Invalid audit response"
    assert json.loads(evidence_row[13]) == [
        "EVIDENCE_LOW findings cannot use High confidence."
    ]

def test_run_selected_code_audit_saves_accepted_evidence(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"
    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    valid_response = (
        "1. Bottom line\n"
        "No actionable defect is visible.\n"
        "6. Verdict\n"
        "GO\n"
        "7. Confidence\n"
        "High"
    )

    monkeypatch.setattr(
        chat_agent,
        "run_validated_audit",
        lambda initial_prompt, model_call, available_context_names=None: ValidatedAuditResult(
            success=True,
            response=valid_response,
            errors=[],
            retry_used=False,
            first_response=valid_response,
            first_validation_errors=[],
            retry_response=None,
            retry_validation_errors=[],
            retry_prompt=None,
        ),
    )

    result = chat_agent.run_selected_code_audit(
        file_name="target.py",
        audit_target="target.py, function safe_parse, lines 1-2",
        start_line=1,
        end_line=2,
        selected_content=(
            "1: def safe_parse(raw):\n"
            "2:     return raw"
        ),
        context_content=(
            "def normalize(raw):\n"
            "    return raw"
        ),
        context_names={"normalize"},
    )

    assert "Audit saved: #1" in result

    with sqlite3.connect(test_db) as conn:
        row = conn.execute(
            """
            SELECT
                audit_results.status,
                audit_results.retry_used,
                audit_evidence.context_names_json,
                audit_evidence.first_response,
                audit_evidence.first_validation_errors_json,
                audit_evidence.retry_prompt,
                audit_evidence.retry_prompt_sha256,
                audit_evidence.retry_response,
                audit_evidence.retry_validation_errors_json
            FROM audit_results
            JOIN audit_evidence
                ON audit_evidence.audit_id = audit_results.id
            WHERE audit_results.id = 1
            """
        ).fetchone()

    assert row is not None
    assert row[0] == "accepted"
    assert row[1] == 0
    assert json.loads(row[2]) == ["normalize"]
    assert row[3] == valid_response
    assert json.loads(row[4]) == []
    assert row[5] is None
    assert row[6] is None
    assert row[7] is None
    assert json.loads(row[8]) == []


def test_rate_audit_command_saves_feedback(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    audit_id = memory_store.create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    result = handle_memory_command(
        f"/rate_audit {audit_id} PARTIALLY_USEFUL "
        "INVESTIGATED_NO_CHANGE | "
        "Caller context confirmed the behavior"
    )

    assert result == (
        f"Audit #{audit_id} rated:\n"
        "Label: PARTIALLY_USEFUL\n"
        "Outcome: INVESTIGATED_NO_CHANGE\n"
        "Note: Caller context confirmed the behavior"
    )

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT
            human_label,
            human_outcome,
            human_note,
            reviewed_at
        FROM audit_results
        WHERE id = ?
        """,
        (audit_id,),
    ).fetchone()

    conn.close()

    assert row is not None
    assert row["human_label"] == "PARTIALLY_USEFUL"
    assert row["human_outcome"] == "INVESTIGATED_NO_CHANGE"
    assert row["human_note"] == (
        "Caller context confirmed the behavior"
    )
    assert row["reviewed_at"]


def test_rate_audit_command_accepts_label_only(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    audit_id = memory_store.create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    result = handle_memory_command(
        f"/rate_audit {audit_id} LOW_VALUE"
    )

    assert result == (
        f"Audit #{audit_id} rated:\n"
        "Label: LOW_VALUE"
    )

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT
            human_label,
            human_outcome,
            human_note
        FROM audit_results
        WHERE id = ?
        """,
        (audit_id,),
    ).fetchone()

    conn.close()

    assert row["human_label"] == "LOW_VALUE"
    assert row["human_outcome"] is None
    assert row["human_note"] is None


def test_rate_audit_command_accepts_note_without_outcome(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    audit_id = memory_store.create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    result = handle_memory_command(
        f"/rate_audit {audit_id} FALSE_POSITIVE | "
        "Caller already handles the exception"
    )

    assert result == (
        f"Audit #{audit_id} rated:\n"
        "Label: FALSE_POSITIVE\n"
        "Note: Caller already handles the exception"
    )

    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        """
        SELECT
            human_label,
            human_outcome,
            human_note
        FROM audit_results
        WHERE id = ?
        """,
        (audit_id,),
    ).fetchone()

    conn.close()

    assert row["human_label"] == "FALSE_POSITIVE"
    assert row["human_outcome"] is None
    assert row["human_note"] == (
        "Caller already handles the exception"
    )


def test_rate_audit_command_rejects_missing_arguments():
    result = handle_memory_command("/rate_audit")

    assert result == (
        "Usage: /rate_audit <id> <label> "
        "[outcome] [| note]"
    )


def test_rate_audit_command_rejects_invalid_id():
    result = handle_memory_command(
        "/rate_audit abc USEFUL"
    )

    assert result == "Audit ID must be a number."


def test_rate_audit_command_rejects_unknown_audit(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    result = handle_memory_command(
        "/rate_audit 9999 USEFUL"
    )

    assert result == "Unknown audit ID: 9999"


def test_rate_audit_command_rejects_invalid_label():
    result = handle_memory_command(
        "/rate_audit 1 HELPFUL"
    )

    assert result == (
        "Invalid label: HELPFUL\n"
        "Allowed labels: FALSE_POSITIVE, LOW_VALUE, "
        "NEEDS_MORE_CONTEXT, PARTIALLY_USEFUL, USEFUL"
    )


def test_rate_audit_command_rejects_invalid_outcome():
    result = handle_memory_command(
        "/rate_audit 1 USEFUL FIXED_EVERYTHING"
    )

    assert result == (
        "Invalid outcome: FIXED_EVERYTHING\n"
        "Allowed outcomes: CODE_CHANGED, "
        "INVESTIGATED_NO_CHANGE, NO_ACTION, TEST_ADDED"
    )


def test_evaluation_stats_command_shows_human_feedback(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    audit_1 = memory_store.create_audit_result(
        file_path="first.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    audit_2 = memory_store.create_audit_result(
        file_path="second.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    memory_store.create_audit_result(
        file_path="third.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    memory_store.rate_audit(
        audit_1,
        "USEFUL",
        "TEST_ADDED",
    )

    memory_store.rate_audit(
        audit_2,
        "FALSE_POSITIVE",
        "NO_ACTION",
    )

    result = handle_memory_command("/evaluation_stats")

    assert result == (
        "Human evaluation stats:\n"
        "\n"
        "Total audits: 3\n"
        "Reviewed: 2\n"
        "Not reviewed: 1\n"
        "\n"
        "Labels:\n"
        "USEFUL: 1 (50.0%)\n"
        "PARTIALLY_USEFUL: 0 (0.0%)\n"
        "LOW_VALUE: 0 (0.0%)\n"
        "FALSE_POSITIVE: 1 (50.0%)\n"
        "NEEDS_MORE_CONTEXT: 0 (0.0%)\n"
        "\n"
        "Outcomes:\n"
        "TEST_ADDED: 1\n"
        "CODE_CHANGED: 0\n"
        "INVESTIGATED_NO_CHANGE: 0\n"
        "NO_ACTION: 1"
    )


def test_evaluation_stats_command_handles_no_reviews(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    memory_store.create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    result = handle_memory_command("/evaluation_stats")

    assert result == (
        "Human evaluation stats:\n"
        "\n"
        "Total audits: 1\n"
        "Reviewed: 0\n"
        "Not reviewed: 1\n"
        "\n"
        "No audits have been reviewed yet."
    )


def test_audit_function_passes_context_names_to_runner(
    tmp_path,
    monkeypatch,
):
    target_file = tmp_path / "example.py"
    target_file.write_text(
        "def helper():\n"
        "    return 1\n\n"
        "def target():\n"
        "    return helper()\n",
        encoding="utf-8",
    )

    prepared = chat_agent.SelectedCodeAuditPreparation(
        file_path=target_file,
        relative_path="example.py",
        selected_content="def target():\n    return helper()",
        context_content="def helper():\n    return 1",
        context_names={"helper"},
        start_line=4,
        end_line=5,
    )

    captured = {}

    monkeypatch.setattr(chat_agent, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        chat_agent,
        "find_python_function_range",
        lambda file_path, function_name: (4, 5),
    )
    monkeypatch.setattr(
        chat_agent,
        "prepare_selected_code_audit",
        lambda project_root, file_name, start_line, end_line: prepared,
    )

    def fake_run_selected_code_audit(**kwargs):
        captured.update(kwargs)
        return "audit complete"

    monkeypatch.setattr(
        chat_agent,
        "run_selected_code_audit",
        fake_run_selected_code_audit,
    )

    result = handle_memory_command(
        "/audit_function example.py target"
    )

    assert result == "audit complete"
    assert captured["context_names"] == {"helper"}
    assert captured["context_content"] == prepared.context_content



def test_export_audit_case_command_exports_fixture(monkeypatch):
    calls = []

    def fake_export_audit_case(audit_id):
        calls.append(audit_id)
        return chat_agent.Path(
            f"audit_exports/audit_case_{audit_id}.json"
        )

    monkeypatch.setattr(
        chat_agent,
        "export_audit_case",
        fake_export_audit_case,
        raising=False,
    )

    result = handle_memory_command("/export_audit_case 12")

    assert calls == [12]
    assert result == (
        "Audit case #12 exported:\n"
        "audit_exports/audit_case_12.json"
    )



def test_export_audit_case_command_handles_invalid_or_unavailable_cases(
    monkeypatch,
):
    invalid_commands = [
        "/export_audit_case",
        "/export_audit_case abc",
        "/export_audit_case 0",
        "/export_audit_case 1 extra",
    ]

    for command in invalid_commands:
        assert handle_memory_command(command) == (
            "Usage: /export_audit_case <id>"
        )

    def fake_export_audit_case(audit_id):
        if audit_id == 404:
            raise memory_store.AuditCaseNotFoundError(
                "Audit #404 does not exist."
            )

        raise memory_store.AuditEvidenceNotFoundError(
            f"Audit #{audit_id} has no reproducible evidence."
        )

    monkeypatch.setattr(
        chat_agent,
        "export_audit_case",
        fake_export_audit_case,
    )

    assert handle_memory_command(
        "/export_audit_case 404"
    ) == "Audit #404 does not exist."

    assert handle_memory_command(
        "/export_audit_case 7"
    ) == "Audit #7 has no reproducible evidence."



def test_export_audit_case_command_is_listed_in_help():
    for command in ["/help", "/unknown_command"]:
        result = handle_memory_command(command)

        assert "/export_audit_case <id>" in result
