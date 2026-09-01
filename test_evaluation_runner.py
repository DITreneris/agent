import json
from pathlib import Path

from audit_runner import ValidatedAuditResult

from evaluation_runner import (
    load_evaluation_cases,
    parse_cli_args,
    prepare_evaluation_case,
    run_cli,
    score_evaluation_result,
    summarize_case_stability,
    summarize_evaluation_scores,
    run_evaluation_suite,
    extract_recommended_action,
    map_action_to_decision,
    summarize_decision_scores,
    summarize_benchmark_gate,
)


def test_parse_cli_args_accepts_multi_seed_config(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "result.json"

    args = parse_cli_args(
        [
            "--model",
            "test-model",
            "--temperature",
            "0.0",
            "--num-ctx",
            "8192",
            "--seeds",
            "11,22,33",
            "--output",
            str(output_path),
        ]
    )

    assert args.model == "test-model"
    assert args.temperature == 0.0
    assert args.num_ctx == 8192
    assert args.seeds == [11, 22, 33]
    assert args.output == output_path


def test_run_cli_writes_multi_seed_json_without_real_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured = {
        "configs": [],
    }

    def fake_run_evaluation_suite(
        cases=None,
        model_call=None,
    ):
        config = model_call.keywords["config"]
        captured["configs"].append(config)

        return (
            [
                {
                    "case_id": "case_001",
                    "passed": True,
                    "audit_valid": True,
                    "verdict": "GO",
                    "retry_used": False,
                    "expected_decision": "NO_CHANGE",
                    "actual_decision": "NO_CHANGE",
                    "decision_correct": True,
                    "high_confidence_false_positive": False,
                }
            ],
            {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "pass_rate": 1.0,
            },
        )

    monkeypatch.setattr(
        "evaluation_runner.run_evaluation_suite",
        fake_run_evaluation_suite,
    )

    output_path = tmp_path / "nested" / "result.json"

    exit_code = run_cli(
        [
            "--model",
            "test-model",
            "--temperature",
            "0.0",
            "--num-ctx",
            "8192",
            "--seeds",
            "11,22,33",
            "--output",
            str(output_path),
        ]
    )

    report = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert [
        config.seed
        for config in captured["configs"]
    ] == [11, 22, 33]
    assert [
        config.num_ctx
        for config in captured["configs"]
    ] == [8192, 8192, 8192]
    assert report["metadata"] == {
        "model": "test-model",
        "temperature": 0.0,
        "num_ctx": 8192,
        "seeds": [11, 22, 33],
        "run_count": 3,
    }
    assert report["summary"] == {
        "total": 3,
        "passed": 3,
        "failed": 0,
        "pass_rate": 1.0,
    }

    assert report["decision_summary"] == {
        "total_scored": 3,
        "correct_decisions": 3,
        "incorrect_decisions": 0,
        "decision_accuracy": 1.0,
        "false_positive_count": 0,
        "false_negative_count": 0,
        "high_confidence_false_positive_count": 0,
        "context_required_runs": 0,
        "actual_inspect_context_runs": 0,
        "correct_inspect_context_runs": 0,
        "inspect_context_recall": 0.0,
        "inspect_context_precision": 0.0,
    }

    assert report["benchmark_gate"] == {
        "total_cases": 1,
        "majority_correct_cases": 1,
        "minimum_majority_correct_cases": 6,
        "majority_case_gate": False,
        "change_cases": 0,
        "change_cases_correct": 0,
        "required_change_cases_correct": 3,
        "change_case_gate": False,
        "no_change_cases": 1,
        "no_change_cases_correct": 1,
        "required_no_change_cases_correct": 2,
        "no_change_case_gate": False,
        "context_cases": 0,
        "context_cases_correct": 0,
        "required_context_cases_correct": 1,
        "context_case_gate": False,
        "high_confidence_false_positive_count": 0,
        "high_confidence_false_positive_gate": True,
        "total_runs": 3,
        "structurally_valid_runs": 3,
        "structural_validation_rate": 1.0,
        "minimum_structural_validation_rate": 0.75,
        "structural_validation_gate": True,
        "passed": False,
    }


    assert [
        run["seed"]
        for run in report["runs"]
    ] == [11, 22, 33]
    assert report["runs"][0]["case_results"][0] == {
        "case_id": "case_001",
        "passed": True,
        "audit_valid": True,
        "verdict": "GO",
        "retry_used": False,
        "expected_decision": "NO_CHANGE",
        "actual_decision": "NO_CHANGE",
        "decision_correct": True,
        "high_confidence_false_positive": False,
        "run_index": 1,
        "seed": 11,
    }

    assert report["case_stability"] == [
            {
                "case_id": "case_001",
                "total_runs": 3,
                "passed_runs": 3,
                "failed_runs": 0,
                "pass_rate": 1.0,
                "stable_pass_outcome": True,
                "verdict_counts": {"GO": 3},
                "stable_verdict": True,
                "retry_runs": 0,
                "retry_rate": 0.0,
                "expected_decision": "NO_CHANGE",
                "decision_counts": {"NO_CHANGE": 3},
                "majority_decision": "NO_CHANGE",
                "majority_count": 3,
                "majority_decision_correct": True,
                "correct_decision_runs": 3,
                "decision_accuracy": 1.0,
                "stable_decision": True,
                "high_confidence_false_positive_runs": 0,
            }
        ]


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
        "case_004_empty_average_bug",
        "case_005_partial_transfer_mutation",
        "case_006_idempotent_cleanup",
        "case_007_timeout_requires_caller",
        "case_008_profile_requires_schema",
    ]

    assert cases[0]["expected_verdicts"] == ["GO"]
    assert cases[1]["expected_verdicts"] == ["GO_WITH_NOTES", "BLOCK"]
    assert cases[2]["expected_verdicts"] == ["GO"]

    assert [
        case["expected_decision"]
        for case in cases
    ] == [
        "NO_CHANGE",
        "CHANGE",
        "NO_CHANGE",
        "CHANGE",
        "CHANGE",
        "NO_CHANGE",
        "INSPECT_CONTEXT",
        "INSPECT_CONTEXT",
    ]

    assert all(
        case["ground_truth"]
        for case in cases
    )

    assert cases[0]["allowed_actions"] == [
        "NO_CHANGE",
        "DO_NOT_FIX",
    ]
    assert cases[1]["allowed_actions"] == [
        "FIX_NOW",
    ]
    assert cases[2]["allowed_actions"] == [
        "NO_CHANGE",
        "DO_NOT_FIX",
    ]

    assert cases[3]["allowed_actions"] == [
        "FIX_NOW",
    ]

    assert cases[4]["allowed_actions"] == [
        "FIX_NOW",
    ]

    assert cases[5]["allowed_actions"] == [
        "NO_CHANGE",
        "DO_NOT_FIX",
    ]

    assert cases[6]["allowed_actions"] == [
        "INSPECT_CONTEXT",
    ]

    assert cases[7]["allowed_actions"] == [
        "INSPECT_CONTEXT",
    ]

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



