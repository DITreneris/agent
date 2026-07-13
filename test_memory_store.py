import sqlite3
import pytest
import memory_store

from memory_store import (
    VALID_HUMAN_LABELS,
    VALID_HUMAN_OUTCOMES,
    create_audit_result,
    get_connection,
    init_memory_db,
    rate_audit,
    get_human_evaluation_stats,
)


def test_create_audit_result(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))

    memory_store.init_memory_db()

    response = """1. Bottom line
Audit is valid.

2. Direct critique
No blocking issue.

3. Better option
No change needed.

4. Next steps
Keep testing.

5. Top 3 pitfalls
1. Pitfall one.
2. Pitfall two.
3. Pitfall three.

6. Verdict
GO_WITH_NOTES

7. Confidence
High
"""

    audit_id = memory_store.create_audit_result(
        file_path="chat_agent.py",
        start_line=339,
        end_line=397,
        response=response,
        retry_used=True,
    )

    assert audit_id == 1

    conn = sqlite3.connect(test_db)
    row = conn.execute(
        """
        SELECT file_path, start_line, end_line, verdict, confidence, retry_used, response
        FROM audit_results
        WHERE id = ?
        """,
        (audit_id,),
    ).fetchone()

    assert row is not None
    assert row[0] == "chat_agent.py"
    assert row[1] == 339
    assert row[2] == 397
    assert row[3] == "GO_WITH_NOTES"
    assert row[4] == "High"
    assert row[5] == 1
    assert "1. Bottom line" in row[6]

def test_get_recent_audit_results_returns_latest_first(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))

    memory_store.init_memory_db()

    response_go = """1. Bottom line
Audit is valid.

2. Direct critique
No blocking issue.

3. Better option
No change needed.

4. Next steps
Keep testing.

5. Top 3 pitfalls
1. Pitfall one.
2. Pitfall two.
3. Pitfall three.

6. Verdict
GO

7. Confidence
High
"""

    response_fix = """1. Bottom line
Audit found an issue.

2. Direct critique
There is a real issue.

3. Better option
Fix the issue.

4. Next steps
Apply the fix.

5. Top 3 pitfalls
1. Pitfall one.
2. Pitfall two.
3. Pitfall three.

6. Verdict
FIX

7. Confidence
Medium
"""

    first_id = memory_store.create_audit_result(
        file_path="chat_agent.py",
        start_line=10,
        end_line=20,
        response=response_go,
        retry_used=False,
    )

    second_id = memory_store.create_audit_result(
        file_path="memory_store.py",
        start_line=30,
        end_line=40,
        response=response_fix,
        retry_used=True,
    )

    rows = memory_store.get_recent_audit_results(limit=10)

    assert len(rows) == 2
    assert rows[0]["id"] == second_id
    assert rows[0]["file_path"] == "memory_store.py"
    assert rows[0]["verdict"] == "FIX"
    assert rows[0]["confidence"] == "Medium"
    assert rows[0]["retry_used"] == 1

    assert rows[1]["id"] == first_id
    assert rows[1]["file_path"] == "chat_agent.py"
    assert rows[1]["verdict"] == "GO"
    assert rows[1]["confidence"] == "High"
    assert rows[1]["retry_used"] == 0

def test_get_audit_stats_empty_database(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))

    memory_store.init_memory_db()

    stats = memory_store.get_audit_stats()

    assert stats["total"] == 0
    assert stats["status_counts"] == {}
    assert stats["verdict_counts"] == {}
    assert stats["retries_used"] == 0
    assert stats["most_audited_file"] is None

def test_get_audit_stats_counts_saved_audits(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))

    memory_store.init_memory_db()

    response_go = """1. Bottom line
Audit is valid.

2. Direct critique
No blocking issue.

3. Better option
No change needed.

4. Next steps
Keep testing.

5. Top 3 pitfalls
1. Pitfall one.
2. Pitfall two.
3. Pitfall three.

6. Verdict
GO

7. Confidence
High
"""

    response_fix = """1. Bottom line
Audit found an issue.

2. Direct critique
There is a real issue.

3. Better option
Fix the issue.

4. Next steps
Apply the fix.

5. Top 3 pitfalls
1. Pitfall one.
2. Pitfall two.
3. Pitfall three.

6. Verdict
FIX

7. Confidence
Medium
"""

    memory_store.create_audit_result(
        file_path="chat_agent.py",
        start_line=10,
        end_line=20,
        response=response_go,
        retry_used=False,
    )

    memory_store.create_audit_result(
        file_path="chat_agent.py",
        start_line=30,
        end_line=40,
        response=response_go,
        retry_used=True,
    )

    memory_store.create_audit_result(
        file_path="memory_store.py",
        start_line=50,
        end_line=60,
        response=response_fix,
        retry_used=True,
    )

    memory_store.create_audit_result(
        file_path="orchestrator.py",
        start_line=43,
        end_line=46,
        response="Invalid audit response",
        retry_used=True,
        status="rejected",
        validation_errors=[
            "EVIDENCE_LOW findings cannot use High confidence."
        ],
    )

    stats = memory_store.get_audit_stats()

    assert stats["total"] == 4
    assert stats["status_counts"] == {
        "accepted": 3,
        "rejected": 1,
    }
    assert stats["verdict_counts"] == {
        "GO": 2,
        "FIX": 1,
    }
    assert stats["retries_used"] == 3
    assert stats["most_audited_file"] == "chat_agent.py"

