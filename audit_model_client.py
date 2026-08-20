from dataclasses import dataclass
import json
import urllib.request


@dataclass(frozen=True)
class OllamaAuditConfig:
    model: str = "gemma4:e4b"
    temperature: float = 0.1
    seed: int | None = None
    num_ctx: int = 4096
    timeout_seconds: int = 300
    base_url: str = "http://localhost:11434/api/chat"


@dataclass(frozen=True)
class OllamaAuditResponse:
    content: str
    prompt_eval_count: int | None
    eval_count: int | None
    done_reason: str | None


DEFAULT_OLLAMA_AUDIT_CONFIG = OllamaAuditConfig()


def call_ollama_audit_with_metadata(
    prompt: str,
    system_prompt: str,
    config: OllamaAuditConfig = DEFAULT_OLLAMA_AUDIT_CONFIG,
) -> OllamaAuditResponse:
    options: dict[str, float | int] = {
        "temperature": config.temperature,
        "num_ctx": config.num_ctx,
    }

    if config.seed is not None:
        options["seed"] = config.seed

    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "think": False,
        "options": options,
    }

    request = urllib.request.Request(
        config.base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=config.timeout_seconds,
    ) as response:
        data = json.loads(response.read().decode("utf-8"))

    return OllamaAuditResponse(
        content=data["message"]["content"],
        prompt_eval_count=data.get("prompt_eval_count"),
        eval_count=data.get("eval_count"),
        done_reason=data.get("done_reason"),
    )


def call_ollama_audit(
    prompt: str,
    system_prompt: str,
    config: OllamaAuditConfig = DEFAULT_OLLAMA_AUDIT_CONFIG,
) -> str:
    return call_ollama_audit_with_metadata(
        prompt=prompt,
        system_prompt=system_prompt,
        config=config,
    ).content
