import os

from ai.base import AIProvider


def get_provider() -> AIProvider:
    name = os.environ.get("AI_PROVIDER", "groq").lower()
    if name == "groq":
        from ai.groq_provider import GroqProvider
        return GroqProvider()
    raise ValueError(f"Unknown AI_PROVIDER: {name!r}")
