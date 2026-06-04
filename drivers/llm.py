import json
import os
import re

import httpx
import requests

from os_kernel.system_states import SystemStageManager


class StateAwareLLMManager:
    """3B parsing core: phonetic stage latch, then JSON schema extraction."""

    def __init__(
        self,
        llm_config: dict | None = None,
        stage_manager: SystemStageManager | None = None,
        base_url: str | None = None,
    ):
        llm = llm_config or {}
        root = str(
            llm.get("url") or llm.get("base_url", "http://localhost:11434")
        ).rstrip("/")
        v1_base = base_url or f"{root}/v1"
        self.client = httpx.Client(base_url=v1_base, timeout=15.0)
        self.model = str(llm.get("model", "llama3.2:3b"))
        self.stage_manager = stage_manager or SystemStageManager()

    def process_staged_query(self, user_text: str) -> dict:
        active_stage, action_query = self.stage_manager.clean_and_evaluate(user_text)

        if active_stage == "TRACK_TERMINATE":
            return {
                "active_stage": active_stage,
                "action_query": action_query,
                "meta": {},
            }

        system_prompt = (
            f"You are the central parsing core for Jarvis. The system is operating within: "
            f"[{active_stage}].\n"
            "Extract explicit structural metadata query directives matching this system track context.\n\n"
            "Return raw JSON format matching this layout exactly without markdown formatting headers:\n"
            '{"active_stage": "STAGE_NAME", "action_query": "cleaned query content"}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context parameters to process: '{action_query}'"},
        ]

        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            parsed = json.loads(response.json()["choices"][0]["message"]["content"])
            parsed["active_stage"] = parsed.get("active_stage") or active_stage
            parsed["action_query"] = parsed.get("action_query") or action_query
            parsed.setdefault("meta", {})
            return parsed
        except Exception:
            return {
                "active_stage": active_stage,
                "action_query": action_query,
                "meta": {},
            }


class LLMManager:
    def __init__(
        self,
        llm_config: dict,
        system_prompt: str = "",
        stage_manager: SystemStageManager | None = None,
        stage_orchestrator: StateAwareLLMManager | None = None,
    ):
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
        self._stage_orchestrator = stage_orchestrator or StateAwareLLMManager(
            llm_config=self.llm_config,
            stage_manager=stage_manager,
        )

    def process_staged_query(self, user_text: str) -> dict:
        return self._stage_orchestrator.process_staged_query(user_text)

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = os.environ.get(self._api_key_env, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def _format_staged_context(staged_context: dict | None) -> str:
        if not staged_context:
            return ""
        stage = staged_context.get("active_stage", "TRACK_CONVERSATION")
        action = staged_context.get("action_query", "")
        meta = staged_context.get("meta") or {}
        meta_json = json.dumps(meta, ensure_ascii=False)
        return (
            f"\n\nACTIVE WORKSPACE STAGE: [{stage}]\n"
            f"STAGE-PARSED ACTION QUERY: {action}\n"
            f"STAGE-PARSED META (JSON): {meta_json}\n"
            "Honor the locked stage domain when choosing tools or conversational replies."
        )

    def _build_system_guidance(
        self, tools: list, staged_context: dict | None = None
    ) -> str:
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
        stage_block = self._format_staged_context(staged_context)
        return (
            f"{base}{stage_block}\n\n"
            f"You have access to these exact tools ONLY:\n{tools_description}\n"
            f"{tool_rules}"
        )

    @staticmethod
    def _normalize_user_text(user_text) -> str:
        if isinstance(user_text, list):
            return " ".join(str(item) for item in user_text)
        return str(user_text)

    def generate_tool_aware_response(
        self,
        user_text,
        tools,
        temperature=0.0,
        *,
        active_stage: str | None = None,
        staged_context: dict | None = None,
    ):
        """
        Routes to Ollama (local) or OpenAI-compatible chat (deployed org gateway).
        When staged_context is omitted, runs the 3B stage schema pass first.
        """
        user_text = self._normalize_user_text(user_text)
        if staged_context is None:
            staged_context = self.process_staged_query(user_text)
        elif active_stage and not staged_context.get("active_stage"):
            staged_context["active_stage"] = active_stage
        effective_text = staged_context.get("action_query") or user_text
        cleaned_input = effective_text.lower().strip()

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

        system_guidance = self._build_system_guidance(tools, staged_context)
        print(
            f"[LLM Stage Context: {staged_context.get('active_stage')} "
            f"action={staged_context.get('action_query')!r}]"
        )

        try:
            if self.provider == "openai_compatible":
                response_text = self._request_openai_compatible(
                    system_guidance, effective_text, temperature
                )
            else:
                response_text = self._request_ollama(
                    system_guidance, effective_text, temperature
                )

            parsed = self._parse_call_tool_response(response_text, effective_text)
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
