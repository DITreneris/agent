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
            verdict TEXT NOT NULL,
            confidence TEXT NOT NULL,
            retry_used INTEGER NOT NULL DEFAULT 0,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

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
) -> int:
    now = datetime.now(UTC).isoformat()    

    verdict = extract_audit_verdict(response)
    confidence = extract_audit_confidence(response)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_results (
                file_path,
                start_line,
                end_line,
                verdict,
                confidence,
                retry_used,
                response,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_path,
                start_line,
                end_line,
                verdict,
                confidence,
                int(retry_used),
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
                verdict,
                confidence,
                retry_used,
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
        "verdict_counts": {
            row["verdict"]: row["count"]
            for row in verdict_rows
        },
        "retries_used": retries_used,
        "most_audited_file": (
            most_audited_row["file_path"]
            if most_audited_row
            else None
        ),
    }
