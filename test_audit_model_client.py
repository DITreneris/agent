import json

import chat_agent

from audit_model_client import (
    OllamaAuditConfig,
    call_ollama_audit,
    call_ollama_audit_with_metadata,
)


class FakeResponse:
    def __init__(
        self,
        content: str,
        prompt_eval_count: int | None = None,
        eval_count: int | None = None,
        done_reason: str | None = None,
    ) -> None:
        self.content = content
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count
        self.done_reason = done_reason

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        payload = {
            "message": {
                "content": self.content,
            },
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "done_reason": self.done_reason,
        }
        return json.dumps(payload).encode("utf-8")


def test_call_ollama_audit_uses_default_config(
    monkeypatch,
) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse("Default response")

    monkeypatch.setattr(
        "audit_model_client.urllib.request.urlopen",
        fake_urlopen,
    )

    result = call_ollama_audit(
        prompt="Audit this code.",
        system_prompt="System instructions.",
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))

    assert result == "Default response"
    assert request.full_url == "http://localhost:11434/api/chat"
    assert request.get_method() == "POST"
    assert captured["timeout"] == 300
    assert payload["model"] == "gemma4:e4b"
    assert payload["messages"] == [
        {
            "role": "system",
            "content": "System instructions.",
        },
        {
            "role": "user",
            "content": "Audit this code.",
        },
    ]
    assert payload["options"] == {
        "temperature": 0.1,
        "num_ctx": 4096,
    }


def test_call_ollama_audit_uses_custom_config(
    monkeypatch,
) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse("Seeded response")

    monkeypatch.setattr(
        "audit_model_client.urllib.request.urlopen",
        fake_urlopen,
    )

    config = OllamaAuditConfig(
        model="test-model",
        temperature=0.0,
        seed=42,
        num_ctx=8192,
        timeout_seconds=12,
        base_url="http://localhost:9999/api/chat",
    )

    result = call_ollama_audit(
        prompt="Prompt",
        system_prompt="System",
        config=config,
    )

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))

    assert result == "Seeded response"
    assert request.full_url == "http://localhost:9999/api/chat"
    assert captured["timeout"] == 12
    assert payload["model"] == "test-model"
    assert payload["options"] == {
        "temperature": 0.0,
        "num_ctx": 8192,
        "seed": 42,
    }

def test_call_ollama_audit_preserves_response_metadata(
    monkeypatch,
) -> None:
    def fake_urlopen(request, timeout):
        return FakeResponse(
            "Measured response",
            prompt_eval_count=3210,
            eval_count=240,
            done_reason="stop",
        )

    monkeypatch.setattr(
        "audit_model_client.urllib.request.urlopen",
        fake_urlopen,
    )

    result = call_ollama_audit_with_metadata(
        prompt="Audit prompt",
        system_prompt="System prompt",
    )

    assert result.content == "Measured response"
    assert result.prompt_eval_count == 3210
    assert result.eval_count == 240
    assert result.done_reason == "stop"


def test_chat_agent_delegates_to_configurable_client(
    monkeypatch,
) -> None:
    captured = {}

    def fake_call_ollama_audit(
        *,
        prompt,
        system_prompt,
        config,
    ):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        captured["config"] = config
        return "Delegated response"

    monkeypatch.setattr(
        chat_agent,
        "call_ollama_audit",
        fake_call_ollama_audit,
    )

    config = OllamaAuditConfig(
        model="test-model",
        temperature=0.0,
        seed=7,
    )

    result = chat_agent.run_ollama_audit(
        "Audit prompt",
        config=config,
    )

    assert result == "Delegated response"
    assert captured["prompt"] == "Audit prompt"
    assert captured["system_prompt"] == chat_agent.SYSTEM_PROMPT
    assert captured["config"] is config