def test_summarize_case_stability_tracks_variation() -> None:
    scores = [
        {
            "case_id": "case_stable",
            "passed": True,
            "verdict": "GO",
            "retry_used": False,
        },
        {
            "case_id": "case_variable",
            "passed": True,
            "verdict": "GO_WITH_NOTES",
            "retry_used": False,
        },
        {
            "case_id": "case_stable",
            "passed": True,
            "verdict": "GO",
            "retry_used": False,
        },
        {
            "case_id": "case_variable",
            "passed": False,
            "verdict": "BLOCK",
            "retry_used": True,
        },
    ]

    summaries = summarize_case_stability(scores)

    assert summaries == [
        {
            "case_id": "case_stable",
            "total_runs": 2,
            "passed_runs": 2,
            "failed_runs": 0,
            "pass_rate": 1.0,
            "stable_pass_outcome": True,
            "verdict_counts": {"GO": 2},
            "stable_verdict": True,
            "retry_runs": 0,
            "retry_rate": 0.0,
        },
        {
            "case_id": "case_variable",
            "total_runs": 2,
            "passed_runs": 1,
            "failed_runs": 1,
            "pass_rate": 0.5,
            "stable_pass_outcome": False,
            "verdict_counts": {
                "GO_WITH_NOTES": 1,
                "BLOCK": 1,
            },
            "stable_verdict": False,
            "retry_runs": 1,
            "retry_rate": 0.5,
        },
    ]



