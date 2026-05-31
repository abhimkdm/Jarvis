import subprocess

NAME = "open_notepad"
MATCH = ["open notepad", "launch notepad", "run notepad"]
DESCRIPTION = "Launches a completely blank instance of Notepad."


def exec_command():
    subprocess.Popen(["cmd", "/c", "start notepad.exe"], shell=True)
    return "Opening a blank Notepad instance for you now, sir."
