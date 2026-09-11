from dataclasses import dataclass, field
import re


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


ALLOWED_CLASSIFICATIONS = {
    "REAL_BUG",
    "PLAUSIBLE_RISK",
    "FALSE_POSITIVE_CANDIDATE",
    "MAINTAINABILITY_HARDENING",
    "PRODUCT_INSIGHT",
    "TEST_GAP",
    "NEEDS_CONTEXT",
}

ALLOWED_EVIDENCE_LEVELS = {
    "EVIDENCE_HIGH",
    "EVIDENCE_MEDIUM",
    "EVIDENCE_LOW",
}

ALLOWED_ACTIONS = {
    "NO_CHANGE",
    "DO_NOT_FIX",
    "INSPECT_CONTEXT",
    "HARDEN_SMALL",
    "ADD_TEST_CONFIRMED",
    "FIX_NOW",
    "REFACTOR_LATER",
}

ALLOWED_TEST_STATUSES = {
    "ADD_TEST_CONFIRMED",
    "POSSIBLE_TEST_GAP",
    "TEST_ALREADY_EXISTS",
    "NO_TEST_NEEDED",
}

ALLOWED_VERDICTS = {
    "GO",
    "GO_WITH_NOTES",
    "BLOCK",
}

ALLOWED_CONFIDENCE_LEVELS = {
    "High",
    "Medium",
    "Low",
}

BLOCK_REQUIRES_ERROR = (
    "BLOCK verdict requires at least one REAL_BUG finding with EVIDENCE_HIGH."
)

LOW_EVIDENCE_HIGH_CONFIDENCE_ERROR = (
    "EVIDENCE_LOW findings cannot use High confidence."
)

NEEDS_CONTEXT_HIGH_CONFIDENCE_ERROR = (
    "NEEDS_CONTEXT findings cannot use High confidence."
)

MEDIUM_EVIDENCE_HIGH_CONFIDENCE_ERROR = (
    "EVIDENCE_MEDIUM findings cannot use High confidence."
)

MAINTAINABILITY_NO_CHANGE_ERROR = (
    "MAINTAINABILITY_HARDENING cannot recommend NO_CHANGE."
)

HYPOTHETICAL_DEPENDENCY_CHANGE_ERROR = (
    "Audit findings cannot rely on hypothetical future dependency changes."
)

LOW_EVIDENCE_CODE_CHANGE_ERROR = (
    "EVIDENCE_LOW findings cannot recommend code changes."
)

ONLY_LOW_EVIDENCE_GO_ERROR = (
    "Audits with only EVIDENCE_LOW findings must use GO."
)

LOW_EVIDENCE_INVENTED_REQUIREMENT_ERROR = (
    "EVIDENCE_LOW findings cannot invent caller or product requirements."
)

HIGH_EVIDENCE_HYPOTHETICAL_REQUIREMENT_ERROR = (
    "EVIDENCE_HIGH findings cannot rely on hypothetical caller "
    "or product requirements."
)

REAL_BUG_NO_CHANGE_ERROR = (
    "REAL_BUG finding cannot recommend NO_CHANGE."
)

REAL_BUG_GO_NO_TEST_ERROR = (
    "REAL_BUG finding cannot use GO verdict with NO_TEST_NEEDED."
)

QUOTE_STRIP_TABLE = str.maketrans("", "", "\"'`“”‘’")

LOW_EVIDENCE_INVENTION_MARKERS = (
    "caller might expect",
    "caller expects",
    "caller's expected",
    "business rule",
    "product requirement",
    "required behavior",
    "should it be",
    "if the goal is",
    "if the contract requires",
    "if the upstream contract expects",
    "unstated requirement",
)

HYPOTHETICAL_REQUIREMENT_MARKERS = (
    "if the caller expects",
    "if callers expect",
    "if the product requires",
    "if the business rule requires",
    "if the contract requires",
    "if this is not the desired",
    "if that is not the desired",
    "if 0 is not the desired",
)

