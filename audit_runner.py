from collections.abc import Callable
from dataclasses import dataclass, field

from audit_validator import validate_audit_output

REPAIR_PROMPT = """
Create a new standalone audit from the original request and visible code.
The final audit must stand alone.
Do not mention the previous audit, previous response, validation errors, retry, repair, or formatting correction.

Return exactly these seven non-empty sections:
1. Bottom line
2. Direct critique
3. Better option
4. Next steps
5. Top 3 pitfalls
6. Verdict
7. Confidence

Section 2 must contain:
Classification: <one allowed value>
Evidence: <one allowed value>
Why: <grounded explanation>
Missing context: <specific missing artifact or none>

Allowed classifications:
REAL_BUG, PLAUSIBLE_RISK, FALSE_POSITIVE_CANDIDATE,
MAINTAINABILITY_HARDENING, PRODUCT_INSIGHT, TEST_GAP,
NEEDS_CONTEXT.

Allowed evidence:
EVIDENCE_HIGH, EVIDENCE_MEDIUM, EVIDENCE_LOW.

Section 4 must contain:
Recommended action: <one allowed value>
Test status: <one allowed value>
Reason: <grounded explanation>

Allowed actions:
NO_CHANGE, DO_NOT_FIX, INSPECT_CONTEXT, HARDEN_SMALL,
ADD_TEST_CONFIRMED, FIX_NOW, REFACTOR_LATER.

Allowed test statuses:
ADD_TEST_CONFIRMED, POSSIBLE_TEST_GAP, TEST_ALREADY_EXISTS,
NO_TEST_NEEDED.

Section 6 must be exactly one of:
GO, GO_WITH_NOTES, BLOCK.

Section 7 must be exactly one of:
High, Medium, Low.

Calibration rules:
- Use only facts supported by the visible code and context.
- Do not invent business rules, caller expectations, or future changes.
- Unknown or hypothetical caller expectations are not missing context.
- If provided helper context shows the helper's behavior, use it.
- An explicit branch that maps None to a concrete value is visible behavior.
- MAINTAINABILITY_HARDENING cannot be combined with NO_CHANGE.
- PLAUSIBLE_RISK cannot be combined with NO_CHANGE.
- If no code change is justified and no specific necessary artifact is absent, use
  FALSE_POSITIVE_CANDIDATE, NO_CHANGE, NO_TEST_NEEDED, and GO.
- If no grounded practical risk remains, use GO.
- Do not preserve hypothetical future dependency changes.
- Audits with only EVIDENCE_LOW findings must use GO.
- When this validation error is present, change the verdict to GO.
- For only EVIDENCE_LOW findings, use Recommended action: NO_CHANGE or INSPECT_CONTEXT.
- Do not invent an alternative business rule.
- Do not mention validation, retry, repair, or any earlier response.
- Do not add text before section 1 or after section 7.

Original audit request and visible code:
{initial_prompt}

Errors that the new audit must resolve:
{validation_errors}

FINAL VALIDATION OVERRIDE:
If every finding uses EVIDENCE_LOW:
- Verdict must be GO.
- Recommended action must be NO_CHANGE or INSPECT_CONTEXT.
- Use NO_TEST_NEEDED unless a concrete missing test is visible.
- Do not use GO_WITH_NOTES.
- Do not invent missing caller, product, type, or error-handling requirements.
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
    )
