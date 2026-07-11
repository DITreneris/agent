import sqlite3
from datetime import datetime, UTC

DB_PATH = "memory.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_memory_db():
    with get_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            memory_type TEXT DEFAULT 'fact',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'accepted',
            verdict TEXT NOT NULL DEFAULT '',
            confidence TEXT NOT NULL DEFAULT '',
            retry_used INTEGER NOT NULL DEFAULT 0,
            attempt_count INTEGER NOT NULL DEFAULT 1,
            validation_errors TEXT NOT NULL DEFAULT '',
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        audit_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(audit_results)"
            ).fetchall()
        }

        if "status" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN status TEXT NOT NULL DEFAULT 'accepted'
                """
            )

        if "attempt_count" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1
                """
            )

        if "validation_errors" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN validation_errors TEXT NOT NULL DEFAULT ''
                """
            )

        conn.execute(
            """
            UPDATE audit_results
            SET attempt_count = CASE
                WHEN retry_used = 1 THEN 2
                ELSE 1
            END
            """
        )

        conn.commit()


def create_memory(content: str, memory_type: str = "fact") -> int:
    now = datetime.now(UTC).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO memories (content, memory_type, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (content.strip(), memory_type, now, now)
        )
        conn.commit()
        return cursor.lastrowid


def read_memories():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, content, memory_type, created_at, updated_at
            FROM memories
            ORDER BY id ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]

def get_memory(memory_id: int):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, content, memory_type, created_at, updated_at
            FROM memories
            WHERE id = ?
            """,
            (memory_id,)
        ).fetchone()

    return dict(row) if row else None


def update_memory(memory_id: int, new_content: str) -> bool:
    now = datetime.now(UTC).isoformat()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id FROM memories
            WHERE id = ?
            """,
            (memory_id,)
        ).fetchone()

        if not row:
            return False

        conn.execute(
            """
            UPDATE memories
            SET content = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_content.strip(), now, memory_id)
        )
        conn.commit()

    return True


def delete_memory(memory_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM memories
            WHERE id = ?
            """,
            (memory_id,)
        )
        conn.commit()

    return cursor.rowcount > 0


def clear_memories() -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM memories")
        conn.commit()

    return cursor.rowcount

def format_memories_for_user() -> str:
    memories = read_memories()

    if not memories:
        return "Memory is empty."

    lines = ["Stored memory:"]

    for memory in memories:
        lines.append(
            f"{memory['id']}. [{memory['memory_type']}] {memory['content']}"
        )

    return "\n".join(lines)


def format_memories_for_prompt() -> str:
    memories = read_memories()

    if not memories:
        return "No stored memories."

    lines = ["Stored memories:"]

    for memory in memories:
        lines.append(
            f"- [{memory['id']}] ({memory['memory_type']}) {memory['content']}"
        )

    return "\n".join(lines)

def extract_audit_field(
    response: str,
    heading: str,
    next_heading: str | None = None,
) -> str:
    start = response.find(heading)

    if start == -1:
        return ""

    start += len(heading)

    if next_heading:
        end = response.find(next_heading, start)
        if end == -1:
            end = len(response)
    else:
        end = len(response)

    return response[start:end].strip()


def extract_audit_verdict(response: str) -> str:
    return extract_audit_field(
        response,
        "6. Verdict",
        "7. Confidence",
    )


def extract_audit_confidence(response: str) -> str:
    return extract_audit_field(
        response,
        "7. Confidence",
        None,
    )


def create_audit_result(
    file_path: str,
    start_line: int,
    end_line: int,
    response: str,
    retry_used: bool,
    status: str = "accepted",
    validation_errors: list[str] | None = None,
) -> int:
    now = datetime.now(UTC).isoformat()

    verdict = extract_audit_verdict(response)
    confidence = extract_audit_confidence(response)

    if status not in {"accepted", "rejected"}:
        raise ValueError("status must be 'accepted' or 'rejected'")

    attempt_count = 2 if retry_used else 1
    validation_errors_text = "\n".join(validation_errors or [])

    if status == "rejected":
        verdict = ""
        confidence = ""

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_results (
                file_path,
                start_line,
                end_line,
                status,
                verdict,
                confidence,
                retry_used,
                attempt_count,
                validation_errors,
                response,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_path,
                start_line,
                end_line,
                status,
                verdict,
                confidence,
                int(retry_used),
                attempt_count,
                validation_errors_text,
                response,
                now,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_recent_audit_results(limit: int = 10):
    if limit < 1:
        limit = 10

    if limit > 50:
        limit = 50

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                id,
                file_path,
                start_line,
                end_line,
                status,
                verdict,
                confidence,
                retry_used,
                attempt_count,
                validation_errors,
                created_at
            FROM audit_results
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()


def get_audit_stats():
    with get_connection() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM audit_results
            """
        ).fetchone()["count"]

        status_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM audit_results
            GROUP BY status
            ORDER BY status ASC
            """
        ).fetchall()

        verdict_rows = conn.execute(
            """
            SELECT verdict, COUNT(*) AS count
            FROM audit_results
            GROUP BY verdict
            ORDER BY count DESC, verdict ASC
            """
        ).fetchall()

        retries_used = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM audit_results
            WHERE retry_used = 1
            """
        ).fetchone()["count"]

        most_audited_row = conn.execute(
            """
            SELECT file_path, COUNT(*) AS count
            FROM audit_results
            GROUP BY file_path
            ORDER BY count DESC, file_path ASC
            LIMIT 1
            """
        ).fetchone()

    return {
        "total": total,
        "status_counts": {
            row["status"]: row["count"]
            for row in status_rows
        },
        "verdict_counts": {
            row["verdict"]: row["count"]
            for row in verdict_rows
            if row["verdict"]
        },
        "retries_used": retries_used,
        "most_audited_file": (
            most_audited_row["file_path"]
            if most_audited_row
            else None
        ),
    }
