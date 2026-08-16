from dataclasses import dataclass
import json
import urllib.request


@dataclass(frozen=True)
class OllamaAuditConfig:
    model: str = "gemma4:e4b"
    temperature: float = 0.1
    seed: int | None = None
    timeout_seconds: int = 300
    base_url: str = "http://localhost:11434/api/chat"


DEFAULT_OLLAMA_AUDIT_CONFIG = OllamaAuditConfig()


def call_ollama_audit(
    prompt: str,
    system_prompt: str,
    config: OllamaAuditConfig = DEFAULT_OLLAMA_AUDIT_CONFIG,
) -> str:
    options: dict[str, float | int] = {
        "temperature": config.temperature,
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

    return data["message"]["content"]
