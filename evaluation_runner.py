from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import partial
import json
from pathlib import Path

from audit_model_client import OllamaAuditConfig
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


def _extract_finding_labels(response: str) -> list[str]:
    labels: list[str] = []

    for line in response.splitlines():
        normalized = line.strip()

        if normalized.startswith("- "):
            normalized = normalized[2:].strip()

        prefix = "Classification:"
        if not normalized.startswith(prefix):
            continue

        label = normalized[len(prefix):].strip()
        if label in FINDING_LABELS and label not in labels:
            labels.append(label)

    return labels


def score_evaluation_result(
    case: dict,
    result: ValidatedAuditResult,
) -> dict:
    response = result.response or ""
    verdict = _extract_verdict(response)

    verdict_pass = verdict in case["expected_verdicts"]

    finding_labels_found = _extract_finding_labels(response)

    no_findings_pass = True
    if case.get("expected_no_findings") is True:
        no_findings_pass = (
            bool(finding_labels_found)
            and all(
                label == "FALSE_POSITIVE_CANDIDATE"
                for label in finding_labels_found
            )
        )

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


def summarize_case_stability(
    scores: list[dict],
) -> list[dict]:
    grouped_scores: dict[str, list[dict]] = {}
    case_order: list[str] = []

    for score in scores:
        case_id = score["case_id"]

        if case_id not in grouped_scores:
            grouped_scores[case_id] = []
            case_order.append(case_id)

        grouped_scores[case_id].append(score)

    summaries: list[dict] = []

    for case_id in case_order:
        case_scores = grouped_scores[case_id]
        total_runs = len(case_scores)
        passed_runs = sum(
            1
            for score in case_scores
            if score["passed"]
        )
        failed_runs = total_runs - passed_runs
        retry_runs = sum(
            1
            for score in case_scores
            if score.get("retry_used", False)
        )

        verdict_counts: dict[str, int] = {}

        for score in case_scores:
            verdict = score.get("verdict") or "UNKNOWN"
            verdict_counts[verdict] = (
                verdict_counts.get(verdict, 0) + 1
            )

        summaries.append(
            {
                "case_id": case_id,
                "total_runs": total_runs,
                "passed_runs": passed_runs,
                "failed_runs": failed_runs,
                "pass_rate": (
                    passed_runs / total_runs
                    if total_runs
                    else 0.0
                ),
                "stable_pass_outcome": (
                    total_runs >= 2
                    and passed_runs in {0, total_runs}
                ),
                "verdict_counts": verdict_counts,
                "stable_verdict": (
                    total_runs >= 2
                    and len(verdict_counts) == 1
                ),
                "retry_runs": retry_runs,
                "retry_rate": (
                    retry_runs / total_runs
                    if total_runs
                    else 0.0
                ),
            }
        )

    return summaries


def run_evaluation_case(
    case: dict,
    model_call: Callable[[str], str] = run_ollama_audit,
) -> ValidatedAuditResult:
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
        model_call=model_call,
        available_context_names=set(prepared["context_names"]),
    )


def run_evaluation_suite(
    cases: list[dict] | None = None,
    model_call: Callable[[str], str] = run_ollama_audit,
) -> tuple[list[dict], dict]:
    selected_cases = (
        load_evaluation_cases()
        if cases is None
        else cases
    )
    scores: list[dict] = []

    for case in selected_cases:
        result = run_evaluation_case(
            case,
            model_call=model_call,
        )
        score = score_evaluation_result(case, result)

        score["retry_used"] = result.retry_used
        score["validation_errors"] = result.errors
        score["response"] = result.response or ""
        score["first_response"] = result.first_response
        score["first_validation_errors"] = list(
            result.first_validation_errors
        )
        score["retry_response"] = result.retry_response
        score["retry_validation_errors"] = list(
            result.retry_validation_errors
        )
        scores.append(score)

    summary = summarize_evaluation_scores(scores)
    return scores, summary


def parse_seed_list(value: str) -> list[int]:
    parts = [
        part.strip()
        for part in value.split(",")
    ]

    if not parts or any(not part for part in parts):
        raise argparse.ArgumentTypeError(
            "Seeds must be comma-separated integers."
        )

    try:
        seeds = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Seeds must be comma-separated integers."
        ) from exc

    if any(seed < 0 for seed in seeds):
        raise argparse.ArgumentTypeError(
            "Seeds must be zero or positive integers."
        )

    return seeds


def parse_cli_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fixed audit evaluation benchmark.",
    )
    parser.add_argument(
        "--model",
        default="gemma4:e4b",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
    )
    parser.add_argument(
        "--seeds",
        type=parse_seed_list,
        default=None,
        help="Comma-separated integer seeds.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    return parser.parse_args(argv)


def run_cli(argv: list[str] | None = None) -> int:
    args = parse_cli_args(argv)
    seeds = (
        args.seeds
        if args.seeds is not None
        else [None]
    )

    runs: list[dict] = []
    all_scores: list[dict] = []

    for run_index, seed in enumerate(seeds, start=1):
        config = OllamaAuditConfig(
            model=args.model,
            temperature=args.temperature,
            seed=seed,
        )
        model_call = partial(
            run_ollama_audit,
            config=config,
        )

        scores, run_summary = run_evaluation_suite(
            model_call=model_call,
        )

        annotated_scores = [
            {
                **score,
                "run_index": run_index,
                "seed": seed,
            }
            for score in scores
        ]
        all_scores.extend(annotated_scores)

        runs.append(
            {
                "run_index": run_index,
                "seed": seed,
                "summary": run_summary,
                "case_results": annotated_scores,
            }
        )

    summary = summarize_evaluation_scores(all_scores)

    report = {
        "metadata": {
            "model": args.model,
            "temperature": args.temperature,
            "seeds": seeds,
            "run_count": len(seeds),
        },
        "summary": summary,
        "case_stability": summarize_case_stability(
            all_scores
        ),
        "runs": runs,
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "Evaluation completed: "
        f"{summary['passed']}/{summary['total']} passed"
    )
    print(f"Results written to: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
