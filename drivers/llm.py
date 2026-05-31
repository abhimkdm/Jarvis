import json
import re
import requests

class LLMManager:
    def __init__(self, model="llama3.2:1b"):
        self.model = model.lower().strip()
        self.api_url = "http://localhost:11434/api/chat"

    def generate_tool_aware_response(self, user_text, tools, temperature=0.0):
        """
        Streamlined tool router optimized for maximum determinism.
        Forces temperature 0.0 globally for all conversation threads.
        """
        if isinstance(user_text, list):
            user_text = " ".join(str(item) for item in user_text)
        else:
            user_text = str(user_text)
        cleaned_input = user_text.lower().strip()

        # Structural response interfaces mapped to core expectations
        class ToolCall:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        class AIResponse:
            def __init__(self, text=None, tool_calls=None):
                self.text = text
                self.tool_calls = tool_calls or []

        # 1. GREETING INTERCEPTOR
        greetings = ["hey jarvis", "good morning", "hello", "hi jarvis", "how are you", "good evening"]
        if any(g == cleaned_input or cleaned_input.startswith(g + " ") for g in greetings):
            return AIResponse(text="Good morning, sir. I am fully operational and monitoring system states. How can I assist you today?")

        # 2. BUILD SCHEMAS AND GUIDANCE (Enforcing absolute temperature 0.0)
        tools_description = ""
        for tool in tools:
            tools_description += f"- {tool['name']}: {tool['description']}\n"

        system_guidance = (
            f"You are Jarvis. You have access to these exact tools ONLY:\n{tools_description}\n"
            "CRITICAL ORDER:\n"
            "If the user is just chatting, saying thank you, or asking a general question, "
            "do NOT use the CALL_TOOL format. Just reply with a normal conversational sentence.\n\n"
            "DIRECTIONS:\n"
            "- To simply open a program (Chrome, Outlook, VS Code, Notepad, Calculator), "
            "output: CALL_TOOL: open_application | ARGUMENTS: {\"app_name\": \"calc\"}\n"
            "- To dictate words or write actual text contents into a note, "
            "output: CALL_TOOL: stage_note | ARGUMENTS: {\"text_payload\": \"text\"}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_guidance},
                {"role": "user", "content": user_text}
            ],
            "options": {
                "temperature": 0.0  # <-- Locked down globally
            },
            "stream": False
        }

        try:
            response = requests.post(self.api_url, json=payload)
            response_content = response.json().get("message", {}).get("content", "")

            # If Ollama returns content as array segments instead of a string
            if isinstance(response_content, list):
                response_text = " ".join(str(item) for item in response_content).strip()
            else:
                response_text = str(response_content).strip()

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

                        for key, value in list(arguments.items()):
                            if isinstance(value, list):
                                arguments[key] = value[0] if value else ""

                        tool_clean = tool_name.lower().replace("_", "").replace(" ", "")
                        if tool_clean == "stagenote":
                            final_name = "stage_note"
                            if "text_payload" not in arguments:
                                arguments = {
                                    "text_payload": (
                                        list(arguments.values())[0]
                                        if arguments
                                        else user_text
                                    )
                                }
                        elif tool_clean == "stageemail":
                            final_name = "stage_email"
                        elif tool_clean == "openapplication":
                            final_name = "open_application"
                        else:
                            final_name = tool_name

                        return AIResponse(
                            tool_calls=[ToolCall(name=final_name, arguments=arguments)]
                        )
                    except Exception:
                        pass

            return AIResponse(text=response_text)

        except Exception as e:
            class ErrorResponse:
                text = f"Sir, my brain matrix encountered an error: {e}"
                tool_calls = []
            return ErrorResponse()
