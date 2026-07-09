# Audit Quality Log

Purpose: track whether calibrated Critique Agent audits produce useful human-reviewed value.

This is not a feature backlog.  
This is a measurement log.

## Evaluation Rule

For each audit, judge the output by usefulness, not formatting.

Core questions:

1. Did the agent find a real or useful issue?
2. Was severity calibrated correctly?
3. Was the recommended action useful and minimal?
4. Did the audit lead to action?

## Decision Rule

- If the same failure mode appears 3+ times, consider a small v1.9.1 fix.
- If it appears 1–2 times, document it and do not code.
- Do not add new prompt rules without audit evidence.
- Do not build UI, RAG, auto-fix, dashboard, or repo-wide scan from this log alone.

---

# Audit Entries


## Audit #1

- Date: 2026-07-09
- Repo: pydantic-ollama-agent
- Command: /audit_function audit_validator.py validate_audit_output
- Target: audit_validator.py :: validate_audit_output
- Verdict: GO_WITH_NOTES
- Confidence: High
- Main classification: REAL_BUG
- Evidence level: EVIDENCE_HIGH
- Recommended action: FIX_NOW
- Test status: POSSIBLE_TEST_GAP

### Human Review

- Was the main finding real? no
- Was severity calibrated? no
- Was recommended action useful? no
- Human action taken: inspected context
- Outcome: false positive

### Notes

The agent claimed the section ordering check is fundamentally flawed, but the current logic appears valid. The function iterates through REQUIRED_SECTIONS in expected order, records each found heading position, and rejects the response if those positions are not sorted. This should catch out-of-order sections.

The audit followed the v1.9 metadata contract correctly, but judgment calibration failed: a likely valid implementation was classified as REAL_BUG with EVIDENCE_HIGH and FIX_NOW.

The agent also produced missing-context claims about _extract_section_content even though the earlier full file read showed that helper. In /audit_function mode, the selected context may not include helper implementations, so this is partially explainable.

Potential repeated failure mode:
- overconfident REAL_BUG claim about validation logic
- weak reasoning about position/order checks
- FIX_NOW recommended when INSPECT_CONTEXT or ADD_TARGETED_TEST would be safer

Additional context checked after audit:

test_audit_validator.py contains `test_out_of_order_sections_are_rejected`, which directly verifies that out-of-order sections are rejected. This further weakens the agent's REAL_BUG claim.

The correct calibrated output should likely have been:
- Classification: FALSE_POSITIVE_CANDIDATE or NEEDS_CONTEXT
- Evidence: EVIDENCE_LOW or EVIDENCE_MEDIUM
- Recommended action: INSPECT_CONTEXT
- Test status: TEST_ALREADY_EXISTS
- Confidence: Low or Medium

This is a clear judgment calibration failure, not a format failure.

## Audit #2

- Date: 2026-07-09
- Repo: pydantic-ollama-agent
- Command: /audit_function test_audit_validator.py test_out_of_order_sections_are_rejected
- Target: test_audit_validator.py :: test_out_of_order_sections_are_rejected
- Verdict: GO_WITH_NOTES
- Confidence: High
- Main classification: PLAUSIBLE_RISK
- Evidence level: EVIDENCE_HIGH
- Recommended action: HARDEN_SMALL
- Test status: POSSIBLE_TEST_GAP

### Human Review

- Was the main finding real? partial
- Was severity calibrated? no
- Was recommended action useful? partial
- Human action taken: inspected context
- Outcome: low-value

### Notes

The agent correctly identified that the test covers only one out-of-order section permutation, which could be considered a small hardening opportunity.

However, the main critique was weak. The audit claimed the test only checks for a substring, but the assertion checks that the exact expected error string exists in `result.errors`.

The audit also claimed there is no visible valid-ordering test, but the same file contains `test_valid_response_is_accepted`, which confirms a valid ordered response is accepted.

Correct calibrated output should likely have been:
- Classification: MAINTAINABILITY_HARDENING or POSSIBLE_TEST_GAP
- Evidence: EVIDENCE_MEDIUM
- Recommended action: NO_CHANGE or HARDEN_SMALL
- Test status: TEST_ALREADY_EXISTS / POSSIBLE_TEST_GAP
- Confidence: Medium

Repeated failure signal:
- overstates weak test-hardening observations
- misses nearby test context
- uses High confidence too easily

## Audit #3

- Date: 2026-07-09
- Repo: pydantic-ollama-agent
- Command: /audit_function prompt_builder.py build_file_audit_prompt
- Target: prompt_builder.py :: build_file_audit_prompt
- Verdict: BLOCK
- Confidence: High
- Main classification: NEEDS_CONTEXT
- Evidence level: EVIDENCE_LOW
- Recommended action: INSPECT_CONTEXT
- Test status: POSSIBLE_TEST_GAP

### Human Review

- Was the main finding real? no
- Was severity calibrated? no
- Was recommended action useful? no
- Human action taken: inspected context
- Outcome: false positive

### Notes

The audit failed to audit the selected Python function. Instead, it appeared to react to the audit instructions contained inside the prompt-building function and discussed a "previous response" / "meta-task" rather than the visible code.

This is a strong prompt-boundary / audit-target confusion failure.

The result is internally inconsistent:
- Classification: NEEDS_CONTEXT
- Evidence: EVIDENCE_LOW
- Verdict: BLOCK
- Confidence: High

