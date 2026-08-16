from audit_runner import run_validated_audit
from test_audit_validator import VALID_RESPONSE


def test_valid_first_response_does_not_retry():
    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return VALID_RESPONSE

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is True
    assert result.response == VALID_RESPONSE
    assert result.errors == []
    assert result.retry_used is False
    assert len(calls) == 1


def test_invalid_first_response_is_retried_once():
    responses = iter(
        [
            "Invalid response",
            VALID_RESPONSE,
        ]
    )

    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return next(responses)

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is True
    assert result.response == VALID_RESPONSE
    assert result.errors == []
    assert result.retry_used is True
    assert len(calls) == 2
    assert "Previous response:" not in calls[1]
    assert "Invalid response" not in calls[1]
    assert "Response must start with '1. Bottom line'." in calls[1]


def test_second_invalid_response_is_rejected():
    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return "Invalid response"

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is False
    assert result.response == "Invalid response"
    assert result.errors
    assert result.retry_used is True
    assert len(calls) == 2



def test_retry_preserves_both_attempts_and_validation_errors():
    responses = iter(
        [
            "Invalid first response",
            "Invalid retry response",
        ]
    )

    def model_call(prompt: str) -> str:
        return next(responses)

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=model_call,
    )

    assert result.success is False
    assert result.retry_used is True

    assert result.first_response == "Invalid first response"
    assert result.first_validation_errors

    assert result.retry_response == "Invalid retry response"
    assert result.retry_validation_errors

    assert result.response == result.retry_response
    assert result.errors == result.retry_validation_errors



def test_retry_is_not_run_more_than_once():
    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return "Still invalid"

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is False
    assert result.response == "Still invalid"
    assert result.retry_used is True
    assert len(calls) == 2


def test_repair_prompt_is_compact_and_keeps_calibration_rules():
    from audit_runner import REPAIR_PROMPT

    assert len(REPAIR_PROMPT) < 1800
    assert (
        "Do not invent alternative business rules, caller expectations,"
        in REPAIR_PROMPT
    )
    assert (
        "Treat an explicit branch that maps None to a concrete value"
        in REPAIR_PROMPT
    )
    assert "Use provided helper behavior as available context" in REPAIR_PROMPT
    assert "Classification: FALSE_POSITIVE_CANDIDATE" in REPAIR_PROMPT
    assert (
        "Do not combine MAINTAINABILITY_HARDENING or PLAUSIBLE_RISK"
        in REPAIR_PROMPT
    )


def test_retry_prompt_includes_first_validation_errors():
    prompts = []

    invalid_response = """
1. Bottom line
Potential issue.

2. Direct critique
Classification: PLAUSIBLE_RISK
Evidence: EVIDENCE_LOW
Why: A theoretical issue may exist.
Missing context: caller

3. Better option
Change the code.

4. Next steps
Recommended action: HARDEN_SMALL
Test status: POSSIBLE_TEST_GAP
Reason: Add defensive handling.

5. Top 3 pitfalls
No grounded pitfalls are visible.

6. Verdict
GO_WITH_NOTES

7. Confidence
Medium
""".strip()

    def model_call(prompt: str) -> str:
        prompts.append(prompt)
        return invalid_response

    result = run_validated_audit(
        initial_prompt="Initial audit prompt",
        model_call=model_call,
    )

    assert result.success is False
    assert len(prompts) == 2
    assert (
        "EVIDENCE_LOW findings cannot recommend code changes."
        in prompts[1]
    )


def test_runner_passes_available_context_names_to_validator():
    prompts = []

    invalid_response = """
1. Bottom line
Potential helper contract risk.

2. Direct critique
Classification: PLAUSIBLE_RISK
Evidence: EVIDENCE_MEDIUM
Why: The target depends on safe_parse.
Missing context: The explicit type signature and return contract for safe_parse.

3. Better option
Harden the target.

4. Next steps
Recommended action: HARDEN_SMALL
Test status: POSSIBLE_TEST_GAP
Reason: Defensively handle the helper result.

5. Top 3 pitfalls
1. Helper contract drift.

6. Verdict
GO_WITH_NOTES

7. Confidence
Medium
""".strip()

    def model_call(prompt: str) -> str:
        prompts.append(prompt)
        return invalid_response

    result = run_validated_audit(
        initial_prompt="Initial audit prompt",
        model_call=model_call,
        available_context_names={"safe_parse"},
    )

    assert result.success is False
    assert (
        "Available helper context cannot be reported as missing: safe_parse."
        in result.errors
    )


def test_repair_prompt_maps_only_low_evidence_to_go():
    from audit_runner import REPAIR_PROMPT

    assert "If every finding uses EVIDENCE_LOW" in REPAIR_PROMPT
    assert (
        "Recommended action: NO_CHANGE or INSPECT_CONTEXT"
        in REPAIR_PROMPT
    )
    assert "and Verdict: GO" in REPAIR_PROMPT
    assert (
        "When this validation error is present"
        not in REPAIR_PROMPT
    )


def test_retry_prompt_includes_original_audit_prompt():
    responses = iter(
        [
            "Invalid response",
            VALID_RESPONSE,
        ]
    )
    prompts = []

    def model_call(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    original_prompt = (
        "ORIGINAL_AUDIT_CONTEXT: audit calculate_discount "
        "with the visible find_discount helper."
    )

    result = run_validated_audit(
        initial_prompt=original_prompt,
        model_call=model_call,
    )

    assert result.success is True
    assert result.retry_used is True
    assert len(prompts) == 2
    assert original_prompt in prompts[1]


def test_repair_prompt_requires_standalone_audit():
    from audit_runner import REPAIR_PROMPT

    normalized_prompt = " ".join(REPAIR_PROMPT.split())

    assert "The final audit must stand alone." in normalized_prompt
    assert (
        "Do not mention the previous audit, previous response, "
        "validation errors, retry, repair, or formatting correction."
        in normalized_prompt
    )


def test_repair_prompt_ends_with_complete_section_contract():
    from audit_runner import REPAIR_PROMPT

    expected_ending = """Keep the complete answer concise so all seven sections fit.
Section 6 value: GO, GO_WITH_NOTES, or BLOCK.
Section 7 value: High, Medium, or Low."""

    assert REPAIR_PROMPT.rstrip().endswith(expected_ending)
