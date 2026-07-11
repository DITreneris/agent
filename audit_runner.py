from collections.abc import Callable
from dataclasses import dataclass

from audit_validator import validate_audit_output

REPAIR_PROMPT = """
Rewrite the previous audit response so that it follows the exact required format.

Use exactly these seven headings in this order:

1. Bottom line
2. Direct critique
3. Better option
4. Next steps
5. Top 3 pitfalls
6. Verdict
7. Confidence

Requirements:
- Start exactly with "1. Bottom line".
- Use every heading exactly as written.
- Do not leave any section empty.
- In section 2, include the exact labels:
  - Classification:
  - Evidence:
  - Why:
  - Missing context:
- In section 4, include the exact labels:
  - Recommended action:
  - Test status:
  - Reason:
- Do not use "Action:" instead of "Recommended action:".
- Do not use "Test:" instead of "Test status:".
- Classification must be one of: REAL_BUG, PLAUSIBLE_RISK, FALSE_POSITIVE_CANDIDATE, MAINTAINABILITY_HARDENING, PRODUCT_INSIGHT, TEST_GAP, NEEDS_CONTEXT.
- Evidence must be one of: EVIDENCE_HIGH, EVIDENCE_MEDIUM, EVIDENCE_LOW.
- Recommended action must be one of: NO_CHANGE, DO_NOT_FIX, INSPECT_CONTEXT, HARDEN_SMALL, ADD_TEST_CONFIRMED, FIX_NOW, REFACTOR_LATER.
- Test status must be one of: ADD_TEST_CONFIRMED, POSSIBLE_TEST_GAP, TEST_ALREADY_EXISTS, NO_TEST_NEEDED.
- In section 6, return exactly one of: GO, GO_WITH_NOTES, BLOCK.
- In section 7, return exactly one of: High, Medium, Low.
- Use High confidence only when the finding is directly provable from visible code.
- Use Medium or Low confidence when the finding depends on missing imports, callers, runtime state, or test context.
- Do not add text before section 1 or after section 7.
- Do not use the phrase "Self-Correction".
- Preserve evidence-based technical findings.
- Do not invent new issues.
- If the previous response made a context-dependent claim without visible proof, downgrade it to PLAUSIBLE_RISK or NEEDS_CONTEXT.

Previous response:
{response}
""".strip()


@dataclass
class ValidatedAuditResult:
    success: bool
    response: str | None
    errors: list[str]
    retry_used: bool


def run_validated_audit(
    initial_prompt: str,
    model_call: Callable[[str], str],
) -> ValidatedAuditResult:
    first_response = model_call(initial_prompt)

    first_validation = validate_audit_output(first_response)

    if first_validation.valid:
        return ValidatedAuditResult(
            success=True,
            response=first_response.strip(),
            errors=[],
            retry_used=False,
        )

    repair_prompt = REPAIR_PROMPT.format(
        response=first_response,
    )

    second_response = model_call(repair_prompt)
    second_validation = validate_audit_output(second_response)

    if second_validation.valid:
        return ValidatedAuditResult(
            success=True,
            response=second_response.strip(),
            errors=[],
            retry_used=True,
        )

    return ValidatedAuditResult(
        success=False,
        response=second_response.strip(),
        errors=second_validation.errors,
        retry_used=True,
    )
