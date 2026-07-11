from audit_runner import run_validated_audit
from test_audit_validator import VALID_RESPONSE


def test_valid_first_response_does_not_retry():
    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return VALID_RESPONSE

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is True
    assert result.response == VALID_RESPONSE
    assert result.errors == []
    assert result.retry_used is False
    assert len(calls) == 1


def test_invalid_first_response_is_retried_once():
    responses = iter(
        [
            "Invalid response",
            VALID_RESPONSE,
        ]
    )

    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return next(responses)

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is True
    assert result.response == VALID_RESPONSE
    assert result.errors == []
    assert result.retry_used is True
    assert len(calls) == 2
    assert "Previous response:" in calls[1]
    assert "Invalid response" in calls[1]


def test_second_invalid_response_is_rejected():
    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return "Invalid response"

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is False
    assert result.response == "Invalid response"
    assert result.errors
    assert result.retry_used is True
    assert len(calls) == 2


def test_retry_is_not_run_more_than_once():
    calls = []

    def fake_model_call(prompt: str) -> str:
        calls.append(prompt)
        return "Still invalid"

    result = run_validated_audit(
        initial_prompt="Audit this code.",
        model_call=fake_model_call,
    )

    assert result.success is False
    assert result.response == "Still invalid"
    assert result.retry_used is True
    assert len(calls) == 2
