class NotepadMCP:
    def __init__(self):
        self.trigger_phrase = "write in notepad"
        self.target_agent = "notepad"

    def match_and_parse(self, user_text):
        """
        Model Context Protocol Layer.
        Checks if input text matches the required schema structure.
        """
        cleaned = user_text.lower()
        if self.trigger_phrase in cleaned:
            start_idx = cleaned.find(self.trigger_phrase) + len(self.trigger_phrase)
            payload_text = user_text[start_idx:].strip()

            return {
                "agent": self.target_agent,
                "payload": payload_text if payload_text else None,
            }
        return None
