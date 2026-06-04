class SystemStageManager:
    def __init__(self):
        self.current_stage = "TRACK_CONVERSATION"

        # Phonetic dictionary to catch transcription errors
        self.phonetic_dictionary = {
            "grown": "chrome",
            "grome": "chrome",
            "tms": "tms",
            "pass page": "bass page",
            "outlook": "outlook",
            "shutdown": "exit",
            "stop": "exit",
            "close": "exit",
            "quit": "exit",
            "terminate": "exit",
        }

        # Explicitly maps core targets to structural tracks
        self.stage_map = {
            "chrome": "TRACK_BROWSER_AUTOMATION",
            "youtube": "TRACK_BROWSER_AUTOMATION",
            "bass page": "TRACK_BROWSER_AUTOMATION",
            "tms": "TRACK_TMS",
            "outlook": "TRACK_SYSTEM_COMMUNICATION",
            "webex": "TRACK_SYSTEM_COMMUNICATION",
            "calculator": "TRACK_SYSTEM_UTILITY",
            "vs code": "TRACK_FILE_ANALYSIS",
            "exit": "TRACK_TERMINATE",
        }

    def clean_and_evaluate(self, raw_input: str) -> tuple[str, str]:
        clean_input = (
            raw_input.lower()
            .replace(",", "")
            .replace(".", "")
            .replace("!", "")
            .strip()
        )

        words = clean_input.split()
        corrected_words = [
            self.phonetic_dictionary.get(word, word) for word in words
        ]
        normalized_text = " ".join(corrected_words)

        for typo, fix in self.phonetic_dictionary.items():
            if " " in typo:
                normalized_text = normalized_text.replace(typo, fix)

        exit_phrases = [
            "exit",
            "stop",
            "close",
            "shutdown",
            "quit",
            "okay stop",
            "ok stop",
        ]
        if any(phrase in normalized_text for phrase in exit_phrases):
            self.current_stage = "TRACK_TERMINATE"
            return "TRACK_TERMINATE", "exit"

        for anchor, stage in self.stage_map.items():
            if anchor in normalized_text:
                self.current_stage = stage
                residual_query = (
                    normalized_text.replace(f"open {anchor}", "")
                    .replace(anchor, "")
                    .strip()
                )
                return stage, residual_query if residual_query else normalized_text

        return self.current_stage, normalized_text

    def evaluate_and_switch(self, raw_input: str) -> str:
        """Legacy latch API — returns only the active stage."""
        stage, _ = self.clean_and_evaluate(raw_input)
        return stage
