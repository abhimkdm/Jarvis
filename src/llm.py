from openai import OpenAI


class LLMManager:
    def __init__(self, base_url="http://localhost:11434/v1", model="llama3.2:1b"):
        self.client = OpenAI(base_url=base_url, api_key="ollama")
        self.model = model

    def generate_response(self, prompt, system_instruction):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content
            return (content or "").strip()
        except Exception as e:
            return f"Error connecting to Ollama: {e}"
