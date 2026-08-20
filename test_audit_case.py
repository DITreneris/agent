import hashlib
import json

import pytest

import audit_case
import memory_store

from audit_case import serialize_audit_case
from memory_store import AuditCase, AuditEvidence


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_serialize_audit_case_is_deterministic_and_keeps_both_attempts():
    initial_prompt = "Audit this selected code."
    retry_prompt = "Repair the rejected audit."

    evidence = AuditEvidence(
        audit_target="target.py, function normalize, lines 3-4",
        selected_content="3: value = normalize(raw)",
        context_content=(
            "def normalize(value):\n"
            "    return value.strip()"
        ),
        context_names=["zeta_helper", "normalize"],
        initial_prompt=initial_prompt,
        initial_prompt_sha256=sha256_text(initial_prompt),
        system_prompt_sha256="a" * 64,
        model_config={
            "temperature": 0.1,
            "model": "gemma4:e4b",
            "seed": 11,
        },
        first_response="Invalid first response",
        first_validation_errors=["Missing section 6"],
        retry_prompt=retry_prompt,
        retry_prompt_sha256=sha256_text(retry_prompt),
        retry_response=(
            "6. Verdict\nGO_WITH_NOTES\n"
            "7. Confidence\nMedium"
        ),
        retry_validation_errors=[],
    )
    audit_case = AuditCase(
        audit_id=42,
        file_path="target.py",
        start_line=3,
        end_line=4,
        status="accepted",
        retry_used=True,
        attempt_count=2,
        response=evidence.retry_response,
        schema_version=1,
        evidence=evidence,
    )

    first_json = serialize_audit_case(audit_case)
    second_json = serialize_audit_case(audit_case)

    assert first_json == second_json
    assert first_json.endswith("\n")

    payload = json.loads(first_json)

    assert payload["fixture_schema_version"] == 2
    assert payload["evidence_schema_version"] == 1
    assert payload["human_review"] == {
        "label": "NOT_REVIEWED",
        "outcome": None,
        "note": None,
        "reviewed_at": None,
    }
    assert payload["audit"] == {
        "attempt_count": 2,
        "end_line": 4,
        "file_path": "target.py",
        "id": 42,
        "response": evidence.retry_response,
        "retry_used": True,
        "start_line": 3,
        "status": "accepted",
    }
    assert payload["input"]["selected_content"] == (
        "3: value = normalize(raw)"
    )
    assert payload["input"]["context_names"] == [
        "normalize",
        "zeta_helper",
    ]
    assert payload["model_config"]["model"] == "gemma4:e4b"
    assert payload["prompts"]["initial"] == {
        "content": initial_prompt,
        "sha256": sha256_text(initial_prompt),
    }
    assert payload["prompts"]["retry"] == {
        "content": retry_prompt,
        "sha256": sha256_text(retry_prompt),
    }
    assert payload["attempts"]["first"] == {
        "response": "Invalid first response",
        "validation_errors": ["Missing section 6"],
    }
    assert payload["attempts"]["retry"] == {
        "response": evidence.retry_response,
        "validation_errors": [],
    }

    assert first_json == (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )



@pytest.mark.parametrize(
    ("initial_hash", "retry_hash", "expected_message"),
    [
        (
            "0" * 64,
            sha256_text("Retry prompt"),
            "Initial prompt SHA-256 mismatch.",
        ),
        (
            sha256_text("Initial prompt"),
            "0" * 64,
            "Retry prompt SHA-256 mismatch.",
        ),
    ],
)
def test_serialize_audit_case_rejects_prompt_hash_mismatch(
    initial_hash,
    retry_hash,
    expected_message,
):
    evidence = AuditEvidence(
        audit_target="target.py, lines 1-2",
        selected_content="1: value = normalize(raw)",
        context_content="",
        context_names=[],
        initial_prompt="Initial prompt",
        initial_prompt_sha256=initial_hash,
        system_prompt_sha256="a" * 64,
        model_config={"model": "gemma4:e4b"},
        first_response="Invalid first response",
        first_validation_errors=["Missing section 6"],
        retry_prompt="Retry prompt",
        retry_prompt_sha256=retry_hash,
        retry_response=(
            "6. Verdict\nGO\n"
            "7. Confidence\nHigh"
        ),
        retry_validation_errors=[],
    )
    stored_case = AuditCase(
        audit_id=7,
        file_path="target.py",
        start_line=1,
        end_line=2,
        status="accepted",
        retry_used=True,
        attempt_count=2,
        response=evidence.retry_response,
        schema_version=1,
        evidence=evidence,
    )

    with pytest.raises(
        audit_case.AuditCaseIntegrityError,
        match=expected_message,
    ):
        serialize_audit_case(stored_case)



