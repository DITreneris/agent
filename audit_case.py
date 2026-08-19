import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from audit_validator import validate_audit_output
from memory_store import (
    AUDIT_EVIDENCE_SCHEMA_VERSION,
    AuditCase,
    get_audit_case,
)


AUDIT_CASE_FIXTURE_SCHEMA_VERSION = 1


class AuditCaseIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class AuditReplayResult:
    matches_capture: bool
    first_valid: bool
    first_errors: list[str]
    retry_valid: bool | None
    retry_errors: list[str] | None
    mismatches: list[str]


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



def _verify_fixture_prompt(
    prompt: dict[str, object],
    label: str,
) -> None:
    content = prompt.get("content")
    expected_hash = prompt.get("sha256")

    if (
        not isinstance(content, str)
        or not isinstance(expected_hash, str)
        or _sha256_text(content) != expected_hash
    ):
        raise AuditCaseIntegrityError(
            f"{label} prompt SHA-256 mismatch."
        )


def replay_audit_case(fixture_path: Path) -> AuditReplayResult:
    fixture_path = Path(fixture_path)
    payload = json.loads(
        fixture_path.read_text(encoding="utf-8")
    )

    fixture_schema_version = payload.get(
        "fixture_schema_version"
    )
    if (
        fixture_schema_version
        != AUDIT_CASE_FIXTURE_SCHEMA_VERSION
    ):
        raise AuditCaseIntegrityError(
            "Unsupported audit case fixture schema version: "
            f"{fixture_schema_version}"
        )

    evidence_schema_version = payload.get(
        "evidence_schema_version"
    )
    if (
        evidence_schema_version
        != AUDIT_EVIDENCE_SCHEMA_VERSION
    ):
        raise AuditCaseIntegrityError(
            "Unsupported audit evidence schema version: "
            f"{evidence_schema_version}"
        )

    prompts = payload["prompts"]
    _verify_fixture_prompt(
        prompts["initial"],
        "Initial",
    )

    retry_prompt = prompts["retry"]
    if retry_prompt is not None:
        _verify_fixture_prompt(
            retry_prompt,
            "Retry",
        )

    system_prompt_hash = prompts["system_sha256"]
    if (
        not isinstance(system_prompt_hash, str)
        or len(system_prompt_hash) != 64
        or any(
            character not in "0123456789abcdef"
            for character in system_prompt_hash.lower()
        )
    ):
        raise AuditCaseIntegrityError(
            "System prompt SHA-256 is invalid."
        )

    context_names = set(
        payload["input"]["context_names"]
    )
    attempts = payload["attempts"]

    first_attempt = attempts["first"]
    first_validation = validate_audit_output(
        first_attempt["response"],
        available_context_names=context_names,
    )
    captured_first_errors = list(
        first_attempt["validation_errors"]
    )

    mismatches: list[str] = []

    if first_validation.errors != captured_first_errors:
        mismatches.append(
            "First attempt validation errors changed."
        )

    retry_attempt = attempts["retry"]
    retry_valid = None
    retry_errors = None

    if retry_attempt is not None:
        retry_validation = validate_audit_output(
            retry_attempt["response"],
            available_context_names=context_names,
        )
        retry_valid = retry_validation.valid
        retry_errors = list(retry_validation.errors)
        captured_retry_errors = list(
            retry_attempt["validation_errors"]
        )

        if retry_errors != captured_retry_errors:
            mismatches.append(
                "Retry attempt validation errors changed."
            )

    return AuditReplayResult(
        matches_capture=not mismatches,
        first_valid=first_validation.valid,
        first_errors=list(first_validation.errors),
        retry_valid=retry_valid,
        retry_errors=retry_errors,
        mismatches=mismatches,
    )
