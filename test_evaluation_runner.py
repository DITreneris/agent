from pathlib import Path

from audit_runner import ValidatedAuditResult

from evaluation_runner import (
    load_evaluation_cases,
    prepare_evaluation_case,
    score_evaluation_result,
    summarize_evaluation_scores,
    run_evaluation_suite,
)


def test_load_evaluation_cases(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_001"
    case_dir.mkdir()

    (case_dir / "target.py").write_text(
        "def example() -> int:\n    return 1\n",
        encoding="utf-8",
    )

    (case_dir / "expected.json").write_text(
        """{
  "id": "case_001",
  "command": "audit_function",
  "symbol": "example",
  "expected_verdicts": ["GO"],
  "forbidden_claims": []
}
""",
        encoding="utf-8",
    )

    cases = load_evaluation_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0]["id"] == "case_001"
    assert cases[0]["symbol"] == "example"
    assert cases[0]["target_path"].endswith("target.py")


def test_load_real_evaluation_cases() -> None:
    cases = load_evaluation_cases(Path("evaluation_cases"))

    assert [case["id"] for case in cases] == [
        "case_001_correct_helper_contract",
        "case_002_real_none_bug",
        "case_003_intentional_none_contract",
    ]

    assert cases[0]["expected_verdicts"] == ["GO"]
    assert cases[1]["expected_verdicts"] == ["GO_WITH_NOTES", "BLOCK"]
    assert cases[2]["expected_verdicts"] == ["GO"]


def test_prepare_evaluation_case_includes_same_file_helper() -> None:
    cases = load_evaluation_cases(Path("evaluation_cases"))
    prepared = prepare_evaluation_case(cases[0])

    assert prepared["id"] == "case_001_correct_helper_contract"
    assert prepared["start_line"] == 7
    assert prepared["end_line"] == 8
    assert prepared["context_names"] == ["safe_parse"]
    assert "def safe_parse" in prepared["context_content"]
    assert "return safe_parse(raw)" in prepared["selected_content"]


def test_score_rejects_findings_when_none_are_expected() -> None:
    case = {
        "id": "case_001_correct_helper_contract",
        "expected_verdicts": ["GO"],
        "expected_no_findings": True,
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "No blocking issue is visible.\n"
            "2. Direct critique\n"
            "Classification: NEEDS_CONTEXT\n"
            "Evidence: EVIDENCE_LOW\n"
            "6. Verdict\n"
            "GO\n"
            "7. Confidence\n"
            "Medium"
        ),
        errors=[],
        retry_used=True,
    )

    score = score_evaluation_result(case, result)

    assert score["audit_valid"] is True
    assert score["verdict"] == "GO"
    assert score["verdict_pass"] is True
    assert score["finding_labels_found"] == ["NEEDS_CONTEXT"]
    assert score["no_findings_pass"] is False
    assert score["passed"] is False


def test_score_accepts_false_positive_as_no_finding() -> None:
    case = {
        "id": "case_safe_contract",
        "expected_verdicts": ["GO"],
        "expected_no_findings": True,
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "The visible code safely handles the concern.\n"
            "2. Direct critique\n"
            "Classification: FALSE_POSITIVE_CANDIDATE\n"
            "Evidence: EVIDENCE_HIGH\n"
            "Test status: POSSIBLE_TEST_GAP\n"
            "6. Verdict\n"
            "GO\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["finding_labels_found"] == [
        "FALSE_POSITIVE_CANDIDATE"
    ]
    assert "TEST_GAP" not in score["finding_labels_found"]
    assert score["no_findings_pass"] is True
    assert score["passed"] is True


