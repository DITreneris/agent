from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

model = OllamaModel(
    "gemma4:e4b",
    provider=OllamaProvider(base_url="http://localhost:11434/v1"),
)

agent = Agent(
    model,
    system_prompt=(
        "You are a local technical test agent. "
        "You are running through Pydantic AI connected to an Ollama server at localhost:11434. "
        "Do not claim that you run on Google, OpenAI, Anthropic, or any cloud infrastructure. "
        "Use exact technical names: Pydantic AI, Ollama, localhost:11434. "
        "Answer briefly and clearly in English. "
        "Use one sentence only."
    ),
)

result = agent.run_sync("Confirm your current runtime setup.")
print(result.output)
