from dataclasses import dataclass, field


REQUIRED_SECTIONS = [
    "1. Bottom line",
    "2. Direct critique",
    "3. Better option",
    "4. Next steps",
    "5. Top 3 pitfalls",
    "6. Verdict",
    "7. Confidence",
]

FORBIDDEN_PHRASES = [
    "Self-Correction",
    "Additional analysis",
]

SECTION_2_REQUIRED_LABELS = [
    "Classification:",
    "Evidence:",
    "Why:",
    "Missing context:",
]

SECTION_4_REQUIRED_LABELS = [
    "Recommended action:",
    "Test status:",
    "Reason:",
]

@dataclass
class AuditValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def _extract_section_content(
    response: str,
    current_heading: str,
    next_heading: str | None,
) -> str:
    """Extract the text between the current and next section headings."""

    start = response.find(current_heading)

    if start == -1:
        return ""

    content_start = start + len(current_heading)

    if next_heading is None:
        return response[content_start:].strip()

    end = response.find(next_heading, content_start)

    if end == -1:
        return ""

    return response[content_start:end].strip()

def _require_labels_in_section(
    content: str,
    labels: list[str],
    section: str,
    errors: list[str],
) -> None:
    for label in labels:
        if label not in content:
            errors.append(f"Missing required label in {section}: '{label}'.")

def validate_audit_output(response: str) -> AuditValidationResult:
    """Validate that an audit response follows the required output contract."""

    if not isinstance(response, str):
        return AuditValidationResult(
            valid=False,
            errors=["Audit response must be a string."],
        )

    cleaned = response.strip()
    errors: list[str] = []

    if not cleaned:
        return AuditValidationResult(
            valid=False,
            errors=["Audit response is empty."],
        )

    # The response must start with the first required section.
    if not cleaned.startswith(REQUIRED_SECTIONS[0]):
        errors.append(
            f"Response must start with '{REQUIRED_SECTIONS[0]}'."
        )

    # Check whether every section exists exactly once.
    for section in REQUIRED_SECTIONS:
        count = cleaned.count(section)

        if count == 0:
            errors.append(f"Missing section: '{section}'.")

        elif count > 1:
            errors.append(f"Duplicate section: '{section}'.")

    # Check that existing sections appear in the correct order.
    section_positions: list[int] = []

    for section in REQUIRED_SECTIONS:
        position = cleaned.find(section)

        if position >= 0:
            section_positions.append(position)

    if section_positions != sorted(section_positions):
        errors.append("Required sections are not in the correct order.")

    # Check that every existing section contains content.
    for index, section in enumerate(REQUIRED_SECTIONS):
        if section not in cleaned:
            continue

        next_section = (
            REQUIRED_SECTIONS[index + 1]
            if index + 1 < len(REQUIRED_SECTIONS)
            else None
        )

        content = _extract_section_content(
            cleaned,
            section,
            next_section,
        )

        if not content:
            errors.append(f"Section is empty: '{section}'.")

    if "2. Direct critique" in cleaned and "3. Better option" in cleaned:
        direct_critique = _extract_section_content(
            cleaned,
            "2. Direct critique",
            "3. Better option",
        )
        _require_labels_in_section(
            direct_critique,
            SECTION_2_REQUIRED_LABELS,
            "2. Direct critique",
            errors,
        )

    if "4. Next steps" in cleaned and "5. Top 3 pitfalls" in cleaned:
        next_steps = _extract_section_content(
            cleaned,
            "4. Next steps",
            "5. Top 3 pitfalls",
        )
        _require_labels_in_section(
            next_steps,
            SECTION_4_REQUIRED_LABELS,
            "4. Next steps",
            errors,
        )

    # Reject known unwanted phrases.
    cleaned_lower = cleaned.lower()

    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in cleaned_lower:
            errors.append(f"Forbidden phrase found: '{phrase}'.")

    return AuditValidationResult(
        valid=len(errors) == 0,
        errors=errors,
    )