def test_score_fails_when_required_claim_is_missing() -> None:
    case = {
        "id": "case_required_claim",
        "expected_verdicts": ["BLOCK"],
        "required_claims": ["strip may fail on None"],
        "forbidden_claims": [],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "A bug exists.\n"
            "2. Direct critique\n"
            "Classification: REAL_BUG\n"
            "Evidence: EVIDENCE_HIGH\n"
            "6. Verdict\n"
            "BLOCK\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["required_claims_pass"] is False
    assert score["missing_required_claims"] == [
        "strip may fail on None"
    ]
    assert score["passed"] is False


def test_score_fails_when_forbidden_claim_is_present() -> None:
    case = {
        "id": "case_forbidden_claim",
        "expected_verdicts": ["GO"],
        "forbidden_claims": [
            "helper implementation is missing"
        ],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "No blocking issue is visible.\n"
            "2. Direct critique\n"
            "The helper implementation is missing.\n"
            "6. Verdict\n"
            "GO\n"
            "7. Confidence\n"
            "Low"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["forbidden_claims_pass"] is False
    assert score["matched_forbidden_claims"] == [
        "helper implementation is missing"
    ]
    assert score["passed"] is False


def test_score_passes_required_keyword_groups() -> None:
    case = {
        "id": "case_keyword_groups",
        "expected_verdicts": ["BLOCK"],
        "required_keyword_groups": [
            ["name", "missing"],
            ["none", "strip"],
            ["attributeerror"],
        ],
        "forbidden_claims": [],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "The name key may be missing.\n"
            "2. Direct critique\n"
            "Calling strip on None raises AttributeError.\n"
            "6. Verdict\n"
            "BLOCK\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["missing_required_keyword_groups"] == []
    assert score["required_keyword_groups_pass"] is True
    assert score["passed"] is True


def test_score_fails_missing_keyword_group() -> None:
    case = {
        "id": "case_keyword_groups",
        "expected_verdicts": ["BLOCK"],
        "required_keyword_groups": [
            ["none", "strip"],
            ["attributeerror"],
        ],
        "forbidden_claims": [],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "The function may fail.\n"
            "6. Verdict\n"
            "BLOCK\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["required_keyword_groups_pass"] is False
    assert score["missing_required_keyword_groups"] == [
        ["none", "strip"],
        ["attributeerror"],
    ]
    assert score["passed"] is False


def test_summarize_evaluation_scores() -> None:
    scores = [
        {"passed": False},
        {"passed": True},
        {"passed": False},
    ]

    summary = summarize_evaluation_scores(scores)

    assert summary == {
        "total": 3,
        "passed": 1,
        "failed": 2,
        "pass_rate": 1 / 3,
    }


def test_run_evaluation_suite_aggregates_scores(
    monkeypatch,
) -> None:
    cases = [
        {
            "id": "case_001",
            "expected_verdicts": ["GO"],
            "expected_no_findings": True,
        },
        {
            "id": "case_002",
            "expected_verdicts": ["BLOCK"],
        },
    ]

    results = iter(
        [
            ValidatedAuditResult(
                success=True,
                response=(
                    "1. Bottom line\n"
                    "No issue visible.\n"
                    "2. Direct critique\n"
                    "Classification: FALSE_POSITIVE_CANDIDATE\n"
                    "No actionable defect.\n"
                    "6. Verdict\n"
                    "GO\n"
                    "7. Confidence\n"
                    "High"
                ),
                errors=[],
                retry_used=False,
            ),
            ValidatedAuditResult(
                success=True,
                response=(
                    "1. Bottom line\n"
                    "A real bug exists.\n"
                    "2. Direct critique\n"
                    "Classification: REAL_BUG\n"
                    "Evidence: EVIDENCE_HIGH\n"
                    "6. Verdict\n"
                    "BLOCK\n"
                    "7. Confidence\n"
                    "High"
                ),
                errors=[],
                retry_used=True,
            ),
        ]
    )

    monkeypatch.setattr(
        "evaluation_runner.run_evaluation_case",
        lambda case: next(results),
    )

    scores, summary = run_evaluation_suite(cases)

    assert len(scores) == 2
    assert scores[0]["passed"] is True
    assert scores[0]["retry_used"] is False
    assert scores[1]["passed"] is True
    assert scores[1]["retry_used"] is True

    assert summary == {
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
    }



def test_run_evaluation_suite_preserves_attempt_diagnostics(
    monkeypatch,
) -> None:
    retry_response = """
1. Bottom line
No actionable defect is visible.

2. Direct critique
Classification: FALSE_POSITIVE_CANDIDATE
Evidence: EVIDENCE_HIGH
Why: The visible code handles the case.
Missing context: none

3. Better option
Keep the code unchanged.

4. Next steps
Recommended action: NO_CHANGE
Test status: NO_TEST_NEEDED
Reason: No defect is visible.

5. Top 3 pitfalls
No grounded pitfalls are visible.

6. Verdict
GO

7. Confidence
High
""".strip()

    result = ValidatedAuditResult(
        success=True,
        response=retry_response,
        errors=[],
        retry_used=True,
        first_response="Invalid first response",
        first_validation_errors=[
            "Response must start with '1. Bottom line'.",
        ],
        retry_response=retry_response,
        retry_validation_errors=[],
    )

    monkeypatch.setattr(
        "evaluation_runner.run_evaluation_case",
        lambda case: result,
    )

    cases = [
        {
            "id": "case_diagnostics",
            "expected_verdicts": ["GO"],
            "expected_no_findings": True,
        }
    ]

    scores, summary = run_evaluation_suite(cases)
    score = scores[0]

    assert summary["passed"] == 1
    assert score["first_response"] == result.first_response
    assert (
        score["first_validation_errors"]
        == result.first_validation_errors
    )
    assert score["retry_response"] == result.retry_response
    assert (
        score["retry_validation_errors"]
        == result.retry_validation_errors
    )



def test_score_requires_expected_finding_label() -> None:
    case = {
        "id": "case_real_bug",
        "expected_verdicts": ["GO_WITH_NOTES", "BLOCK"],
        "required_finding_labels": ["REAL_BUG"],
        "required_keyword_groups": [
            ["none", "strip"],
            ["attributeerror"],
        ],
        "forbidden_claims": [],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "Missing name may cause failure.\n"
            "2. Direct critique\n"
            "Classification: MAINTAINABILITY_HARDENING\n"
            "Evidence: EVIDENCE_HIGH\n"
            "Calling strip on None raises AttributeError.\n"
            "6. Verdict\n"
            "GO_WITH_NOTES\n"
            "7. Confidence\n"
            "Medium"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["required_finding_labels_pass"] is False
    assert score["missing_required_finding_labels"] == [
        "REAL_BUG"
    ]
    assert score["passed"] is False


def test_score_rejects_missing_classification_when_none_are_expected():
    case = {
        "id": "case_safe_contract",
        "expected_verdicts": ["GO"],
        "expected_no_findings": True,
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "No issue is visible.\n"
            "2. Direct critique\n"
            "No findings.\n"
            "6. Verdict\n"
            "GO\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["finding_labels_found"] == []
    assert score["no_findings_pass"] is False
    assert score["passed"] is False