CODE_CHANGE_ACTIONS = [
    "Recommended action: HARDEN_SMALL",
    "Recommended action: FIX_NOW",
    "Recommended action: REFACTOR_LATER",
    "Recommended action: ADD_TEST_CONFIRMED",
]


@dataclass
class AuditValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class AuditFinding:
    classification: str
    evidence: str
    why: str
    missing_context: str


def _normalize_contract_line(line: str) -> str:
    normalized = line.strip()

    if normalized.startswith("- "):
        normalized = normalized[2:].strip()

    return normalized


def _value_after_label(line: str, label: str) -> str | None:
    prefix = f"{label}:"
    normalized = _normalize_contract_line(line)

    if not normalized.startswith(prefix):
        return None

    return normalized[len(prefix):].strip()


def _extract_findings(direct_critique: str) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    current: dict[str, str] | None = None
    last_field: str | None = None

    def flush() -> None:
        nonlocal current

        if current is None:
            return

        findings.append(
            AuditFinding(
                classification=current.get("classification", ""),
                evidence=current.get("evidence", ""),
                why=current.get("why", ""),
                missing_context=current.get("missing_context", ""),
            )
        )
        current = None

    for line in direct_critique.splitlines():
        classification = _value_after_label(line, "Classification")
        if classification is not None:
            flush()
            current = {
                "classification": classification,
                "evidence": "",
                "why": "",
                "missing_context": "",
            }
            last_field = "classification"
            continue

        if current is None:
            continue

        evidence = _value_after_label(line, "Evidence")
        if evidence is not None:
            current["evidence"] = evidence
            last_field = "evidence"
            continue

        why = _value_after_label(line, "Why")
        if why is not None:
            current["why"] = why
            last_field = "why"
            continue

        missing_context = _value_after_label(line, "Missing context")
        if missing_context is not None:
            current["missing_context"] = missing_context
            last_field = "missing_context"
            continue

        normalized = _normalize_contract_line(line)
        if last_field == "why" and normalized:
            current["why"] = f"{current['why']} {normalized}".strip()

    flush()
    return findings


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

def _extract_verdict(response: str) -> str:
    verdict_content = _extract_section_content(
        response,
        "6. Verdict",
        "7. Confidence",
    )

    return verdict_content.strip().rstrip(".")


def _extract_confidence(response: str) -> str:
    confidence_content = _extract_section_content(
        response,
        "7. Confidence",
        None,
    )

    return confidence_content.strip().rstrip(".")


def _validate_labeled_values(
    content: str,
    label: str,
    allowed_values: set[str],
    section: str,
    errors: list[str],
) -> None:
    values: list[str] = []

    for line in content.splitlines():
        value = _value_after_label(line, label)
        if value is not None:
            values.append(value)

    for value in values:
        if value not in allowed_values:
            errors.append(
                f"Invalid {label} value in {section}: '{value}'."
            )


def _validate_contract_values(
    cleaned: str,
    errors: list[str],
) -> None:
    direct_critique = _extract_section_content(
        cleaned,
        "2. Direct critique",
        "3. Better option",
    )
    next_steps = _extract_section_content(
        cleaned,
        "4. Next steps",
        "5. Top 3 pitfalls",
    )

    _validate_labeled_values(
        direct_critique,
        "Classification",
        ALLOWED_CLASSIFICATIONS,
        "2. Direct critique",
        errors,
    )
    _validate_labeled_values(
        direct_critique,
        "Evidence",
        ALLOWED_EVIDENCE_LEVELS,
        "2. Direct critique",
        errors,
    )
    _validate_labeled_values(
        next_steps,
        "Recommended action",
        ALLOWED_ACTIONS,
        "4. Next steps",
        errors,
    )
    _validate_labeled_values(
        next_steps,
        "Test status",
        ALLOWED_TEST_STATUSES,
        "4. Next steps",
        errors,
    )

    verdict = _extract_verdict(cleaned)

    if verdict not in ALLOWED_VERDICTS:
        errors.append(f"Invalid Verdict value: '{verdict}'.")

    confidence = _extract_confidence(cleaned)

    if confidence not in ALLOWED_CONFIDENCE_LEVELS:
        errors.append(f"Invalid Confidence value: '{confidence}'.")


