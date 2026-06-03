import json
import os

from groq import Groq

from ai.base import AIProvider

_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    def __init__(self):
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate_text(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=tools if tools else None,
        )
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        msg = response.choices[0].message
        if msg.tool_calls:
            return {
                "tool_calls": [
                    {
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in msg.tool_calls
                ],
                "usage": usage,
            }
        return {"text": msg.content or "", "usage": usage}
