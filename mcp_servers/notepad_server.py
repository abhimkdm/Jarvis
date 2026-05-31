import os
import sys

# ─── SYS PATH PATCH: Forces the background subprocess to see your root workspace ───
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from mcp.server.fastmcp import FastMCP
from agents.notepad_agent import NotepadAgent

server = FastMCP("Notepad-Server")
worker = NotepadAgent()
pending_state = {}

@server.tool()
async def stage_note(text_payload: str) -> str:
    """
    Stages a block of text to be written into Notepad. Requires validation.
    
    Args:
        text_payload (str): The exact note characters or words to write down.
    """
    pending_state["current"] = text_payload
    return f"[CONFIRMATION_REQUIRED] Staged note: '{text_payload}'. Should I write this into Notepad, sir?"

@server.tool()
async def confirm_and_open_notepad() -> str:
    """Executes the action, launching Notepad and physically typing the staged text."""
    note = pending_state.get("current")
    if not note:
        return "Operational error: No pending notes exist to write, sir."
        
    status = worker.run(note)
    pending_state.clear()
    return status

if __name__ == "__main__":
    server.run(transport="stdio")