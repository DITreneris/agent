from __future__ import annotations

import json
from pathlib import Path

from audit_runner import ValidatedAuditResult, run_validated_audit
from audit_validator import _extract_verdict
from chat_agent import prepare_selected_code_audit, run_ollama_audit
from code_chunker import find_python_function_range
from prompt_builder import build_file_audit_prompt


EVALUATION_CASES_DIR = Path("evaluation_cases")


def load_evaluation_cases(base_dir: Path = EVALUATION_CASES_DIR) -> list[dict]:
    cases: list[dict] = []

    for case_dir in sorted(base_dir.iterdir()):
        if not case_dir.is_dir():
            continue

        target_path = case_dir / "target.py"
        expected_path = case_dir / "expected.json"

        if not target_path.exists() or not expected_path.exists():
            raise ValueError(f"Incomplete evaluation case: {case_dir}")

        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["case_dir"] = str(case_dir)
        expected["target_path"] = str(target_path)
        cases.append(expected)

    return cases


def prepare_evaluation_case(case: dict) -> dict:
    if case.get("command") != "audit_function":
        raise ValueError(
            f"Unsupported evaluation command: {case.get('command')}"
        )

    target_path = Path(case["target_path"])
    case_dir = target_path.parent
    symbol = case["symbol"]

    start_line, end_line = find_python_function_range(
        target_path,
        symbol,
    )

    prepared = prepare_selected_code_audit(
        project_root=case_dir,
        file_name=target_path.name,
        start_line=start_line,
        end_line=end_line,
    )

    return {
        **case,
        "start_line": prepared.start_line,
        "end_line": prepared.end_line,
        "selected_content": prepared.selected_content,
        "context_content": prepared.context_content,
        "context_names": sorted(prepared.context_names),
    }


FINDING_LABELS = (
    "REAL_BUG",
    "PLAUSIBLE_RISK",
    "FALSE_POSITIVE_CANDIDATE",
    "MAINTAINABILITY_HARDENING",
    "PRODUCT_INSIGHT",
    "TEST_GAP",
    "NEEDS_CONTEXT",
)


def score_evaluation_result(
    case: dict,
    result: ValidatedAuditResult,
) -> dict:
    response = result.response or ""
    verdict = _extract_verdict(response)

    verdict_pass = verdict in case["expected_verdicts"]

    finding_labels_found = [
        label
        for label in FINDING_LABELS
        if label in response
    ]

    no_findings_pass = True
    if case.get("expected_no_findings") is True:
        no_findings_pass = not finding_labels_found

    required_finding_labels = case.get(
        "required_finding_labels",
        [],
    )
    missing_required_finding_labels = [
        label
        for label in required_finding_labels
        if label not in finding_labels_found
    ]
    required_finding_labels_pass = (
        not missing_required_finding_labels
    )

    response_lower = response.lower()

    required_claims = case.get("required_claims", [])
    missing_required_claims = [
        claim
        for claim in required_claims
        if claim.lower() not in response_lower
    ]
    required_claims_pass = not missing_required_claims

    required_keyword_groups = case.get(
        "required_keyword_groups",
        [],
    )
    missing_required_keyword_groups = [
        group
        for group in required_keyword_groups
        if not all(
            keyword.lower() in response_lower
            for keyword in group
        )
    ]
    required_keyword_groups_pass = (
        not missing_required_keyword_groups
    )

    forbidden_claims = case.get("forbidden_claims", [])
    matched_forbidden_claims = [
        claim
        for claim in forbidden_claims
        if claim.lower() in response_lower
    ]
    forbidden_claims_pass = not matched_forbidden_claims

    return {
        "case_id": case["id"],
        "audit_valid": result.success,
        "verdict": verdict,
        "verdict_pass": verdict_pass,
        "finding_labels_found": finding_labels_found,
        "no_findings_pass": no_findings_pass,
        "missing_required_finding_labels": (
            missing_required_finding_labels
        ),
        "required_finding_labels_pass": (
            required_finding_labels_pass
        ),
        "missing_required_claims": missing_required_claims,
        "required_claims_pass": required_claims_pass,
        "missing_required_keyword_groups": (
            missing_required_keyword_groups
        ),
        "required_keyword_groups_pass": (
            required_keyword_groups_pass
        ),
        "matched_forbidden_claims": matched_forbidden_claims,
        "forbidden_claims_pass": forbidden_claims_pass,
        "passed": (
            result.success
            and verdict_pass
            and no_findings_pass
            and required_finding_labels_pass
            and required_claims_pass
            and required_keyword_groups_pass
            and forbidden_claims_pass
        ),
    }


def summarize_evaluation_scores(scores: list[dict]) -> dict:
    total = len(scores)
    passed = sum(1 for score in scores if score["passed"])
    failed = total - passed

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total else 0.0,
    }


def run_evaluation_case(case: dict) -> ValidatedAuditResult:
    prepared = prepare_evaluation_case(case)

    audit_target = (
        f"{prepared['target_path']}, "
        f"function {prepared['symbol']}, "
        f"lines {prepared['start_line']}-{prepared['end_line']}"
    )

    prompt = build_file_audit_prompt(
        audit_target,
        prepared["selected_content"],
        prepared["context_content"],
    )

    return run_validated_audit(
        initial_prompt=prompt,
        model_call=run_ollama_audit,
        available_context_names=set(prepared["context_names"]),
    )


def run_evaluation_suite(
    cases: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    selected_cases = cases or load_evaluation_cases()
    scores: list[dict] = []

    for case in selected_cases:
        result = run_evaluation_case(case)
        score = score_evaluation_result(case, result)

        score["retry_used"] = result.retry_used
        score["validation_errors"] = result.errors
        score["response"] = result.response or ""
        scores.append(score)

    summary = summarize_evaluation_scores(scores)
    return scores, summary


if __name__ == "__main__":
    loaded_cases = load_evaluation_cases()
    print(f"Loaded evaluation cases: {len(loaded_cases)}")

    for case in loaded_cases:
        print(f"- {case['id']}: {case['symbol']}")
