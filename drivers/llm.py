import json
import re
from dataclasses import dataclass, field

import requests
from openai import OpenAI


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class ToolAwareResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMManager:
    def __init__(self, base_url="http://localhost:11434/v1", model="llama3.2:1b"):
        self.client = OpenAI(base_url=base_url, api_key="ollama")
        self.model = model
        root = base_url.rsplit("/v1", 1)[0] if "/v1" in base_url else base_url.rstrip("/")
        self.api_url = f"{root}/api/chat"

    @staticmethod
    def _format_tools(tools_manifest):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("input_schema")
                    or {"type": "object", "properties": {}},
                },
            }
            for tool in tools_manifest
        ]

    def generate_response(self, messages_payload):
        """Accepts complete contextual list array instead of just a raw string."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages_payload,
            )
            content = response.choices[0].message.content
            return (content or "").strip()
        except Exception as e:
            return f"Error connecting to Ollama: {e}"

    def generate_tool_aware_response(self, user_text, tools, temperature=0.0):
        """
        Custom tool-routing wrapper optimized for small 1B models.
        Provides explicit function naming examples to guarantee character matching.
        """
        tools_description = ""
        for tool in tools:
            tools_description += (
                f"- Tool Name: {tool['name']}\n"
                f"  Description: {tool['description']}\n"
            )

        system_guidance = (
            f"You are Jarvis. You have access to these exact local system tools:\n{tools_description}\n"
            "CRITICAL rules for tool usage:\n"
            "1. If the user wants to write a note or open notepad, you MUST call 'stage_note'.\n"
            "2. If the user wants to draft an email or contact someone, you MUST call 'stage_email'.\n"
            "3. If the user says confirm or yes, call 'confirm_and_open_notepad' or 'confirm_and_send_email'.\n\n"
            "Format your response strictly like this example:\n"
            'CALL_TOOL: stage_note | ARGUMENTS: {"text_payload": "your text here"}\n\n'
            "If no system tool is required, reply with a normal conversational sentence."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_guidance},
                {"role": "user", "content": user_text},
            ],
            "options": {
                "temperature": temperature,
            },
            "stream": False,
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            response.raise_for_status()
            response_text = response.json().get("message", {}).get("content", "").strip()

            if "CALL_TOOL:" in response_text:
                match = re.search(
                    r"CALL_TOOL:\s*(\w+)\s*\|\s*ARGUMENTS:\s*(\{.*\}).*",
                    response_text,
                    re.DOTALL,
                )
                if match:
                    tool_name = match.group(1).strip()
                    args_str = match.group(2).strip()
                    try:
                        arguments = json.loads(args_str)

                        tool_clean = (
                            tool_name.strip().lower().replace("_", "").replace(" ", "")
                        )
                        if tool_clean == "stagenote" and "text_payload" not in arguments:
                            fallback_val = (
                                list(arguments.values())[0] if arguments else user_text
                            )
                            arguments = {"text_payload": fallback_val}

                        return ToolAwareResponse(
                            tool_calls=[ToolCall(name=tool_name, arguments=arguments)]
                        )
                    except Exception:
                        print(
                            f"[Brain Warning: Model output invalid JSON arguments string: {args_str}]"
                        )

            return ToolAwareResponse(text=response_text)

        except Exception as e:
            return ToolAwareResponse(
                text=f"Sir, my processing matrix encountered an error: {e}"
            )