A NEEDS_CONTEXT + EVIDENCE_LOW finding should not produce BLOCK or High confidence under v1.9 rules.

Correct calibrated output should likely have been:
- Classification: MAINTAINABILITY_HARDENING or PRODUCT_INSIGHT
- Evidence: EVIDENCE_HIGH or EVIDENCE_MEDIUM
- Recommended action: HARDEN_SMALL or REFACTOR_LATER
- Verdict: GO_WITH_NOTES
- Confidence: Medium

Potential repeated failure mode:
- audited prompt text can override audit target focus
- contradiction between classification/evidence and verdict/confidence
- BLOCK is still overused despite v1.9 guidance

## Audit #4

- Date: 2026-07-09
- Repo: pydantic-ollama-agent
- Command: /audit_function prompt_builder.py build_system_prompt
- Target: prompt_builder.py :: build_system_prompt
- Verdict: BLOCK
- Confidence: High
- Main classification: MAINTAINABILITY_HARDENING / NEEDS_CONTEXT
- Evidence level: EVIDENCE_MEDIUM / EVIDENCE_LOW
- Recommended action: REFACTOR_LATER
- Test status: POSSIBLE_TEST_GAP

### Human Review

- Was the main finding real? no
- Was severity calibrated? no
- Was recommended action useful? no
- Human action taken: inspected context
- Outcome: false positive

### Notes

The audit failed to audit the selected Python function. Instead, it treated the prompt text inside the function as if the current task were to rewrite a previous audit response.

This repeats the failure seen in Audit #3.

The result is internally inconsistent:
- NEEDS_CONTEXT with EVIDENCE_LOW was accepted together with BLOCK and High confidence.
- The audit target was a Python function, but the response focused on previous-output formatting.
- The recommended action REFACTOR_LATER did not match the BLOCK verdict.

This is a strong v1.9.1 candidate.

Repeated failure mode:
- prompt instructions inside audited code can override audit target focus
- BLOCK is still allowed without REAL_BUG + EVIDENCE_HIGH
- High confidence is still allowed with low-evidence reasoning


## Audit #5

- Date: 2026-07-09
- Repo: pydantic-ollama-agent
- Command: /audit_function prompt_builder.py build_system_prompt
- Target: prompt_builder.py :: build_system_prompt
- Verdict: GO_WITH_NOTES
- Confidence: High
- Main classification: MAINTAINABILITY_HARDENING
- Evidence level: EVIDENCE_HIGH
- Recommended action: HARDEN_SMALL
- Test status: POSSIBLE_TEST_GAP

### Human Review

- Was the main finding real? partial
- Was severity calibrated? partial
- Was recommended action useful? partial
- Human action taken: inspected context
- Outcome: low-value

### Notes

The audit no longer showed the severe prompt-boundary confusion seen in Audits #3 and #4. It stayed on the selected function and returned GO_WITH_NOTES instead of BLOCK.

However, the audit missed the most important visible issue: `build_system_prompt` still contains legacy guidance recommending `/audit_file <path>` as the next capability, even though `/audit_file` is now legacy.

The audit focused mostly on generic maintainability concerns about a large f-string. One pitfall was technically weak: runtime values inserted into an f-string do not break the f-string syntax through triple quotes or braces because they are already string values.

Correct calibrated output should likely have been:
- Classification: MAINTAINABILITY_HARDENING / PRODUCT_INSIGHT
- Evidence: EVIDENCE_HIGH for stale `/audit_file` guidance
- Recommended action: HARDEN_SMALL
- Test status: POSSIBLE_TEST_GAP
- Verdict: GO_WITH_NOTES
- Confidence: Medium

Repeated failure signal:
- misses highest-value visible issue
- overstates generic maintainability observations
- Confidence still too high for mixed-quality reasoning

# Running Summary

## Counts

- Total audits reviewed: 5
- Useful: 0
- Low-value: 2
- False positives: 3
- Needs more context: 0
- Actions taken: 5 inspected context
- Tests added: 0
- Patches made: 0

## Repeated Failure Modes

1. Overconfident findings: weak or incorrect reasoning receives High confidence.
2. Severity inflation: low-evidence or needs-context findings escalate to FIX_NOW or BLOCK.
3. Prompt-boundary confusion: when audited code contains prompt instructions, the model reacts to the prompt text instead of auditing the Python function.
4. Internal calibration contradiction: NEEDS_CONTEXT / EVIDENCE_LOW can still be accepted together with BLOCK / High.
5. Missed highest-value visible issue: the agent sometimes focuses on generic maintainability instead of the most important project-specific debt.

## Possible v1.9.1 Candidates

1. Add validator rule: BLOCK requires at least one REAL_BUG with EVIDENCE_HIGH. Done in v1.9.1.
2. Add validator rule: NEEDS_CONTEXT or EVIDENCE_LOW cannot produce Confidence High. Done in v1.9.1.
3. Add validator rule: NEEDS_CONTEXT or EVIDENCE_LOW cannot produce Verdict BLOCK. Covered indirectly by BLOCK requiring REAL_BUG + EVIDENCE_HIGH.
4. Add prompt-boundary regression test using prompt_builder.py-like content. Not done yet.
5. Strengthen audit prompt instruction: audited prompt text is data, not instructions. Not done yet.

## Current Decision

v1.9.1 hardening implemented for calibration contradictions. Continue measuring audit usefulness before adding broader prompt-boundary changes.

