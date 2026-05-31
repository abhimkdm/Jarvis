import os
import sys
import subprocess

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print(f"[CRITICAL APPLICATION SERVER ERROR]: Missing dependencies: {e}", file=sys.stderr)
    sys.exit(1)

server = FastMCP("System-Apps-Server")

@server.tool()
async def open_application(app_name: str) -> str:
    """
    Launches a requested standard desktop application on Windows natively.

    Args:
        app_name (str): The common name of the application to launch ('chrome', 'outlook', 'vscode', 'notepad', 'calc').
    """
    if isinstance(app_name, list):
        target = str(app_name[0]).lower().strip()
    else:
        target = str(app_name).lower().strip()

    try:
        if "chrome" in target:
            subprocess.Popen(["cmd", "/c", "start chrome"], shell=True)
            return "I have successfully launched Google Chrome, sir."

        elif "outlook" in target:
            subprocess.Popen(["cmd", "/c", "start outlook"], shell=True)
            return "Deploying Microsoft Outlook now, sir."

        elif "notepad" in target:
            subprocess.Popen(["cmd", "/c", "start notepad.exe"], shell=True)
            return "Opening a blank Notepad instance for you now, sir."

        elif "calc" in target or "calculator" in target:
            subprocess.Popen(["cmd", "/c", "start calc"], shell=True)
            return "Launching the Windows Calculator interface, sir."

        elif "vscode" in target or "vs code" in target or target == "code":
            subprocess.Popen(["cmd", "/c", "code"], shell=True)
            return "Opening Visual Studio Code workspace environment, sir."

        else:
            return f"I could not locate an execution routine for '{target}' inside my matrix, sir."

    except Exception as e:
        return f"Operational error while attempting to boot the application process: {str(e)}"

if __name__ == "__main__":
    server.run(transport="stdio")
