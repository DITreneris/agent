import sqlite3

import memory_store


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

    stats = memory_store.get_audit_stats()

    assert stats["total"] == 3
    assert stats["verdict_counts"] == {
        "GO": 2,
        "FIX": 1,
    }
    assert stats["retries_used"] == 2
    assert stats["most_audited_file"] == "chat_agent.py"
