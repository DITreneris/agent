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
- In section 6, return exactly one of: GO, GO_WITH_NOTES, BLOCK.
- In section 7, return exactly one of: High, Medium, Low.
- Do not add text before section 1 or after section 7.
- Do not use the phrase "Self-Correction".
- Preserve evidence-based technical findings.
- Do not invent new issues.

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
        response=None,
        errors=second_validation.errors,
        retry_used=True,
    )