def _has_real_bug_high_evidence(
    findings: list[AuditFinding],
    cleaned: str,
) -> bool:
    if findings:
        return any(
            finding.classification == "REAL_BUG"
            and finding.evidence == "EVIDENCE_HIGH"
            for finding in findings
        )

    return (
        "Classification: REAL_BUG" in cleaned
        and "Evidence: EVIDENCE_HIGH" in cleaned
    )


def _has_only_low_evidence(
    findings: list[AuditFinding],
    direct_critique: str,
) -> bool:
    if findings:
        return all(
            finding.evidence == "EVIDENCE_LOW"
            for finding in findings
        )

    evidence_values = [
        _value_after_label(line, "Evidence")
        for line in direct_critique.splitlines()
    ]
    evidence_values = [
        value
        for value in evidence_values
        if value is not None
    ]

    return bool(evidence_values) and all(
        value == "EVIDENCE_LOW"
        for value in evidence_values
    )


def _recommends_code_change(cleaned: str) -> bool:
    return any(
        action in cleaned
        for action in CODE_CHANGE_ACTIONS
    )


def _normalize_why(text: str) -> str:
    return text.lower().translate(QUOTE_STRIP_TABLE)


def _validate_finding_hypothetical_markers(
    findings: list[AuditFinding],
    errors: list[str],
) -> None:
    high_evidence_error_added = False
    low_evidence_error_added = False

    for finding in findings:
        why_lower = finding.why.lower()
        normalized_why = _normalize_why(finding.why)

        if (
            not high_evidence_error_added
            and finding.evidence == "EVIDENCE_HIGH"
            and any(
                marker in normalized_why
                for marker in HYPOTHETICAL_REQUIREMENT_MARKERS
            )
        ):
            errors.append(
                HIGH_EVIDENCE_HYPOTHETICAL_REQUIREMENT_ERROR
            )
            high_evidence_error_added = True

        if (
            not low_evidence_error_added
            and finding.evidence == "EVIDENCE_LOW"
            and any(
                marker in why_lower
                for marker in LOW_EVIDENCE_INVENTION_MARKERS
            )
        ):
            errors.append(LOW_EVIDENCE_INVENTED_REQUIREMENT_ERROR)
            low_evidence_error_added = True


def _validate_substring_hypothetical_markers(
    direct_critique: str,
    cleaned: str,
    errors: list[str],
) -> None:
    high_evidence = "Evidence: EVIDENCE_HIGH" in cleaned
    low_evidence = "Evidence: EVIDENCE_LOW" in cleaned
    normalized_direct_critique = _normalize_why(direct_critique)

    if high_evidence and any(
        marker in normalized_direct_critique
        for marker in HYPOTHETICAL_REQUIREMENT_MARKERS
    ):
        errors.append(
            HIGH_EVIDENCE_HYPOTHETICAL_REQUIREMENT_ERROR
        )

    if low_evidence and any(
        marker in direct_critique.lower()
        for marker in LOW_EVIDENCE_INVENTION_MARKERS
    ):
        errors.append(LOW_EVIDENCE_INVENTED_REQUIREMENT_ERROR)


