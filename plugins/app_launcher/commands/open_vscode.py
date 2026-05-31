import subprocess

NAME = "open_vscode"
MATCH = ["open vscode", "launch vscode", "open vs code", "open code"]
DESCRIPTION = "Launches Visual Studio Code on Windows natively."


def exec_command():
    subprocess.Popen(["cmd", "/c", "code"], shell=True)
    return "Opening Visual Studio Code workspace environment, sir."
