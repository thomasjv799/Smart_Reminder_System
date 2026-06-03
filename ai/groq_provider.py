import json
import os
import re

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
        import groq as groq_module
        try:
            response = self._client.chat.completions.create(
                model=_MODEL,
                messages=messages,
                tools=tools if tools else None,
            )
        except groq_module.BadRequestError as exc:
            # Llama occasionally emits <function=name {...}> instead of proper JSON.
            # Salvage the tool call rather than surfacing a raw error to the user.
            body = getattr(exc, "body", {}) or {}
            err = body.get("error", {})
            if err.get("code") == "tool_use_failed":
                failed = err.get("failed_generation", "")
                match = re.search(r"<function=([a-zA-Z0-9_]+)\s*(.*)", failed)
                if match:
                    name = match.group(1)
                    args_str = match.group(2).strip().rstrip("</function>").rstrip(">").strip()
                    try:
                        args = json.loads(args_str) if args_str else {}
                        return {"tool_calls": [{"name": name, "arguments": args}], "usage": {}}
                    except json.JSONDecodeError:
                        pass
            raise

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
