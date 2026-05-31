import subprocess

NAME = "open_chrome"
MATCH = ["open chrome", "launch chrome", "open browser"]
DESCRIPTION = "Launches Google Chrome web browser natively."


def exec_command():
    subprocess.Popen(["cmd", "/c", "start chrome"], shell=True)
    return "I have successfully launched Google Chrome, sir."
