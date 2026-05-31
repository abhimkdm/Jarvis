import re

class SystemStateEngine:
    def __init__(self):
        # Explicit intent keywords mapped to your architectural tasks
        self.code_keywords = ["write code", "python", "script", "bug", "debug", "function", "program"]
        self.creative_keywords = ["story", "poem", "joke", "creative", "imagine", "write a song"]
        self.mcp_triggers = ["notepad", "email", "mail", "send", "write in", "outlook"]

    def evaluate_runtime_parameters(self, user_text, is_mcp_awaiting=False):
        """
        Analyzes conversational context and dynamically scales model parameters.
        Returns a dictionary containing the optimal temperature and system tone guidance.
        """
        cleaned = user_text.lower()

        # 1. CRITICAL STATE: Official Standard MCP Tool Interactions
        if is_mcp_awaiting or any(trigger in cleaned for trigger in self.mcp_triggers):
            return {
                "temperature": 0.0,
                "description": "Deterministic Protocol Execution"
            }

        # 2. STATE: Technical Code Generation / Debugging
        if any(kw in cleaned for kw in self.code_keywords):
            return {
                "temperature": 0.2,
                "description": "Low-Variance Analytical Code Generation"
            }

        # 3. STATE: High-Variance Creative Generation
        if any(kw in cleaned for kw in self.creative_keywords):
            return {
                "temperature": 1.1,
                "description": "High-Variance Creative Exploration"
            }

        # 4. STATE: Factual Q&A (e.g., What is, explain, define, how many)
        if any(kw in cleaned for kw in ["what is", "how to", "explain", "why does", "define", "history"]):
            return {
                "temperature": 0.3,
                "description": "Grounded Information Retrieval"
            }

        # 5. DEFAULT STATE: Casual Conversational Chat
        return {
            "temperature": 0.7,
            "description": "Balanced Conversational Dialogue"
        }