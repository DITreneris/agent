from collections.abc import Callable
from dataclasses import dataclass, field

from audit_validator import validate_audit_output

REPAIR_PROMPT = """
Create a new standalone audit from the original audit request below.
The final audit must stand alone.
Do not mention the previous audit, previous response, validation errors,
retry, repair, or formatting correction.

Original audit request:
{initial_prompt}

Validation errors to correct:
{validation_errors}

Correction rules:
- Correct the listed errors without inventing new findings.
- Use only current behavior proven by visible code and context.
- Do not invent alternative business rules, caller expectations,
  missing contracts, or future dependency changes.
- Use provided helper behavior as available context.
- Treat an explicit branch that maps None to a concrete value as
  visible current behavior.
- Do not combine MAINTAINABILITY_HARDENING or PLAUSIBLE_RISK
  with Recommended action: NO_CHANGE.
- If no grounded practical risk remains, use
  Classification: FALSE_POSITIVE_CANDIDATE,
  Evidence: EVIDENCE_HIGH, Missing context: none,
  Recommended action: NO_CHANGE, Test status: NO_TEST_NEEDED,
  and Verdict: GO.
- If every finding uses EVIDENCE_LOW, use
  Recommended action: NO_CHANGE or INSPECT_CONTEXT,
  Test status: NO_TEST_NEEDED unless a concrete missing test is visible,
  and Verdict: GO.
- Follow every exact label requirement in the original audit request.

Return exactly these seven non-empty sections and no other text:
1. Bottom line
2. Direct critique
3. Better option
4. Next steps
5. Top 3 pitfalls
6. Verdict
7. Confidence

Keep the complete answer concise so all seven sections fit.
Section 6 value: GO, GO_WITH_NOTES, or BLOCK.
Section 7 value: High, Medium, or Low.
""".strip()


@dataclass
class ValidatedAuditResult:
    success: bool
    response: str | None
    errors: list[str]
    retry_used: bool
    first_response: str | None = None
    first_validation_errors: list[str] = field(
        default_factory=list
    )
    retry_response: str | None = None
    retry_validation_errors: list[str] = field(
        default_factory=list
    )
    retry_prompt: str | None = None


def run_validated_audit(
    initial_prompt: str,
    model_call: Callable[[str], str],
    available_context_names: set[str] | None = None,
) -> ValidatedAuditResult:
    first_response = model_call(initial_prompt)

    first_validation = validate_audit_output(
        first_response,
        available_context_names=available_context_names,
    )

    if first_validation.valid:
        return ValidatedAuditResult(
            success=True,
            response=first_response.strip(),
            errors=[],
            retry_used=False,
            first_response=first_response.strip(),
            first_validation_errors=[],
            retry_response=None,
            retry_validation_errors=[],
            retry_prompt=None,
        )

    validation_errors = "\n".join(
        f"- {error}"
        for error in first_validation.errors
    )

    repair_prompt = REPAIR_PROMPT.format(
        initial_prompt=initial_prompt,
        validation_errors=validation_errors,
    )

    second_response = model_call(repair_prompt)
    second_validation = validate_audit_output(
        second_response,
        available_context_names=available_context_names,
    )

    if second_validation.valid:
        return ValidatedAuditResult(
            success=True,
            response=second_response.strip(),
            errors=[],
            retry_used=True,
            first_response=first_response.strip(),
            first_validation_errors=list(
                first_validation.errors
            ),
            retry_response=second_response.strip(),
            retry_validation_errors=[],
            retry_prompt=repair_prompt,
        )

    return ValidatedAuditResult(
        success=False,
        response=second_response.strip(),
        errors=list(second_validation.errors),
        retry_used=True,
        first_response=first_response.strip(),
        first_validation_errors=list(
            first_validation.errors
        ),
        retry_response=second_response.strip(),
        retry_validation_errors=list(
            second_validation.errors
        ),
        retry_prompt=repair_prompt,
    )
