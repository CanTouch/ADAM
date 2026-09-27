"""Desktop pop-ups, so Adam can be used by voice while its window stays out of the way.

Each new pop-up replaces the previous one instead of stacking up.
"""
import subprocess
import threading

from config import PROJECT_DIR

ICON = PROJECT_DIR / "adam_icon.png"


class Notifier:
    def __init__(self):
        self._id = None
        self._lock = threading.Lock()

    def show(self, title, body="", urgent=False):
        """Show a pop-up in the background. urgent ones stay until dismissed."""
        threading.Thread(target=self._show, args=(title, body, urgent), daemon=True).start()

    def _show(self, title, body, urgent):
        with self._lock:
            cmd = ["notify-send", "-a", "Adam", "-i", str(ICON), "-p",
                   "-u", "critical" if urgent else "normal"]
            if self._id:
                cmd += ["-r", self._id]
            try:
                out = subprocess.run(cmd + [title, body], capture_output=True, text=True, timeout=5)
                self._id = out.stdout.strip() or self._id
            except (OSError, subprocess.SubprocessError):
                pass
