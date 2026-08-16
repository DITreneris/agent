import pytest

from audit_validator import validate_audit_output

VALID_RESPONSE = """
1. Bottom line
The function is operational.

2. Direct critique
Classification: FALSE_POSITIVE_CANDIDATE
Evidence: EVIDENCE_HIGH
Why: No blocking defect is visible in the provided code.
Missing context: none

3. Better option
Keep the current implementation.

4. Next steps
Recommended action: NO_CHANGE
Test status: NO_TEST_NEEDED
Reason: No change is justified because no visible defect is present.

5. Top 3 pitfalls
1. Model false positives.
2. Format drift.
3. Missing evidence.

6. Verdict
GO

7. Confidence
High.
""".strip()


def test_valid_response_is_accepted():
    result = validate_audit_output(VALID_RESPONSE)

    assert result.valid is True
    assert result.errors == []


def test_empty_response_is_rejected():
    result = validate_audit_output("")

    assert result.valid is False
    assert "Audit response is empty." in result.errors


def test_missing_section_is_rejected():
    response = VALID_RESPONSE.replace(
        "4. Next steps\n"
        "Recommended action: NO_CHANGE\n"
        "Test status: NO_TEST_NEEDED\n"
        "Reason: No change is justified because no visible defect is present.\n\n",
        "",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert "Missing section: '4. Next steps'." in result.errors


def test_content_before_first_section_is_rejected():
    response = "Here is the audit:\n\n" + VALID_RESPONSE

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "Response must start with '1. Bottom line'."
        in result.errors
    )


def test_empty_section_is_rejected():
    response = VALID_RESPONSE.replace(
        "4. Next steps\n"
        "Recommended action: NO_CHANGE\n"
        "Test status: NO_TEST_NEEDED\n"
        "Reason: No change is justified because no visible defect is present.",
        "4. Next steps",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert "Section is empty: '4. Next steps'." in result.errors


def test_duplicate_section_is_rejected():
    response = (
        VALID_RESPONSE
        + "\n\n2. Direct critique\nDuplicate content."
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert "Duplicate section: '2. Direct critique'." in result.errors


def test_forbidden_phrase_is_rejected():
    response = VALID_RESPONSE.replace(
        "High.",
        "High.\nSelf-Correction: none.",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "Forbidden phrase found: 'Self-Correction'."
        in result.errors
    )

def test_non_string_response_is_rejected():
    result = validate_audit_output(None)

    assert result.valid is False
    assert "Audit response must be a string." in result.errors


def test_markdown_inside_sections_is_allowed():
    response = VALID_RESPONSE.replace(
        "The function is operational.",
        "**The function is operational.**",
    )

    result = validate_audit_output(response)

    assert result.valid is True
    assert result.errors == []


def test_leading_whitespace_is_allowed():
    response = "\n\n   " + VALID_RESPONSE

    result = validate_audit_output(response)

    assert result.valid is True
    assert result.errors == []


def test_only_go_is_rejected():
    result = validate_audit_output("GO")

    assert result.valid is False


def test_code_fence_wrapping_is_rejected():
    response = f"```text\n{VALID_RESPONSE}\n```"

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "Response must start with '1. Bottom line'."
        in result.errors
    )

def test_out_of_order_sections_are_rejected():
    response = """1. Bottom line
OK

3. Better option
OK

2. Direct critique
OK

4. Next steps
OK

5. Top 3 pitfalls
OK

6. Verdict
GO

7. Confidence
High
"""

    result = validate_audit_output(response)

    assert result.valid is False
    assert "Required sections are not in the correct order." in result.errors

def test_block_requires_real_bug_with_high_evidence():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: NEEDS_CONTEXT",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nBLOCK",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nHigh",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "BLOCK verdict requires at least one REAL_BUG finding with EVIDENCE_HIGH."
        in result.errors
    )

def test_low_evidence_cannot_have_high_confidence():
    response = VALID_RESPONSE.replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_LOW findings cannot use High confidence."
        in result.errors
    )

def test_needs_context_cannot_have_high_confidence():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: NEEDS_CONTEXT",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "NEEDS_CONTEXT findings cannot use High confidence."
        in result.errors
    )


def test_real_bug_cannot_recommend_no_change():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: REAL_BUG",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        "Why: The visible execution path raises an exception.",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "REAL_BUG finding cannot recommend NO_CHANGE."
        in result.errors
    )


def test_real_bug_cannot_end_with_go_and_no_test_needed():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: REAL_BUG",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        "Why: The visible execution path raises an exception.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: FIX_NOW",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "REAL_BUG finding cannot use GO verdict with NO_TEST_NEEDED."
        in result.errors
    )


def test_medium_evidence_cannot_have_high_confidence():
    response = VALID_RESPONSE.replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_MEDIUM",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_MEDIUM findings cannot use High confidence."
        in result.errors
    )


def test_maintainability_hardening_cannot_recommend_no_change():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: MAINTAINABILITY_HARDENING",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        "Why: A small change would reduce future fragility.",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "MAINTAINABILITY_HARDENING cannot recommend NO_CHANGE."
        in result.errors
    )


def test_hypothetical_future_contract_change_is_rejected():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: MAINTAINABILITY_HARDENING",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        "Why: If the helper were to change its return contract, this function could fail.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: HARDEN_SMALL",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nGO_WITH_NOTES",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "Audit findings cannot rely on hypothetical future dependency changes."
        in result.errors
    )


def test_low_evidence_cannot_recommend_code_change():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: PLAUSIBLE_RISK",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        "Why: A theoretical edge case might exist.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: HARDEN_SMALL",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nGO_WITH_NOTES",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_LOW findings cannot recommend code changes."
        in result.errors
    )


