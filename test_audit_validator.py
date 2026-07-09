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
