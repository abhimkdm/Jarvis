class ChatMemoryPlugin:
    def __init__(self, max_turns=5):
        self.history = []
        self.max_turns = max_turns

    def execute(self, user_text, context=None):
        """
        Memory doesn't stop execution, it intercepts context.
        If 'context' dictionary is passed, it injects history into it.
        """
        if context is not None and "messages" in context:
            # Append historical logs into the message context loop
            context["messages"].extend(self.history)
        return None

    def update_memory(self, user_text, assistant_reply):
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_reply})
        if len(self.history) > self.max_turns * 2:
            self.history.pop(0)
            self.history.pop(0)