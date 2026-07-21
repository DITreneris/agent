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


def test_repair_prompt_includes_semantic_contradiction_rules():
    from audit_runner import REPAIR_PROMPT

    assert (
        "MAINTAINABILITY_HARDENING cannot be combined with NO_CHANGE"
        in REPAIR_PROMPT
    )
    assert (
        "If no code change is justified and no specific necessary artifact is absent"
        in REPAIR_PROMPT
    )
    assert "Unknown or hypothetical caller expectations" in REPAIR_PROMPT
    assert "If provided helper context shows the helper's behavior" in REPAIR_PROMPT
    assert "An explicit branch that maps None" in REPAIR_PROMPT

    assert (
        "If no grounded practical risk remains, use GO"
        in REPAIR_PROMPT
    )
    assert (
        "Do not preserve hypothetical future dependency changes"
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


def test_repair_prompt_maps_only_low_evidence_error_to_go():
    from audit_runner import REPAIR_PROMPT

    assert (
        "Audits with only EVIDENCE_LOW findings must use GO"
        in REPAIR_PROMPT
    )
    assert (
        "When this validation error is present, change the verdict to GO"
        in REPAIR_PROMPT
    )
    assert (
        "use Recommended action: NO_CHANGE or INSPECT_CONTEXT"
        in REPAIR_PROMPT
    )
    assert (
        "Do not invent an alternative business rule"
        in REPAIR_PROMPT
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

    assert "The final audit must stand alone." in REPAIR_PROMPT
    assert (
        "Do not mention the previous audit, previous response, "
        "validation errors, retry, repair, or formatting correction"
        in REPAIR_PROMPT
    )


def test_repair_prompt_ends_with_low_evidence_override():
    from audit_runner import REPAIR_PROMPT

    expected_ending = """FINAL VALIDATION OVERRIDE:
If every finding uses EVIDENCE_LOW:
- Verdict must be GO.
- Recommended action must be NO_CHANGE or INSPECT_CONTEXT.
- Use NO_TEST_NEEDED unless a concrete missing test is visible.
- Do not use GO_WITH_NOTES.
- Do not invent missing caller, product, type, or error-handling requirements."""

    assert REPAIR_PROMPT.rstrip().endswith(expected_ending)
