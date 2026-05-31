import asyncio
from mcp.server.fastmcp import FastMCP
from agents.outlook_agent import OutlookAgent

# Initialize official server protocol wrapper
server = FastMCP("Outlook-Mail-Server")
worker = OutlookAgent()

# Context cache to hold drafts for validation loops
pending_state = {}

@server.tool()
async def stage_email(recipient: str, body: str) -> str:
    """
    Stages an email draft with a generic recipient and message body. 
    Requires user confirmation before physical execution.
    
    Args:
        recipient (str): Name or email of the receiver (e.g., 'Sarah', 'Manager').
        body (str): Message payload contents.
    """
    pending_state["current"] = {"recipient": recipient, "body": body}
    
    # Return conversational interrupt validation back to the LLM client
    return (
        f"[CONFIRMATION_REQUIRED] I have staged an email draft to '{recipient}' "
        f"containing: '{body}'. Sir, please tell me to 'confirm' or 'modify the text'."
    )

@server.tool()
async def confirm_and_send_email() -> str:
    """Executes and opens the currently pending staged email draft in Microsoft Outlook."""
    draft = pending_state.get("current")
    if not draft:
        return "Operational error: No pending email drafts exist to confirm, sir."
    
    # Execute through the decoupled agent worker
    status = worker.run(draft)
    pending_state.clear() # Reset cache
    return status

if __name__ == "__main__":
    # Fire up using standard input/output protocol transport lines
    server.run(transport="stdio")