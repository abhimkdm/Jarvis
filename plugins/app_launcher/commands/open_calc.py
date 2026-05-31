import subprocess

NAME = "open_calculator"
MATCH = ["open calculator", "open cal", "launch calculator", "run calculator"]
DESCRIPTION = "Launches the native Windows calculator accessory utility."


def exec_command():
    subprocess.Popen(["cmd", "/c", "start calc"], shell=True)
    return "Launching the Windows Calculator interface, sir."