def _validate_calibration_contract(
    cleaned: str,
    errors: list[str],
) -> None:
    verdict = _extract_verdict(cleaned)
    confidence = _extract_confidence(cleaned)
    direct_critique = _extract_section_content(
        cleaned,
        "2. Direct critique",
        "3. Better option",
    )
    findings = _extract_findings(direct_critique)

    has_real_bug_high_evidence = _has_real_bug_high_evidence(
        findings,
        cleaned,
    )

    if verdict == "BLOCK" and not has_real_bug_high_evidence:
        errors.append(BLOCK_REQUIRES_ERROR)

    if "Evidence: EVIDENCE_LOW" in cleaned and confidence == "High":
        errors.append(LOW_EVIDENCE_HIGH_CONFIDENCE_ERROR)

    has_only_low_evidence = _has_only_low_evidence(
        findings,
        direct_critique,
    )

    if findings:
        should_reject_low_code_change = has_only_low_evidence
    else:
        should_reject_low_code_change = (
            "Evidence: EVIDENCE_LOW" in cleaned
        )

    if (
        should_reject_low_code_change
        and _recommends_code_change(cleaned)
    ):
        errors.append(LOW_EVIDENCE_CODE_CHANGE_ERROR)

    if has_only_low_evidence and verdict != "GO":
        errors.append(ONLY_LOW_EVIDENCE_GO_ERROR)

    if findings:
        _validate_finding_hypothetical_markers(findings, errors)
    else:
        _validate_substring_hypothetical_markers(
            direct_critique,
            cleaned,
            errors,
        )

    has_real_bug = "Classification: REAL_BUG" in cleaned
    recommends_no_change = "Recommended action: NO_CHANGE" in cleaned
    has_no_test_needed = "Test status: NO_TEST_NEEDED" in cleaned

    if has_real_bug and recommends_no_change:
        errors.append(REAL_BUG_NO_CHANGE_ERROR)

    has_maintainability_hardening = (
        "Classification: MAINTAINABILITY_HARDENING" in cleaned
    )

    if has_maintainability_hardening and recommends_no_change:
        errors.append(MAINTAINABILITY_NO_CHANGE_ERROR)

    if (
        has_real_bug
        and verdict == "GO"
        and has_no_test_needed
    ):
        errors.append(REAL_BUG_GO_NO_TEST_ERROR)

    normalized = cleaned.lower()

    hypothetical_dependency_patterns = [
        "if the helper were to change",
        "if the dependency were to change",
        "if the imported function were to change",
        "if the helper changes its contract",
        "future dependency change",
    ]

    if any(
        pattern in normalized
        for pattern in hypothetical_dependency_patterns
    ):
        errors.append(HYPOTHETICAL_DEPENDENCY_CHANGE_ERROR)


    if "Classification: NEEDS_CONTEXT" in cleaned and confidence == "High":
        errors.append(NEEDS_CONTEXT_HIGH_CONFIDENCE_ERROR)

    if "Evidence: EVIDENCE_MEDIUM" in cleaned and confidence == "High":
        errors.append(MEDIUM_EVIDENCE_HIGH_CONFIDENCE_ERROR)


def _helper_name_is_mentioned(
    context_name: str,
    direct_critique_lower: str,
) -> bool:
    return re.search(
        rf"\b{re.escape(context_name.lower())}\b",
        direct_critique_lower,
    ) is not None


def validate_audit_output(
    response: str,
    available_context_names: set[str] | None = None,
) -> AuditValidationResult:
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

    _validate_contract_values(cleaned, errors)
    _validate_calibration_contract(cleaned, errors)

    if available_context_names:
        direct_critique = _extract_section_content(
            cleaned,
            "2. Direct critique",
            "3. Better option",
        )
        direct_critique_lower = direct_critique.lower()

        missing_context_values: list[str] = []

        for line in direct_critique.splitlines():
            value = _value_after_label(line, "Missing context")
            if value is not None:
                missing_context_values.append(value)
        missing_context_is_claimed = any(
            value.lower().rstrip(".") not in {"", "none"}
            for value in missing_context_values
        )

        for context_name in sorted(available_context_names):
            helper_is_named = _helper_name_is_mentioned(
                context_name,
                direct_critique_lower,
            )
            helper_contract_is_claimed_missing = any(
                phrase in direct_critique_lower
                for phrase in (
                    "definition",
                    "signature",
                    "return contract",
                    "type contract",
                    "explicit type signature",
                )
            )

            if (
                helper_is_named
                and missing_context_is_claimed
                and helper_contract_is_claimed_missing
            ):
                errors.append(
                    "Available helper context cannot be reported as missing: "
                    f"{context_name}."
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
