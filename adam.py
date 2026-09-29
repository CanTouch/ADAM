"""ADAM entry point."""
import os
import signal
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from config import CONFIG_PATH, ensure_sandbox, load_config


def already_running(listen):
    """Hold a lock for Adam's lifetime. If another Adam has it, bring that one forward.

    The lock file holds the running Adam's PID. SIGUSR1 asks it to come forward,
    SIGUSR2 to listen without coming forward (the Super+A shortcut).
    """
    global _lock
    import fcntl
    from config import SANDBOX
    _lock = open(SANDBOX / "adam.lock", "a+")
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _lock.seek(0)
        try:
            os.kill(int(_lock.read().strip()), signal.SIGUSR2 if listen else signal.SIGUSR1)
        except (ValueError, OSError):
            pass
        if not listen:  # Super+A listens in the background; opening Adam shows it
            subprocess.run(["wmctrl", "-F", "-a", "Adam"], capture_output=True)
        return True
    _lock.truncate(0)
    _lock.write(str(os.getpid()))
    _lock.flush()
    return False


def main():
    listen = "--listen" in sys.argv
    ensure_sandbox()
    if sys.platform.startswith("linux") and already_running(listen):
        return
    # The PID is published now, so catch Super+A presses (which would otherwise kill
    # the process) until the window exists to act on them.
    early = []
    signal.signal(signal.SIGUSR1, lambda *_: early.append(False))
    signal.signal(signal.SIGUSR2, lambda *_: early.append(True))
    cfg = load_config()

    # Imported after setup so the sandbox folders exist before tools load.
    from agent import Agent
    from brain import Brain
    from tools.browser import bridge
    from voice import Voice
    from window import AdamWindow

    bridge.start()

    agent = None

    def on_submit(text):
        if agent is None:
            window.post(f"Add your api_key to {CONFIG_PATH}, then restart Adam.")
        else:
            agent.handle_input(text)

    def on_close():
        if agent:
            agent.shutdown()

    window = AdamWindow(on_submit, on_close)
    voice = Voice(enabled=cfg["speak_replies"])
    voice.warm_up()

    def heard(text):
        if text:
            window.notify("Adam heard", text)
            window.submit_text(text)
        else:
            window.post("Didn't catch that. Press Super+A and try again.")
            window.notify("Didn't catch that", "Press Super+A and try again.")

    def listen_now():
        """UI thread: record in the background and submit what was said. The window stays put."""
        voice.stop_speaking()
        if voice.listening:  # pressed again: the user is done talking
            voice.finish_listening()
            return
        window.notify("Adam is listening...")

        def work():
            try:
                text = voice.listen()
            except Exception as e:
                window.post(f"Microphone error: {e}")
                window.notify("Microphone error", str(e))
                return
            window.call(lambda: heard(text))
        threading.Thread(target=work, daemon=True).start()

    window.attach(voice=voice, bridge=bridge, listen=listen_now)
    signal.signal(signal.SIGUSR1, lambda *_: window.call(window.summon))
    signal.signal(signal.SIGUSR2, lambda *_: window.call(listen_now))
    listen = listen or any(early)
    if early and not listen:
        window.call(window.summon)

    if not cfg["api_key"]:
        window.post(f"First run: add your api_key to {CONFIG_PATH}, then restart Adam.")
    else:
        agent = Agent(window, Brain(cfg), voice)
        window.attach(agent=agent)
        window.post("Adam ready." if not bridge.error else bridge.error)
        if not cfg["obsidian_vault"]:
            window.post("(obsidian_vault not set; vault tools are off until you add it.)")
        if listen:
            window.call(listen_now)
    window.run()


def report_crash():
    """pythonw has no console, so write the error to a file and show it in a popup."""
    err = traceback.format_exc()
    Path(__file__).resolve().parent.joinpath("adam_error.txt").write_text(err, encoding="utf-8")
    print(err)
    try:
        from tkinter import messagebox
        messagebox.showerror("Adam crashed", err[-1500:])
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        report_crash()
        raise
