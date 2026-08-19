import hashlib
import json
from pathlib import Path

from memory_store import AuditCase, get_audit_case


AUDIT_CASE_FIXTURE_SCHEMA_VERSION = 1


class AuditCaseIntegrityError(ValueError):
    pass


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_audit_case_integrity(audit_case: AuditCase) -> None:
    evidence = audit_case.evidence

    if (
        _sha256_text(evidence.initial_prompt)
        != evidence.initial_prompt_sha256
    ):
        raise AuditCaseIntegrityError(
            "Initial prompt SHA-256 mismatch."
        )

    if evidence.retry_prompt is not None:
        if (
            _sha256_text(evidence.retry_prompt)
            != evidence.retry_prompt_sha256
        ):
            raise AuditCaseIntegrityError(
                "Retry prompt SHA-256 mismatch."
            )


def build_audit_case_fixture(
    audit_case: AuditCase,
) -> dict[str, object]:
    verify_audit_case_integrity(audit_case)
    evidence = audit_case.evidence

    retry_prompt = None
    if evidence.retry_prompt is not None:
        retry_prompt = {
            "content": evidence.retry_prompt,
            "sha256": evidence.retry_prompt_sha256,
        }

    retry_attempt = None
    if audit_case.retry_used:
        retry_attempt = {
            "response": evidence.retry_response,
            "validation_errors": list(
                evidence.retry_validation_errors
            ),
        }

    return {
        "fixture_schema_version": (
            AUDIT_CASE_FIXTURE_SCHEMA_VERSION
        ),
        "evidence_schema_version": audit_case.schema_version,
        "audit": {
            "id": audit_case.audit_id,
            "file_path": audit_case.file_path,
            "start_line": audit_case.start_line,
            "end_line": audit_case.end_line,
            "status": audit_case.status,
            "retry_used": audit_case.retry_used,
            "attempt_count": audit_case.attempt_count,
            "response": audit_case.response,
        },
        "input": {
            "audit_target": evidence.audit_target,
            "selected_content": evidence.selected_content,
            "context_content": evidence.context_content,
            "context_names": sorted(evidence.context_names),
        },
        "prompts": {
            "system_sha256": evidence.system_prompt_sha256,
            "initial": {
                "content": evidence.initial_prompt,
                "sha256": evidence.initial_prompt_sha256,
            },
            "retry": retry_prompt,
        },
        "model_config": dict(evidence.model_config),
        "attempts": {
            "first": {
                "response": evidence.first_response,
                "validation_errors": list(
                    evidence.first_validation_errors
                ),
            },
            "retry": retry_attempt,
        },
    }


def serialize_audit_case(audit_case: AuditCase) -> str:
    fixture = build_audit_case_fixture(audit_case)

    return (
        json.dumps(
            fixture,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )



def export_audit_case(
    audit_id: int,
    output_dir: Path = Path("audit_exports"),
) -> Path:
    stored_case = get_audit_case(audit_id)
    serialized_case = serialize_audit_case(stored_case)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"audit_case_{audit_id}.json"
    output_path.write_text(
        serialized_case,
        encoding="utf-8",
    )

    return output_path
