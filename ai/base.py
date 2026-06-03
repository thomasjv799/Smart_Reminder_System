from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Generate plain text for a prompt (used for summarisation)."""

    @abstractmethod
    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        """
        Send messages with optional tool definitions.
        Returns one of:
          {"text": "...", "usage": {"input_tokens": int, "output_tokens": int}}
          {"tool_calls": [{"name": str, "arguments": dict}], "usage": {...}}
        """
