from openai import OpenAI


class LLMManager:
    def __init__(self, base_url="http://localhost:11434/v1", model="llama3.2:1b"):
        self.client = OpenAI(base_url=base_url, api_key="ollama")
        self.model = model

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
