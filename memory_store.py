import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, UTC

DB_PATH = "memory.db"
AUDIT_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AuditEvidence:
    audit_target: str
    selected_content: str
    context_content: str
    context_names: list[str]
    initial_prompt: str
    initial_prompt_sha256: str
    system_prompt_sha256: str
    model_config: dict[str, object]
    first_response: str
    first_validation_errors: list[str]
    retry_prompt: str | None
    retry_prompt_sha256: str | None
    retry_response: str | None
    retry_validation_errors: list[str]


VALID_HUMAN_LABELS = {
    "USEFUL",
    "PARTIALLY_USEFUL",
    "LOW_VALUE",
    "FALSE_POSITIVE",
    "NEEDS_MORE_CONTEXT",
}

VALID_HUMAN_OUTCOMES = {
    "NO_ACTION",
    "CODE_CHANGED",
    "TEST_ADDED",
    "INVESTIGATED_NO_CHANGE",
}

class AuditCaseNotFoundError(LookupError):
    pass


class AuditEvidenceNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class AuditCase:
    audit_id: int
    file_path: str
    start_line: int
    end_line: int
    status: str
    retry_used: bool
    attempt_count: int
    response: str
    schema_version: int
    evidence: AuditEvidence


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
            human_label TEXT NOT NULL DEFAULT 'NOT_REVIEWED',
            human_outcome TEXT,
            human_note TEXT,
            reviewed_at TEXT,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_evidence (
            audit_id INTEGER PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            audit_target TEXT NOT NULL,
            selected_content TEXT NOT NULL,
            context_content TEXT NOT NULL,
            context_names_json TEXT NOT NULL,
            initial_prompt TEXT NOT NULL,
            initial_prompt_sha256 TEXT NOT NULL,
            system_prompt_sha256 TEXT NOT NULL,
            retry_prompt TEXT,
            retry_prompt_sha256 TEXT,
            model_config_json TEXT NOT NULL,
            first_response TEXT NOT NULL,
            first_validation_errors_json TEXT NOT NULL,
            retry_response TEXT,
            retry_validation_errors_json TEXT NOT NULL,
            FOREIGN KEY (audit_id) REFERENCES audit_results(id)
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

        if "human_label" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN human_label TEXT NOT NULL DEFAULT 'NOT_REVIEWED'
                """
            )

        if "human_outcome" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN human_outcome TEXT
                """
            )

        if "human_note" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN human_note TEXT
                """
            )

        if "reviewed_at" not in audit_columns:
            conn.execute(
                """
                ALTER TABLE audit_results
                ADD COLUMN reviewed_at TEXT
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
    evidence: AuditEvidence | None = None,
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
        audit_id = cursor.lastrowid

        if evidence is not None:
            conn.execute(
                """
                INSERT INTO audit_evidence (
                    audit_id,
                    schema_version,
                    audit_target,
                    selected_content,
                    context_content,
                    context_names_json,
                    initial_prompt,
                    initial_prompt_sha256,
                    system_prompt_sha256,
                    retry_prompt,
                    retry_prompt_sha256,
                    model_config_json,
                    first_response,
                    first_validation_errors_json,
                    retry_response,
                    retry_validation_errors_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    audit_id,
                    AUDIT_EVIDENCE_SCHEMA_VERSION,
                    evidence.audit_target,
                    evidence.selected_content,
                    evidence.context_content,
                    json.dumps(
                        sorted(evidence.context_names),
                        ensure_ascii=False,
                    ),
                    evidence.initial_prompt,
                    evidence.initial_prompt_sha256,
                    evidence.system_prompt_sha256,
                    evidence.retry_prompt,
                    evidence.retry_prompt_sha256,
                    json.dumps(
                        evidence.model_config,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    evidence.first_response,
                    json.dumps(
                        evidence.first_validation_errors,
                        ensure_ascii=False,
                    ),
                    evidence.retry_response,
                    json.dumps(
                        evidence.retry_validation_errors,
                        ensure_ascii=False,
                    ),
                ),
            )

        conn.commit()
        return audit_id



def get_audit_case(audit_id: int) -> AuditCase:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                audit_results.id AS audit_id,
                audit_results.file_path,
                audit_results.start_line,
                audit_results.end_line,
                audit_results.status,
                audit_results.retry_used,
                audit_results.attempt_count,
                audit_results.response,
                audit_evidence.schema_version,
                audit_evidence.audit_target,
                audit_evidence.selected_content,
                audit_evidence.context_content,
                audit_evidence.context_names_json,
                audit_evidence.initial_prompt,
                audit_evidence.initial_prompt_sha256,
                audit_evidence.system_prompt_sha256,
                audit_evidence.retry_prompt,
                audit_evidence.retry_prompt_sha256,
                audit_evidence.model_config_json,
                audit_evidence.first_response,
                audit_evidence.first_validation_errors_json,
                audit_evidence.retry_response,
                audit_evidence.retry_validation_errors_json
            FROM audit_results
            LEFT JOIN audit_evidence
                ON audit_evidence.audit_id = audit_results.id
            WHERE audit_results.id = ?
            """,
            (audit_id,),
        ).fetchone()

    if row is None:
        raise AuditCaseNotFoundError(
            f"Audit #{audit_id} does not exist."
        )

    if row["schema_version"] is None:
        raise AuditEvidenceNotFoundError(
            f"Audit #{audit_id} has no reproducible evidence."
        )

    evidence = AuditEvidence(
        audit_target=row["audit_target"],
        selected_content=row["selected_content"],
        context_content=row["context_content"],
        context_names=json.loads(row["context_names_json"]),
        initial_prompt=row["initial_prompt"],
        initial_prompt_sha256=row["initial_prompt_sha256"],
        system_prompt_sha256=row["system_prompt_sha256"],
        model_config=json.loads(row["model_config_json"]),
        first_response=row["first_response"],
        first_validation_errors=json.loads(
            row["first_validation_errors_json"]
        ),
        retry_prompt=row["retry_prompt"],
        retry_prompt_sha256=row["retry_prompt_sha256"],
        retry_response=row["retry_response"],
        retry_validation_errors=json.loads(
            row["retry_validation_errors_json"]
        ),
    )

    return AuditCase(
        audit_id=row["audit_id"],
        file_path=row["file_path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        status=row["status"],
        retry_used=bool(row["retry_used"]),
        attempt_count=row["attempt_count"],
        response=row["response"],
        schema_version=row["schema_version"],
        evidence=evidence,
    )


def rate_audit(
    audit_id: int,
    human_label: str,
    human_outcome: str | None = None,
    human_note: str | None = None,
) -> bool:
    human_label = human_label.strip().upper()

    if human_label not in VALID_HUMAN_LABELS:
        raise ValueError(
            "Invalid human label. Allowed labels: "
            + ", ".join(sorted(VALID_HUMAN_LABELS))
        )

    if human_outcome is not None:
        human_outcome = human_outcome.strip().upper()

        if human_outcome not in VALID_HUMAN_OUTCOMES:
            raise ValueError(
                "Invalid human outcome. Allowed outcomes: "
                + ", ".join(sorted(VALID_HUMAN_OUTCOMES))
            )

    normalized_note = human_note.strip() if human_note else None
    reviewed_at = datetime.now(UTC).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE audit_results
            SET
                human_label = ?,
                human_outcome = ?,
                human_note = ?,
                reviewed_at = ?
            WHERE id = ?
            """,
            (
                human_label,
                human_outcome,
                normalized_note,
                reviewed_at,
                audit_id,
            ),
        )
        conn.commit()

    return cursor.rowcount > 0


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
                human_label,
                human_outcome,
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

def get_human_evaluation_stats():
    with get_connection() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM audit_results
            """
        ).fetchone()[0]

        reviewed = conn.execute(
            """
            SELECT COUNT(*)
            FROM audit_results
            WHERE human_label != 'NOT_REVIEWED'
            """
        ).fetchone()[0]

        label_rows = conn.execute(
            """
            SELECT human_label, COUNT(*) AS count
            FROM audit_results
            WHERE human_label != 'NOT_REVIEWED'
            GROUP BY human_label
            ORDER BY human_label
            """
        ).fetchall()

        outcome_rows = conn.execute(
            """
            SELECT human_outcome, COUNT(*) AS count
            FROM audit_results
            WHERE human_outcome IS NOT NULL
            GROUP BY human_outcome
            ORDER BY human_outcome
            """
        ).fetchall()

    return {
        "total": total,
        "reviewed": reviewed,
        "not_reviewed": total - reviewed,
        "label_counts": {
            row["human_label"]: row["count"]
            for row in label_rows
        },
        "outcome_counts": {
            row["human_outcome"]: row["count"]
            for row in outcome_rows
        },
    }
