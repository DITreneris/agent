import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from audit_validator import validate_audit_output
from memory_store import (
    AUDIT_EVIDENCE_SCHEMA_VERSION,
    VALID_HUMAN_LABELS,
    VALID_HUMAN_OUTCOMES,
    AuditCase,
    get_audit_case,
)


AUDIT_CASE_FIXTURE_SCHEMA_VERSION = 2
SUPPORTED_AUDIT_CASE_FIXTURE_SCHEMA_VERSIONS = frozenset({1, 2})


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
    fixture_schema_version: int
    status: str
    human_label: str
    human_outcome: str | None
    human_note: str | None
    reviewed_at: str | None


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
        "human_review": {
            "label": audit_case.human_label,
            "outcome": audit_case.human_outcome,
            "note": audit_case.human_note,
            "reviewed_at": audit_case.reviewed_at,
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


def _load_fixture_human_review(
    payload: dict[str, object],
    fixture_schema_version: int,
) -> dict[str, str | None]:
    if fixture_schema_version == 1:
        return {
            "label": "NOT_REVIEWED",
            "outcome": None,
            "note": None,
            "reviewed_at": None,
        }

    human_review = payload.get("human_review")

    if not isinstance(human_review, dict):
        raise AuditCaseIntegrityError(
            "Fixture schema v2 requires human_review."
        )

    label = human_review.get("label")
    outcome = human_review.get("outcome")
    note = human_review.get("note")
    reviewed_at = human_review.get("reviewed_at")

    allowed_labels = VALID_HUMAN_LABELS | {"NOT_REVIEWED"}

    if label not in allowed_labels:
        raise AuditCaseIntegrityError(
            f"Invalid human review label: {label!r}."
        )

    if outcome is not None and outcome not in VALID_HUMAN_OUTCOMES:
        raise AuditCaseIntegrityError(
            f"Invalid human review outcome: {outcome!r}."
        )

    if note is not None and not isinstance(note, str):
        raise AuditCaseIntegrityError(
            "Human review note must be text or null."
        )

    if reviewed_at is not None and not isinstance(reviewed_at, str):
        raise AuditCaseIntegrityError(
            "Human review timestamp must be text or null."
        )

    if label == "NOT_REVIEWED":
        if any(
            value is not None
            for value in (outcome, note, reviewed_at)
        ):
            raise AuditCaseIntegrityError(
                "NOT_REVIEWED cannot contain review details."
            )
    elif not reviewed_at:
        raise AuditCaseIntegrityError(
            "Reviewed audit requires reviewed_at."
        )

    return {
        "label": label,
        "outcome": outcome,
        "note": note,
        "reviewed_at": reviewed_at,
    }


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
        not in SUPPORTED_AUDIT_CASE_FIXTURE_SCHEMA_VERSIONS
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

    human_review = _load_fixture_human_review(
        payload,
        fixture_schema_version,
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
        fixture_schema_version=fixture_schema_version,
        status=payload["audit"]["status"],
        human_label=human_review["label"],
        human_outcome=human_review["outcome"],
        human_note=human_review["note"],
        reviewed_at=human_review["reviewed_at"],
    )

class AuditCaseCollectionError(ValueError):
    pass


@dataclass(frozen=True)
class AuditBatchIssue:
    fixture_path: str
    issue_type: str
    message: str


@dataclass(frozen=True)
class AuditBatchReport:
    total_cases: int
    reviewed: int
    not_reviewed: int
    validator_drift: int
    integrity_failures: int
    status_label_counts: dict[tuple[str, str], int]
    outcome_counts: dict[str, int]
    issues: list[AuditBatchIssue]


def _collect_audit_case_paths(path: Path) -> list[Path]:
    path = Path(path)

    if path.is_file():
        return [path]

    if not path.exists():
        raise AuditCaseCollectionError(
            f"Audit case path does not exist: {path}"
        )

    if not path.is_dir():
        raise AuditCaseCollectionError(
            f"Audit case path is not a file or directory: {path}"
        )

    fixture_paths = sorted(path.glob("audit_case_*.json"))

    if not fixture_paths:
        raise AuditCaseCollectionError(
            f"No audit_case_*.json fixtures found in: {path}"
        )

    return fixture_paths


def replay_audit_cases(path: Path) -> AuditBatchReport:
    fixture_paths = _collect_audit_case_paths(path)

    reviewed = 0
    not_reviewed = 0
    validator_drift = 0
    integrity_failures = 0
    status_label_counts: dict[tuple[str, str], int] = {}
    outcome_counts: dict[str, int] = {}
    issues: list[AuditBatchIssue] = []

    for fixture_path in fixture_paths:
        try:
            replay = replay_audit_case(fixture_path)
        except (
            AuditCaseIntegrityError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            OSError,
        ) as error:
            integrity_failures += 1
            issues.append(
                AuditBatchIssue(
                    fixture_path=str(fixture_path),
                    issue_type="integrity_failure",
                    message=str(error),
                )
            )
            continue

        if replay.human_label == "NOT_REVIEWED":
            not_reviewed += 1
        else:
            reviewed += 1

        status_label_key = (
            replay.status,
            replay.human_label,
        )
        status_label_counts[status_label_key] = (
            status_label_counts.get(status_label_key, 0) + 1
        )

        if replay.human_outcome is not None:
            outcome_counts[replay.human_outcome] = (
                outcome_counts.get(replay.human_outcome, 0) + 1
            )

        if not replay.matches_capture:
            validator_drift += 1
            issues.append(
                AuditBatchIssue(
                    fixture_path=str(fixture_path),
                    issue_type="validator_drift",
                    message="; ".join(replay.mismatches),
                )
            )

    return AuditBatchReport(
        total_cases=len(fixture_paths),
        reviewed=reviewed,
        not_reviewed=not_reviewed,
        validator_drift=validator_drift,
        integrity_failures=integrity_failures,
        status_label_counts=dict(
            sorted(status_label_counts.items())
        ),
        outcome_counts=dict(sorted(outcome_counts.items())),
        issues=issues,
    )

def format_audit_batch_report(
    report: AuditBatchReport,
) -> str:
    lines = [
        f"Cases: {report.total_cases}",
        f"Reviewed: {report.reviewed}",
        f"Not reviewed: {report.not_reviewed}",
        "",
    ]

    for (status, label), count in (
        report.status_label_counts.items()
    ):
        lines.append(
            f"{status.title()} + {label}: {count}"
        )

    if report.outcome_counts:
        lines.append("")

        for outcome, count in report.outcome_counts.items():
            lines.append(f"{outcome}: {count}")

    lines.extend(
        [
            "",
            f"Validator drift: {report.validator_drift}",
            f"Integrity failures: {report.integrity_failures}",
        ]
    )

    if report.issues:
        lines.append("")
        lines.append("Issues:")

        for issue in report.issues:
            lines.append(
                f"- {issue.issue_type}: "
                f"{issue.fixture_path}: {issue.message}"
            )

    return "\n".join(lines)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exported audit case utilities."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay one fixture or a fixture directory.",
    )
    replay_parser.add_argument("path", type=Path)

    args = parser.parse_args(argv)

    try:
        report = replay_audit_cases(args.path)
    except AuditCaseCollectionError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(format_audit_batch_report(report))

    if report.validator_drift or report.integrity_failures:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