def test_create_rejected_audit_result(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    audit_id = memory_store.create_audit_result(
        file_path="orchestrator.py",
        start_line=43,
        end_line=46,
        response="Invalid audit response",
        retry_used=True,
        status="rejected",
        validation_errors=[
            "EVIDENCE_LOW findings cannot use High confidence."
        ],
    )

    conn = sqlite3.connect(test_db)
    row = conn.execute(
        """
        SELECT
            status,
            verdict,
            confidence,
            retry_used,
            attempt_count,
            validation_errors,
            response
        FROM audit_results
        WHERE id = ?
        """,
        (audit_id,),
    ).fetchone()

    assert row is not None
    assert row[0] == "rejected"
    assert row[1] == ""
    assert row[2] == ""
    assert row[3] == 1
    assert row[4] == 2
    assert row[5] == "EVIDENCE_LOW findings cannot use High confidence."
    assert row[6] == "Invalid audit response"

def test_create_audit_result_rejects_invalid_status(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory.db"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    with pytest.raises(
        ValueError,
        match="status must be 'accepted' or 'rejected'",
    ):
        memory_store.create_audit_result(
            file_path="chat_agent.py",
            start_line=1,
            end_line=5,
            response="Invalid response",
            retry_used=False,
            status="unknown",
        )


def test_rate_audit_saves_human_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    audit_id = create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    updated = rate_audit(
        audit_id,
        "useful",
        "test_added",
        "  Added regression coverage.  ",
    )

    assert updated is True

    with get_connection() as conn:
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

    assert row["human_label"] == "USEFUL"
    assert row["human_outcome"] == "TEST_ADDED"
    assert row["human_note"] == "Added regression coverage."
    assert row["reviewed_at"]


def test_rate_audit_allows_optional_outcome_and_note(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    audit_id = create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    updated = rate_audit(
        audit_id,
        "LOW_VALUE",
    )

    assert updated is True

    with get_connection() as conn:
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

    assert row["human_label"] == "LOW_VALUE"
    assert row["human_outcome"] is None
    assert row["human_note"] is None
    assert row["reviewed_at"]


def test_rate_audit_returns_false_for_unknown_audit(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    assert rate_audit(9999, "USEFUL") is False


def test_rate_audit_rejects_invalid_label(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    try:
        rate_audit(1, "HELPFUL")
    except ValueError as error:
        assert "Invalid human label" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_rate_audit_rejects_invalid_outcome(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    try:
        rate_audit(
            1,
            "USEFUL",
            "FIXED_EVERYTHING",
        )
    except ValueError as error:
        assert "Invalid human outcome" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_rate_audit_can_replace_existing_feedback(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    audit_id = create_audit_result(
        file_path="example.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    rate_audit(
        audit_id,
        "PARTIALLY_USEFUL",
        "INVESTIGATED_NO_CHANGE",
        "Initial review",
    )

    rate_audit(
        audit_id,
        "FALSE_POSITIVE",
        "NO_ACTION",
        "Caller handles the exception",
    )

    with get_connection() as conn:
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

    assert row["human_label"] == "FALSE_POSITIVE"
    assert row["human_outcome"] == "NO_ACTION"
    assert row["human_note"] == "Caller handles the exception"
    assert row["reviewed_at"]


def test_get_human_evaluation_stats_counts_feedback(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    audit_1 = create_audit_result(
        file_path="first.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    audit_2 = create_audit_result(
        file_path="second.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    create_audit_result(
        file_path="third.py",
        start_line=1,
        end_line=10,
        response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_used=False,
    )

    rate_audit(
        audit_1,
        "USEFUL",
        "TEST_ADDED",
    )

    rate_audit(
        audit_2,
        "FALSE_POSITIVE",
        "NO_ACTION",
    )

    stats = get_human_evaluation_stats()

    assert stats["total"] == 3
    assert stats["reviewed"] == 2
    assert stats["not_reviewed"] == 1

    assert stats["label_counts"] == {
        "FALSE_POSITIVE": 1,
        "USEFUL": 1,
    }

    assert stats["outcome_counts"] == {
        "NO_ACTION": 1,
        "TEST_ADDED": 1,
    }


def test_get_human_evaluation_stats_handles_empty_database(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setattr("memory_store.DB_PATH", str(db_path))

    init_memory_db()

    stats = get_human_evaluation_stats()

    assert stats == {
        "total": 0,
        "reviewed": 0,
        "not_reviewed": 0,
        "label_counts": {},
        "outcome_counts": {},
    }
