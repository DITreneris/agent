from audit_validator import validate_audit_output


VALID_RESPONSE = """
1. Bottom line
The function is operational.

2. Direct critique
No blocking defect is visible.

3. Better option
Keep the current implementation.

4. Next steps
Run regression tests.

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
        "4. Next steps\nRun regression tests.\n\n",
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
        "4. Next steps\nRun regression tests.",
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
