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

    assert payload["fixture_schema_version"] == 1
    assert payload["evidence_schema_version"] == 1
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
