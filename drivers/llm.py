import json
import os
import re

import requests


class LLMManager:
    def __init__(self, llm_config: dict, system_prompt: str = ""):
        self.llm_config = llm_config or {}
        self.model = str(self.llm_config.get("model", "llama3.2:3b")).lower().strip()
        self.provider = str(self.llm_config.get("provider", "ollama")).lower().strip()
        self.active_profile = self.llm_config.get("active_profile", "local")
        self.system_prompt = (system_prompt or "").strip()

        base_url = str(self.llm_config.get("base_url", "http://localhost:11434")).rstrip("/")
        chat_path = self.llm_config.get("chat_path", "/api/chat")
        if not str(chat_path).startswith("/"):
            chat_path = f"/{chat_path}"
        self.api_url = f"{base_url}{chat_path}"

        self._api_key_env = self.llm_config.get("api_key_env", "JARVIS_API_KEY")

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = os.environ.get(self._api_key_env, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _build_system_guidance(self, tools: list) -> str:
        tools_description = ""
        for tool in tools:
            tools_description += f"- {tool['name']}: {tool['description']}\n"

        tool_rules = (
            "CRITICAL ORDER:\n"
            "If the user is just chatting, saying thank you, or asking a general question, "
            "do NOT use the CALL_TOOL format. Just reply with a normal conversational sentence.\n\n"
            "DIRECTIONS:\n"
            "- To simply open a program (Chrome, Outlook, VS Code, Notepad, Calculator), "
            "output: CALL_TOOL: open_application | ARGUMENTS: {\"app_name\": \"calc\"}\n"
            "- To dictate words or write actual text contents into a note, "
            "output: CALL_TOOL: stage_note | ARGUMENTS: {\"text_payload\": \"text\"}\n"
            "- To stage an email, "
            "output: CALL_TOOL: stage_email | ARGUMENTS: {\"recipient\": \"name\", \"body\": \"text\"}"
        )

        base = self.system_prompt or "You are Jarvis, a localized desktop AI assistant."
        return (
            f"{base}\n\n"
            f"You have access to these exact tools ONLY:\n{tools_description}\n"
            f"{tool_rules}"
        )

    @staticmethod
    def _normalize_user_text(user_text) -> str:
        if isinstance(user_text, list):
            return " ".join(str(item) for item in user_text)
        return str(user_text)

    def generate_tool_aware_response(self, user_text, tools, temperature=0.0):
        """
        Routes to Ollama (local) or OpenAI-compatible chat (deployed org gateway).
        """
        user_text = self._normalize_user_text(user_text)
        cleaned_input = user_text.lower().strip()

        class ToolCall:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        class AIResponse:
            def __init__(self, text=None, tool_calls=None):
                self.text = text
                self.tool_calls = tool_calls or []

        greetings = [
            "hey jarvis",
            "good morning",
            "hello",
            "hi jarvis",
            "how are you",
            "good evening",
        ]
        if any(g == cleaned_input or cleaned_input.startswith(g + " ") for g in greetings):
            return AIResponse(
                text="Good morning, sir. I am fully operational and monitoring system states. How can I assist you today?"
            )

        system_guidance = self._build_system_guidance(tools)

        try:
            if self.provider == "openai_compatible":
                response_text = self._request_openai_compatible(
                    system_guidance, user_text, temperature
                )
            else:
                response_text = self._request_ollama(
                    system_guidance, user_text, temperature
                )

            parsed = self._parse_call_tool_response(response_text, user_text)
            if parsed:
                return parsed
            return AIResponse(text=response_text)

        except Exception as exc:
            class ErrorResponse:
                text = f"Sir, my brain matrix encountered an error: {exc}"
                tool_calls = []

            return ErrorResponse()

    def _request_ollama(self, system_guidance: str, user_text: str, temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_guidance},
                {"role": "user", "content": user_text},
            ],
            "options": {"temperature": float(temperature)},
            "stream": False,
        }
        response = requests.post(self.api_url, json=payload, timeout=120)
        response.raise_for_status()
        response_content = response.json().get("message", {}).get("content", "")
        if isinstance(response_content, list):
            return " ".join(str(item) for item in response_content).strip()
        return str(response_content).strip()

    def _request_openai_compatible(
        self, system_guidance: str, user_text: str, temperature: float
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_guidance},
                {"role": "user", "content": user_text},
            ],
            "temperature": float(temperature),
            "stream": False,
        }
        response = requests.post(
            self.api_url,
            json=payload,
            headers=self._auth_headers(),
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(str(block))
            return " ".join(parts).strip()
        return str(content).strip()

    def _parse_call_tool_response(self, response_text: str, user_text: str):
        class ToolCall:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        class AIResponse:
            def __init__(self, text=None, tool_calls=None):
                self.text = text
                self.tool_calls = tool_calls or []

        if "CALL_TOOL:" not in response_text:
            return None

        match = re.search(
            r"CALL_TOOL:\s*(\w+)\s*\|\s*ARGUMENTS:\s*(\{.*\}).*",
            response_text,
            re.DOTALL,
        )
        if not match:
            return None

        tool_name = match.group(1).strip()
        args_str = match.group(2).strip()
        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            return None

        for key, value in list(arguments.items()):
            if isinstance(value, list):
                arguments[key] = value[0] if value else ""

        tool_clean = tool_name.lower().replace("_", "").replace(" ", "")
        if tool_clean == "stagenote":
            final_name = "stage_note"
            if "text_payload" not in arguments:
                arguments = {
                    "text_payload": (
                        list(arguments.values())[0] if arguments else user_text
                    )
                }
        elif tool_clean == "stageemail":
            final_name = "stage_email"
        elif tool_clean == "openapplication":
            final_name = "open_application"
        else:
            final_name = tool_name

        return AIResponse(tool_calls=[ToolCall(name=final_name, arguments=arguments)])