def test_single_run_does_not_establish_stability() -> None:
    summaries = summarize_case_stability(
        [
            {
                "case_id": "case_single",
                "passed": True,
                "verdict": "GO",
                "retry_used": False,
            }
        ]
    )

    assert summaries[0]["stable_pass_outcome"] is False
    assert summaries[0]["stable_verdict"] is False


def test_run_evaluation_suite_respects_empty_case_list(
    monkeypatch,
) -> None:
    def fail_if_cases_are_loaded():
        raise AssertionError("Default cases must not be loaded")

    monkeypatch.setattr(
        "evaluation_runner.load_evaluation_cases",
        fail_if_cases_are_loaded,
    )

    scores, summary = run_evaluation_suite(cases=[])

    assert scores == []
    assert summary == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
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

    model_calls = []

    def fake_run_evaluation_case(case, model_call):
        model_calls.append(model_call)
        return next(results)

    def injected_model_call(prompt):
        return "unused"

    monkeypatch.setattr(
        "evaluation_runner.run_evaluation_case",
        fake_run_evaluation_case,
    )

    scores, summary = run_evaluation_suite(
        cases,
        model_call=injected_model_call,
    )

    assert len(scores) == 2
    assert scores[0]["passed"] is True
    assert scores[0]["retry_used"] is False
    assert scores[1]["passed"] is True
    assert scores[1]["retry_used"] is True
    assert model_calls == [
        injected_model_call,
        injected_model_call,
    ]

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
        lambda case, model_call: result,
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

def test_extract_recommended_action_uses_next_steps_section() -> None:
    response = (
        "3. Better option\n"
        "Do not confuse this with Recommended action: NO_CHANGE.\n"
        "4. Next steps\n"
        "- Recommended action: FIX_NOW\n"
        "- Test status: ADD_TEST_CONFIRMED\n"
        "- Reason: The visible execution path proves the defect.\n"
        "5. Top 3 pitfalls\n"
        "The defect can cause a runtime failure."
    )

    assert extract_recommended_action(response) == "FIX_NOW"


def test_map_action_to_decision() -> None:
    expected_decisions = {
        "FIX_NOW": "CHANGE",
        "HARDEN_SMALL": "CHANGE",
        "ADD_TEST_CONFIRMED": "CHANGE",
        "REFACTOR_LATER": "CHANGE",
        "NO_CHANGE": "NO_CHANGE",
        "DO_NOT_FIX": "NO_CHANGE",
        "INSPECT_CONTEXT": "INSPECT_CONTEXT",
        "": "UNKNOWN",
        "UNSUPPORTED_ACTION": "UNKNOWN",
    }

    for action, expected_decision in expected_decisions.items():
        assert map_action_to_decision(action) == expected_decision