def test_export_audit_case_writes_replayable_json(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"
    export_dir = tmp_path / "exports"

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    initial_prompt = "Audit exported code."
    response = (
        "6. Verdict\nGO\n"
        "7. Confidence\nHigh"
    )
    evidence = AuditEvidence(
        audit_target="target.py, lines 1-2",
        selected_content="1: value = normalize(raw)",
        context_content="",
        context_names=["normalize"],
        initial_prompt=initial_prompt,
        initial_prompt_sha256=sha256_text(initial_prompt),
        system_prompt_sha256="a" * 64,
        model_config={
            "model": "gemma4:e4b",
            "temperature": 0.1,
            "seed": 11,
        },
        first_response=response,
        first_validation_errors=[],
        retry_prompt=None,
        retry_prompt_sha256=None,
        retry_response=None,
        retry_validation_errors=[],
    )
    audit_id = memory_store.create_audit_result(
        file_path="target.py",
        start_line=1,
        end_line=2,
        response=response,
        retry_used=False,
        evidence=evidence,
    )

    exported_path = audit_case.export_audit_case(
        audit_id,
        output_dir=export_dir,
    )

    assert exported_path == (
        export_dir / f"audit_case_{audit_id}.json"
    )
    assert exported_path.is_file()
    assert exported_path.read_text(encoding="utf-8") == (
        serialize_audit_case(
            memory_store.get_audit_case(audit_id)
        )
    )

    payload = json.loads(
        exported_path.read_text(encoding="utf-8")
    )
    assert payload["audit"]["id"] == audit_id
    assert payload["input"]["selected_content"] == (
        "1: value = normalize(raw)"
    )



def test_replay_audit_case_without_database_model_or_source(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_memory.db"
    source_path = tmp_path / "deleted_target.py"
    source_path.write_text(
        "value = normalize(raw)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(memory_store, "DB_PATH", str(test_db))
    memory_store.init_memory_db()

    initial_prompt = "Audit the captured selected code."
    retry_prompt = "Repair the captured audit."
    first_response = "Invalid first response"
    first_errors = [
        "Response must start with '1. Bottom line'.",
        "Missing section: '1. Bottom line'.",
        "Missing section: '2. Direct critique'.",
        "Missing section: '3. Better option'.",
        "Missing section: '4. Next steps'.",
        "Missing section: '5. Top 3 pitfalls'.",
        "Missing section: '6. Verdict'.",
        "Missing section: '7. Confidence'.",
        "Invalid Verdict value: ''.",
        "Invalid Confidence value: ''.",
    ]
    retry_response = """1. Bottom line
No actionable defect is visible.

2. Direct critique
Classification: FALSE_POSITIVE_CANDIDATE
Evidence: EVIDENCE_HIGH
Why: The captured code and context show the current behavior.
Missing context: none

3. Better option
No code change is needed.

4. Next steps
Recommended action: NO_CHANGE
Test status: NO_TEST_NEEDED
Reason: The captured behavior is already explicit.

5. Top 3 pitfalls
1. Changing behavior without evidence.
2. Ignoring captured context.
3. Treating a hypothetical risk as a defect.

6. Verdict
GO

7. Confidence
High"""

    evidence = AuditEvidence(
        audit_target=(
            "deleted_target.py, function normalize, lines 1-1"
        ),
        selected_content="1: value = normalize(raw)",
        context_content=(
            "def normalize(value):\n"
            "    return value.strip()"
        ),
        context_names=["normalize"],
        initial_prompt=initial_prompt,
        initial_prompt_sha256=sha256_text(initial_prompt),
        system_prompt_sha256="a" * 64,
        model_config={
            "model": "gemma4:e4b",
            "temperature": 0.1,
            "seed": 11,
        },
        first_response=first_response,
        first_validation_errors=first_errors,
        retry_prompt=retry_prompt,
        retry_prompt_sha256=sha256_text(retry_prompt),
        retry_response=retry_response,
        retry_validation_errors=[],
    )
    audit_id = memory_store.create_audit_result(
        file_path=str(source_path),
        start_line=1,
        end_line=1,
        response=retry_response,
        retry_used=True,
        evidence=evidence,
    )
    exported_path = audit_case.export_audit_case(
        audit_id,
        output_dir=tmp_path / "exports",
    )

    source_path.unlink()
    test_db.unlink()

    def fail_if_database_is_used(*args, **kwargs):
        raise AssertionError(
            "Replay must not read the audit database."
        )

    monkeypatch.setattr(
        audit_case,
        "get_audit_case",
        fail_if_database_is_used,
    )

    replay = audit_case.replay_audit_case(exported_path)

    assert source_path.exists() is False
    assert test_db.exists() is False
    assert replay.matches_capture is True
    assert replay.first_valid is False
    assert replay.first_errors == first_errors
    assert replay.retry_valid is True
    assert replay.retry_errors == []
    assert replay.mismatches == []

def test_replay_schema_v1_defaults_to_not_reviewed(tmp_path):
    initial_prompt = "Audit captured code."
    valid_response = """1. Bottom line
No actionable defect is visible.

2. Direct critique
Classification: FALSE_POSITIVE_CANDIDATE
Evidence: EVIDENCE_HIGH
Why: The captured code supports the current behavior.
Missing context: none

3. Better option
No code change is needed.

4. Next steps
Recommended action: NO_CHANGE
Test status: NO_TEST_NEEDED
Reason: The behavior is already explicit.

5. Top 3 pitfalls
1. Changing intentional behavior.
2. Ignoring captured evidence.
3. Inventing missing requirements.

6. Verdict
GO

7. Confidence
High"""

    payload = {
        "fixture_schema_version": 1,
        "evidence_schema_version": 1,
        "audit": {
            "status": "accepted",
        },
        "input": {
            "context_names": [],
        },
        "prompts": {
            "system_sha256": "a" * 64,
            "initial": {
                "content": initial_prompt,
                "sha256": sha256_text(initial_prompt),
            },
            "retry": None,
        },
        "attempts": {
            "first": {
                "response": valid_response,
                "validation_errors": [],
            },
            "retry": None,
        },
    }

    fixture_path = tmp_path / "audit_case_v1.json"
    fixture_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    replay = audit_case.replay_audit_case(fixture_path)

    assert replay.matches_capture is True
    assert replay.fixture_schema_version == 1
    assert replay.status == "accepted"
    assert replay.human_label == "NOT_REVIEWED"
    assert replay.human_outcome is None
    assert replay.human_note is None
    assert replay.reviewed_at is None

@pytest.mark.parametrize(
    (
        "human_label",
        "human_outcome",
        "human_note",
    ),
    [
        (
            "FALSE_POSITIVE",
            "INVESTIGATED_NO_CHANGE",
            "Existing contract proves the behavior is intentional.",
        ),
        (
            "USEFUL",
            "CODE_CHANGED",
            "The audit identified a real defect.",
        ),
    ],
)
def test_schema_v2_preserves_reviewed_human_feedback(
    tmp_path,
    human_label,
    human_outcome,
    human_note,
):
    initial_prompt = "Audit reviewed code."
    reviewed_at = "2026-08-20T10:00:00+00:00"

    valid_response = """1. Bottom line
No unsupported claim is present.

2. Direct critique
Classification: FALSE_POSITIVE_CANDIDATE
Evidence: EVIDENCE_HIGH
Why: The captured code supports the conclusion.
Missing context: none

3. Better option
Keep the evidence-backed conclusion.

4. Next steps
Recommended action: NO_CHANGE
Test status: NO_TEST_NEEDED
Reason: The relevant behavior is explicit.

5. Top 3 pitfalls
1. Ignoring captured evidence.
2. Inventing missing requirements.
3. Changing intentional behavior.

6. Verdict
GO

7. Confidence
High"""

    evidence = AuditEvidence(
        audit_target="target.py, function normalize, lines 1-2",
        selected_content="1: value = normalize(raw)",
        context_content="",
        context_names=[],
        initial_prompt=initial_prompt,
        initial_prompt_sha256=sha256_text(initial_prompt),
        system_prompt_sha256="a" * 64,
        model_config={
            "model": "gemma4:e4b",
            "temperature": 0.1,
            "seed": 11,
        },
        first_response=valid_response,
        first_validation_errors=[],
        retry_prompt=None,
        retry_prompt_sha256=None,
        retry_response=None,
        retry_validation_errors=[],
    )

    stored_case = AuditCase(
        audit_id=42,
        file_path="target.py",
        start_line=1,
        end_line=2,
        status="accepted",
        retry_used=False,
        attempt_count=1,
        response=valid_response,
        schema_version=1,
        evidence=evidence,
        human_label=human_label,
        human_outcome=human_outcome,
        human_note=human_note,
        reviewed_at=reviewed_at,
    )

    serialized = serialize_audit_case(stored_case)
    payload = json.loads(serialized)

    assert payload["fixture_schema_version"] == 2
    assert payload["human_review"] == {
        "label": human_label,
        "outcome": human_outcome,
        "note": human_note,
        "reviewed_at": reviewed_at,
    }

    fixture_path = tmp_path / f"{human_label.lower()}.json"
    fixture_path.write_text(serialized, encoding="utf-8")

    replay = audit_case.replay_audit_case(fixture_path)

    assert replay.matches_capture is True
    assert replay.fixture_schema_version == 2
    assert replay.status == "accepted"
    assert replay.human_label == human_label
    assert replay.human_outcome == human_outcome
    assert replay.human_note == human_note
    assert replay.reviewed_at == reviewed_at

BATCH_VALID_RESPONSE = """1. Bottom line
No actionable defect is visible.

2. Direct critique
Classification: FALSE_POSITIVE_CANDIDATE
Evidence: EVIDENCE_HIGH
Why: The captured code supports the conclusion.
Missing context: none

3. Better option
Keep the evidence-backed behavior.

4. Next steps
Recommended action: NO_CHANGE
Test status: NO_TEST_NEEDED
Reason: The relevant behavior is explicit.

5. Top 3 pitfalls
1. Ignoring captured evidence.
2. Inventing missing requirements.
3. Changing intentional behavior.

6. Verdict
GO

7. Confidence
High"""


def _write_batch_fixture(
    path,
    *,
    fixture_schema_version=2,
    status="accepted",
    human_label="NOT_REVIEWED",
    human_outcome=None,
    human_note=None,
    reviewed_at=None,
    initial_prompt_hash=None,
):
    initial_prompt = "Audit batch fixture."

    payload = {
        "fixture_schema_version": fixture_schema_version,
        "evidence_schema_version": 1,
        "audit": {
            "status": status,
        },
        "input": {
            "context_names": [],
        },
        "prompts": {
            "system_sha256": "a" * 64,
            "initial": {
                "content": initial_prompt,
                "sha256": (
                    initial_prompt_hash
                    if initial_prompt_hash is not None
                    else sha256_text(initial_prompt)
                ),
            },
            "retry": None,
        },
        "attempts": {
            "first": {
                "response": BATCH_VALID_RESPONSE,
                "validation_errors": [],
            },
            "retry": None,
        },
    }

    if fixture_schema_version == 2:
        payload["human_review"] = {
            "label": human_label,
            "outcome": human_outcome,
            "note": human_note,
            "reviewed_at": reviewed_at,
        }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_replay_audit_cases_summarizes_v1_and_v2(tmp_path):
    _write_batch_fixture(
        tmp_path / "audit_case_1.json",
        fixture_schema_version=1,
    )
    _write_batch_fixture(
        tmp_path / "audit_case_2.json",
        human_label="FALSE_POSITIVE",
        human_outcome="INVESTIGATED_NO_CHANGE",
        human_note="Caller proves the behavior is intentional.",
        reviewed_at="2026-08-20T10:00:00+00:00",
    )

    report = audit_case.replay_audit_cases(tmp_path)

    assert report.total_cases == 2
    assert report.reviewed == 1
    assert report.not_reviewed == 1
    assert report.validator_drift == 0
    assert report.integrity_failures == 0
    assert report.status_label_counts == {
        ("accepted", "FALSE_POSITIVE"): 1,
        ("accepted", "NOT_REVIEWED"): 1,
    }
    assert report.outcome_counts == {
        "INVESTIGATED_NO_CHANGE": 1,
    }
    assert report.issues == []


def test_replay_audit_cases_continues_after_integrity_failure(
    tmp_path,
):
    _write_batch_fixture(
        tmp_path / "audit_case_1.json",
        human_label="USEFUL",
        human_outcome="CODE_CHANGED",
        human_note="A real defect was corrected.",
        reviewed_at="2026-08-20T10:00:00+00:00",
    )
    _write_batch_fixture(
        tmp_path / "audit_case_2.json",
        initial_prompt_hash="0" * 64,
    )

    report = audit_case.replay_audit_cases(tmp_path)

    assert report.total_cases == 2
    assert report.reviewed == 1
    assert report.not_reviewed == 0
    assert report.validator_drift == 0
    assert report.integrity_failures == 1
    assert report.status_label_counts == {
        ("accepted", "USEFUL"): 1,
    }
    assert report.outcome_counts == {
        "CODE_CHANGED": 1,
    }
    assert len(report.issues) == 1
    assert report.issues[0].issue_type == "integrity_failure"
    assert report.issues[0].fixture_path.endswith(
        "audit_case_2.json"
    )
    assert report.issues[0].message == (
        "Initial prompt SHA-256 mismatch."
    )


def test_replay_audit_cases_rejects_empty_directory(tmp_path):
    with pytest.raises(
        audit_case.AuditCaseCollectionError,
        match=r"No audit_case_\*\.json fixtures found",
    ):
        audit_case.replay_audit_cases(tmp_path)

def test_format_audit_batch_report_is_deterministic():
    report = audit_case.AuditBatchReport(
        total_cases=2,
        reviewed=1,
        not_reviewed=1,
        validator_drift=0,
        integrity_failures=0,
        status_label_counts={
            ("accepted", "FALSE_POSITIVE"): 1,
            ("accepted", "NOT_REVIEWED"): 1,
        },
        outcome_counts={
            "INVESTIGATED_NO_CHANGE": 1,
        },
        issues=[],
    )

    assert audit_case.format_audit_batch_report(report) == (
        "Cases: 2\n"
        "Reviewed: 1\n"
        "Not reviewed: 1\n"
        "\n"
        "Accepted + FALSE_POSITIVE: 1\n"
        "Accepted + NOT_REVIEWED: 1\n"
        "\n"
        "INVESTIGATED_NO_CHANGE: 1\n"
        "\n"
        "Validator drift: 0\n"
        "Integrity failures: 0"
    )


def test_main_replay_returns_zero_for_clean_batch(
    tmp_path,
    capsys,
):
    _write_batch_fixture(tmp_path / "audit_case_1.json")

    exit_code = audit_case.main(
        ["replay", str(tmp_path)]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Cases: 1" in captured.out
    assert "Integrity failures: 0" in captured.out
    assert captured.err == ""


def test_main_replay_returns_one_for_integrity_failure(
    tmp_path,
    capsys,
):
    _write_batch_fixture(
        tmp_path / "audit_case_1.json",
        initial_prompt_hash="0" * 64,
    )

    exit_code = audit_case.main(
        ["replay", str(tmp_path)]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Integrity failures: 1" in captured.out
    assert "Initial prompt SHA-256 mismatch." in captured.out


def test_main_replay_returns_two_for_missing_path(
    tmp_path,
    capsys,
):
    missing_path = tmp_path / "missing"

    exit_code = audit_case.main(
        ["replay", str(missing_path)]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "does not exist" in captured.err
