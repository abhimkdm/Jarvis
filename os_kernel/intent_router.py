import json

import httpx

VALID_TRACKS = frozenset(
    {
        "TRACK_TMS",
        "TRACK_FILE_ANALYSIS",
        "TRACK_BROWSER_AUTOMATION",
        "TRACK_CONVERSATION",
    }
)


def normalize_track(target: str) -> str:
    cleaned = str(target or "").strip().upper()
    if cleaned in VALID_TRACKS:
        return cleaned
    return "TRACK_CONVERSATION"


class IntentRouterLayer:
    def __init__(self, llm_config: dict | None = None, ollama_url: str | None = None):
        llm = llm_config or {}
        base = str(llm.get("base_url", "http://localhost:11434")).rstrip("/")
        v1_base = ollama_url or f"{base}/v1"
        self.client = httpx.Client(base_url=v1_base, timeout=10.0)
        self.model = str(llm.get("model", "llama3.2:3b"))

    def classify_and_route(self, user_request: str) -> dict:
        """
        Forces llama3.2:3b to act as a traffic controller.
        It maps the request to a distinct pipeline track before execution.
        """
        system_routing_prompt = (
            "You are an elite intent classification routing engine for a desktop OS microkernel. "
            "Analyze the user's input request and map it to exactly ONE of the following routing targets:\n"
            "1. 'TRACK_TMS' - If they want to search, update, find bugs, or log items in task management portals.\n"
            "2. 'TRACK_FILE_ANALYSIS' - If they want to diff, parse, write, or review code scripts and documents.\n"
            "3. 'TRACK_BROWSER_AUTOMATION' - If they want to log hours, fill timesheets, or scrape open viewports.\n"
            "4. 'TRACK_CONVERSATION' - General chit-chat, greetings, or questions that don't call an automation agent.\n\n"
            "Output strictly valid raw JSON matching this structure. Do not output code blocks, markdown, or text outside the JSON:\n"
            '{"target": "TRACK_NAME", "confidence": 0.95, "normalized_query": "cleaned query", "extracted_parameters": {}}'
        )

        messages = [
            {"role": "system", "content": system_routing_prompt},
            {"role": "user", "content": f"Classify this input: '{user_request}'"},
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

            raw_content = response.json()["choices"][0]["message"]["content"]
            routing_matrix = json.loads(raw_content)
            routing_matrix["target"] = normalize_track(routing_matrix.get("target", ""))
            return routing_matrix

        except Exception:
            return {
                "target": "TRACK_CONVERSATION",
                "normalized_query": user_request,
                "extracted_parameters": {},
            }
