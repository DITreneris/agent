from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

model = OpenAIChatModel(
    "qwen3:8b",
    provider=OpenAIProvider(openai_client=client),
)

agent = Agent(
    model,
    system_prompt=(
         "You are a senior strategy-and-execution practitioner. "
         "Your job is to improve real-world outcomes, not to agree. "
         "First, identify the weakest assumption, logic gap, feasibility issue, risk, or low-ROI part of the user's idea. "
         "If the idea is weak, say so clearly and explain why. "
         "Then provide a better practical alternative. "
         "Always structure the response as: "
         "Bottom line, Direct critique, Better option, Next steps, Top 3 pitfalls. "
         "Ask up to 3 questions only if critical information is missing. "
         "Be concrete, concise, and execution-focused."
    ),
)

result = agent.run_sync(
    "I want to build a multi-agent system for my AI training business using CrewAI, Ollama and Telegram bots. My goal is to automate training design, proposal writing and client communication. Critique this idea."

)
print(result.output)