def test_score_includes_correct_decision_fields() -> None:
    case = {
        "id": "case_real_bug",
        "expected_verdicts": ["GO_WITH_NOTES", "BLOCK"],
        "expected_decision": "CHANGE",
        "allowed_actions": ["FIX_NOW"],
        "expected_classifications": ["REAL_BUG"],
        "allowed_confidence": ["High", "Medium"],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "A directly provable runtime defect is visible.\n"
            "2. Direct critique\n"
            "Classification: REAL_BUG\n"
            "Evidence: EVIDENCE_HIGH\n"
            "Why: None reaches strip and raises AttributeError.\n"
            "Missing context: none\n"
            "3. Better option\n"
            "Handle None before calling strip.\n"
            "4. Next steps\n"
            "Recommended action: FIX_NOW\n"
            "Test status: ADD_TEST_CONFIRMED\n"
            "Reason: The current execution path can fail.\n"
            "5. Top 3 pitfalls\n"
            "The runtime failure blocks the workflow.\n"
            "6. Verdict\n"
            "GO_WITH_NOTES\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["recommended_action"] == "FIX_NOW"
    assert score["expected_decision"] == "CHANGE"
    assert score["actual_decision"] == "CHANGE"
    assert score["decision_correct"] is True
    assert score["allowed_action_pass"] is True
    assert score["expected_classifications_pass"] is True
    assert score["allowed_confidence_pass"] is True
    assert score["confidence"] == "High"
    assert score["high_confidence_false_positive"] is False
    assert score["passed"] is True


def test_wrong_decision_fails_evaluation_score() -> None:
    case = {
        "id": "case_safe_code",
        "expected_verdicts": ["GO"],
        "expected_decision": "NO_CHANGE",
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "The code should be changed.\n"
            "2. Direct critique\n"
            "Classification: MAINTAINABILITY_HARDENING\n"
            "Evidence: EVIDENCE_HIGH\n"
            "Why: A defensive change could be added.\n"
            "Missing context: none\n"
            "3. Better option\n"
            "Add another guard.\n"
            "4. Next steps\n"
            "Recommended action: HARDEN_SMALL\n"
            "Test status: POSSIBLE_TEST_GAP\n"
            "Reason: Additional defensive handling may help.\n"
            "5. Top 3 pitfalls\n"
            "Future behavior may change.\n"
            "6. Verdict\n"
            "GO\n"
            "7. Confidence\n"
            "High"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["recommended_action"] == "HARDEN_SMALL"
    assert score["expected_decision"] == "NO_CHANGE"
    assert score["actual_decision"] == "CHANGE"
    assert score["decision_correct"] is False
    assert score["confidence"] == "High"
    assert score["high_confidence_false_positive"] is True
    assert score["passed"] is False


def test_summarize_decision_scores() -> None:
    scores = [
        {
            "expected_decision": "CHANGE",
            "actual_decision": "CHANGE",
            "decision_correct": True,
            "high_confidence_false_positive": False,
        },
        {
            "expected_decision": "CHANGE",
            "actual_decision": "NO_CHANGE",
            "decision_correct": False,
            "high_confidence_false_positive": False,
        },
        {
            "expected_decision": "NO_CHANGE",
            "actual_decision": "CHANGE",
            "decision_correct": False,
            "high_confidence_false_positive": True,
        },
        {
            "expected_decision": "NO_CHANGE",
            "actual_decision": "NO_CHANGE",
            "decision_correct": True,
            "high_confidence_false_positive": False,
        },
        {
            "expected_decision": "INSPECT_CONTEXT",
            "actual_decision": "INSPECT_CONTEXT",
            "decision_correct": True,
            "high_confidence_false_positive": False,
        },
        {
            "expected_decision": None,
            "actual_decision": "UNKNOWN",
            "decision_correct": None,
            "high_confidence_false_positive": False,
        },
    ]

    assert summarize_decision_scores(scores) == {
        "total_scored": 5,
        "correct_decisions": 3,
        "incorrect_decisions": 2,
        "decision_accuracy": 0.6,
        "false_positive_count": 1,
        "false_negative_count": 1,
        "high_confidence_false_positive_count": 1,
        "context_required_runs": 1,
        "actual_inspect_context_runs": 1,
        "correct_inspect_context_runs": 1,
        "inspect_context_recall": 1.0,
        "inspect_context_precision": 1.0,
    }

def test_score_rejects_disallowed_decision_contract_values() -> None:
    case = {
        "id": "case_real_bug_understated",
        "expected_verdicts": ["GO_WITH_NOTES"],
        "expected_decision": "CHANGE",
        "allowed_actions": ["FIX_NOW"],
        "expected_classifications": ["REAL_BUG"],
        "allowed_confidence": ["High", "Medium"],
    }

    result = ValidatedAuditResult(
        success=True,
        response=(
            "1. Bottom line\n"
            "A small hardening opportunity is visible.\n"
            "2. Direct critique\n"
            "Classification: MAINTAINABILITY_HARDENING\n"
            "Evidence: EVIDENCE_LOW\n"
            "Why: Defensive handling may help.\n"
            "Missing context: none\n"
            "3. Better option\n"
            "Consider a defensive guard.\n"
            "4. Next steps\n"
            "Recommended action: HARDEN_SMALL\n"
            "Test status: POSSIBLE_TEST_GAP\n"
            "Reason: A small guard may reduce future risk.\n"
            "5. Top 3 pitfalls\n"
            "The current concern may remain.\n"
            "6. Verdict\n"
            "GO_WITH_NOTES\n"
            "7. Confidence\n"
            "Low"
        ),
        errors=[],
        retry_used=False,
    )

    score = score_evaluation_result(case, result)

    assert score["actual_decision"] == "CHANGE"
    assert score["decision_correct"] is True
    assert score["allowed_action_pass"] is False
    assert score["expected_classifications_pass"] is False
    assert score["allowed_confidence_pass"] is False
    assert score["passed"] is False

def test_summarize_case_stability_reports_majority_decision() -> None:
    scores = [
        {
            "case_id": "case_bug",
            "passed": True,
            "verdict": "BLOCK",
            "retry_used": False,
            "expected_decision": "CHANGE",
            "actual_decision": "CHANGE",
            "decision_correct": True,
            "high_confidence_false_positive": False,
        },
        {
            "case_id": "case_bug",
            "passed": True,
            "verdict": "BLOCK",
            "retry_used": True,
            "expected_decision": "CHANGE",
            "actual_decision": "CHANGE",
            "decision_correct": True,
            "high_confidence_false_positive": False,
        },
        {
            "case_id": "case_bug",
            "passed": False,
            "verdict": "GO",
            "retry_used": False,
            "expected_decision": "CHANGE",
            "actual_decision": "NO_CHANGE",
            "decision_correct": False,
            "high_confidence_false_positive": False,
        },
    ]

    case_summary = summarize_case_stability(scores)[0]

    assert case_summary["expected_decision"] == "CHANGE"
    assert case_summary["decision_counts"] == {
        "CHANGE": 2,
        "NO_CHANGE": 1,
    }
    assert case_summary["majority_decision"] == "CHANGE"
    assert case_summary["majority_count"] == 2
    assert case_summary["majority_decision_correct"] is True
    assert case_summary["correct_decision_runs"] == 2
    assert case_summary["decision_accuracy"] == 2 / 3
    assert case_summary["stable_decision"] is False
    assert case_summary["high_confidence_false_positive_runs"] == 0

def test_summarize_benchmark_gate_passes_at_locked_thresholds() -> None:
    case_decisions = {
        "case_001": "NO_CHANGE",
        "case_002": "CHANGE",
        "case_003": "NO_CHANGE",
        "case_004": "CHANGE",
        "case_005": "CHANGE",
        "case_006": "NO_CHANGE",
        "case_007": "INSPECT_CONTEXT",
        "case_008": "INSPECT_CONTEXT",
    }
    scores = []

    for case_id, expected_decision in case_decisions.items():
        for _ in range(3):
            audit_valid = len(scores) >= 6
            scores.append(
                {
                    "case_id": case_id,
                    "passed": audit_valid,
                    "audit_valid": audit_valid,
                    "verdict": "GO",
                    "retry_used": False,
                    "expected_decision": expected_decision,
                    "actual_decision": expected_decision,
                    "decision_correct": True,
                    "high_confidence_false_positive": False,
                }
            )

    gate = summarize_benchmark_gate(scores)

    assert gate == {
        "total_cases": 8,
        "majority_correct_cases": 8,
        "minimum_majority_correct_cases": 6,
        "majority_case_gate": True,
        "change_cases": 3,
        "change_cases_correct": 3,
        "required_change_cases_correct": 3,
        "change_case_gate": True,
        "no_change_cases": 3,
        "no_change_cases_correct": 3,
        "required_no_change_cases_correct": 2,
        "no_change_case_gate": True,
        "context_cases": 2,
        "context_cases_correct": 2,
        "required_context_cases_correct": 1,
        "context_case_gate": True,
        "high_confidence_false_positive_count": 0,
        "high_confidence_false_positive_gate": True,
        "total_runs": 24,
        "structurally_valid_runs": 18,
        "structural_validation_rate": 0.75,
        "minimum_structural_validation_rate": 0.75,
        "structural_validation_gate": True,
        "passed": True,
    }

def test_summarize_benchmark_gate_rejects_failed_thresholds() -> None:
    expected_decisions = {
        "case_001": "NO_CHANGE",
        "case_002": "CHANGE",
        "case_003": "NO_CHANGE",
        "case_004": "CHANGE",
        "case_005": "CHANGE",
        "case_006": "NO_CHANGE",
        "case_007": "INSPECT_CONTEXT",
        "case_008": "INSPECT_CONTEXT",
    }
    wrong_decisions = {
        "case_001": "CHANGE",
        "case_002": "NO_CHANGE",
        "case_003": "CHANGE",
    }
    scores = []

    for case_id, expected_decision in expected_decisions.items():
        actual_decision = wrong_decisions.get(
            case_id,
            expected_decision,
        )

        for _ in range(3):
            audit_valid = len(scores) >= 7
            decision_correct = (
                actual_decision == expected_decision
            )
            scores.append(
                {
                    "case_id": case_id,
                    "passed": (
                        audit_valid and decision_correct
                    ),
                    "audit_valid": audit_valid,
                    "verdict": "GO",
                    "retry_used": False,
                    "expected_decision": expected_decision,
                    "actual_decision": actual_decision,
                    "decision_correct": decision_correct,
                    "high_confidence_false_positive": (
                        expected_decision == "NO_CHANGE"
                        and actual_decision == "CHANGE"
                    ),
                }
            )

    gate = summarize_benchmark_gate(scores)

    assert gate["majority_correct_cases"] == 5
    assert gate["majority_case_gate"] is False

    assert gate["change_cases_correct"] == 2
    assert gate["change_case_gate"] is False

    assert gate["no_change_cases_correct"] == 1
    assert gate["no_change_case_gate"] is False

    assert gate["high_confidence_false_positive_count"] == 6
    assert gate["high_confidence_false_positive_gate"] is False

    assert gate["structurally_valid_runs"] == 17
    assert gate["structural_validation_rate"] == 17 / 24
    assert gate["structural_validation_gate"] is False

    assert gate["passed"] is False


def test_benchmark_gate_rejects_zero_context_recall_at_six_of_eight(
) -> None:
    expected_decisions = {
        "case_001": "NO_CHANGE",
        "case_002": "CHANGE",
        "case_003": "NO_CHANGE",
        "case_004": "CHANGE",
        "case_005": "CHANGE",
        "case_006": "NO_CHANGE",
        "case_007": "INSPECT_CONTEXT",
        "case_008": "INSPECT_CONTEXT",
    }
    scores = []

    for case_id, expected_decision in expected_decisions.items():
        actual_decision = (
            "CHANGE"
            if expected_decision == "INSPECT_CONTEXT"
            else expected_decision
        )
        decision_correct = (
            actual_decision == expected_decision
        )

        for _ in range(3):
            scores.append(
                {
                    "case_id": case_id,
                    "passed": decision_correct,
                    "audit_valid": True,
                    "verdict": "GO",
                    "retry_used": False,
                    "expected_decision": expected_decision,
                    "actual_decision": actual_decision,
                    "decision_correct": decision_correct,
                    "high_confidence_false_positive": False,
                }
            )

    gate = summarize_benchmark_gate(scores)

    assert gate["majority_correct_cases"] == 6
    assert gate["majority_case_gate"] is True
    assert gate["change_case_gate"] is True
    assert gate["no_change_case_gate"] is True
    assert gate["structural_validation_gate"] is True
    assert (
        gate["high_confidence_false_positive_gate"]
        is True
    )
    assert gate["context_cases"] == 2
    assert gate["context_cases_correct"] == 0
    assert gate["context_case_gate"] is False
    assert gate["passed"] is False


def test_benchmark_gate_accepts_one_of_two_context_cases(
) -> None:
    expected_decisions = {
        "case_001": "NO_CHANGE",
        "case_002": "CHANGE",
        "case_003": "NO_CHANGE",
        "case_004": "CHANGE",
        "case_005": "CHANGE",
        "case_006": "NO_CHANGE",
        "case_007": "INSPECT_CONTEXT",
        "case_008": "INSPECT_CONTEXT",
    }
    scores = []

    for case_id, expected_decision in expected_decisions.items():
        for run_index in range(3):
            if case_id == "case_007":
                actual_decision = (
                    "INSPECT_CONTEXT"
                    if run_index < 2
                    else "CHANGE"
                )
            elif case_id == "case_008":
                actual_decision = "CHANGE"
            else:
                actual_decision = expected_decision

            decision_correct = (
                actual_decision == expected_decision
            )

            scores.append(
                {
                    "case_id": case_id,
                    "passed": decision_correct,
                    "audit_valid": True,
                    "verdict": "GO",
                    "retry_used": False,
                    "expected_decision": expected_decision,
                    "actual_decision": actual_decision,
                    "decision_correct": decision_correct,
                    "high_confidence_false_positive": False,
                }
            )

    gate = summarize_benchmark_gate(scores)

    assert gate["majority_correct_cases"] == 7
    assert gate["majority_case_gate"] is True
    assert gate["change_case_gate"] is True
    assert gate["no_change_case_gate"] is True
    assert gate["context_cases"] == 2
    assert gate["context_cases_correct"] == 1
    assert gate["required_context_cases_correct"] == 1
    assert gate["context_case_gate"] is True
    assert gate["structural_validation_gate"] is True
    assert (
        gate["high_confidence_false_positive_gate"]
        is True
    )
    assert gate["passed"] is True


def test_summarize_decision_scores_separates_context_metrics() -> None:
    scores = [
        {
            "expected_decision": "INSPECT_CONTEXT",
            "actual_decision": "INSPECT_CONTEXT",
            "decision_correct": True,
            "high_confidence_false_positive": False,
        },
        {
            "expected_decision": "INSPECT_CONTEXT",
            "actual_decision": "CHANGE",
            "decision_correct": False,
            "high_confidence_false_positive": False,
        },
        {
            "expected_decision": "NO_CHANGE",
            "actual_decision": "INSPECT_CONTEXT",
            "decision_correct": False,
            "high_confidence_false_positive": False,
        },
    ]

    summary = summarize_decision_scores(scores)

    assert summary["context_required_runs"] == 2
    assert summary["actual_inspect_context_runs"] == 2
    assert summary["correct_inspect_context_runs"] == 1
    assert summary["inspect_context_recall"] == 0.5
    assert summary["inspect_context_precision"] == 0.5
    assert "abstention_total" not in summary
    assert "abstention_accuracy" not in summary