def test_available_helper_signature_cannot_be_reported_as_missing_context():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: PLAUSIBLE_RISK",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_MEDIUM",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: If safe_parse's return type changes, "
            "the target could become fragile."
        ),
    ).replace(
        "Missing context: none",
        (
            "Missing context: The explicit type signature "
            "and return contract for safe_parse."
        ),
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: HARDEN_SMALL",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nGO_WITH_NOTES",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(
        response,
        available_context_names={"safe_parse"},
    )

    assert result.valid is False
    assert (
        "Available helper context cannot be reported as missing: safe_parse."
        in result.errors
    )

def test_available_helper_can_be_discussed_when_missing_context_is_none():
    response = VALID_RESPONSE.replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: safe_parse's explicit type signature is visible "
            "and supports the current implementation."
        ),
    )

    result = validate_audit_output(
        response,
        available_context_names={"safe_parse"},
    )

    assert result.valid is True
    assert (
        "Available helper context cannot be reported as missing: safe_parse."
        not in result.errors
    )


def test_only_low_evidence_findings_cannot_use_go_with_notes():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: PLAUSIBLE_RISK",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        "Why: An alternative external requirement might exist.",
    ).replace(
        "Missing context: none",
        "Missing context: An unspecified external product requirement.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: INSPECT_CONTEXT",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nGO_WITH_NOTES",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "Audits with only EVIDENCE_LOW findings must use GO."
        in result.errors
    )


def test_rejects_claim_that_available_helper_definition_is_not_provided():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: NEEDS_CONTEXT",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: No immediate defect is visible, but the reliance on "
            "safe_parse behavior is unverified."
        ),
    ).replace(
        "Missing context: none",
        "Missing context: The definition or behavior of safe_parse is not provided.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: INSPECT_CONTEXT",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(
        response,
        available_context_names={"safe_parse"},
    )

    assert result.valid is False
    assert (
        "Available helper context cannot be reported as missing: safe_parse."
        in result.errors
    )


def test_rejects_low_evidence_invented_caller_contract():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: NEEDS_CONTEXT",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: The function returns None for empty strings, but the "
            "caller might expect an empty string instead."
        ),
    ).replace(
        "Missing context: none",
        "Missing context: Caller's expected return value for an empty input string.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: INSPECT_CONTEXT",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_LOW findings cannot invent caller or product requirements."
        in result.errors
    )


def test_rejects_low_evidence_unstated_requirement_speculation():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: NEEDS_CONTEXT",
    ).replace(
        "Evidence: EVIDENCE_HIGH",
        "Evidence: EVIDENCE_LOW",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: Returning None might conflict with an unstated "
            "requirement to return an empty string instead."
        ),
    ).replace(
        "Missing context: none",
        "Missing context: The required return value for empty input.",
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: INSPECT_CONTEXT",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "7. Confidence\nHigh.",
        "7. Confidence\nMedium",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_LOW findings cannot invent caller or product requirements."
        in result.errors
    )


def test_high_evidence_cannot_rely_on_hypothetical_requirement():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: PLAUSIBLE_RISK",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: Returning 0 could hide an invalid discount code "
            "if 0 is not the desired default."
        ),
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: HARDEN_SMALL",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nGO_WITH_NOTES",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_HIGH findings cannot rely on hypothetical caller "
        "or product requirements."
        in result.errors
    )


def test_high_evidence_can_describe_visible_conditional_behavior():
    response = VALID_RESPONSE.replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            "Why: If the required field is absent, "
            "the visible code raises ValueError."
        ),
    )

    result = validate_audit_output(response)

    assert result.valid is True

def test_high_evidence_hypothetical_requirement_ignores_quotes():
    response = VALID_RESPONSE.replace(
        "Classification: FALSE_POSITIVE_CANDIDATE",
        "Classification: PLAUSIBLE_RISK",
    ).replace(
        "Why: No blocking defect is visible in the provided code.",
        (
            'Why: Returning 0 could hide an invalid discount code '
            'if "0" is not the desired default.'
        ),
    ).replace(
        "Recommended action: NO_CHANGE",
        "Recommended action: HARDEN_SMALL",
    ).replace(
        "Test status: NO_TEST_NEEDED",
        "Test status: POSSIBLE_TEST_GAP",
    ).replace(
        "6. Verdict\nGO",
        "6. Verdict\nGO_WITH_NOTES",
    )

    result = validate_audit_output(response)

    assert result.valid is False
    assert (
        "EVIDENCE_HIGH findings cannot rely on hypothetical caller "
        "or product requirements."
        in result.errors
    )


@pytest.mark.parametrize(
    ("valid_fragment", "invalid_fragment"),
    [
        (
            "Classification: FALSE_POSITIVE_CANDIDATE",
            "Classification: BANANA",
        ),
        (
            "Evidence: EVIDENCE_HIGH",
            "Evidence: CERTAIN",
        ),
        (
            "Recommended action: NO_CHANGE",
            "Recommended action: SHIP_IT",
        ),
        (
            "Test status: NO_TEST_NEEDED",
            "Test status: MAYBE",
        ),
        (
            "6. Verdict\nGO",
            "6. Verdict\nAPPROVE",
        ),
        (
            "7. Confidence\nHigh.",
            "7. Confidence\nVery High.",
        ),
    ],
)
def test_invalid_contract_value_is_rejected(
    valid_fragment,
    invalid_fragment,
):
    response = VALID_RESPONSE.replace(
        valid_fragment,
        invalid_fragment,
    )

    result = validate_audit_output(response)

    assert result.valid is False
