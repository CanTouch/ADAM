"""Which actions wait for a y/n, and how to read the answer."""
import re

from tools.files import note_path

# Reads, searches and everything else run straight away.
ALWAYS_CONFIRM = {"delete_file", "move_file", "fill_form", "click", "forget"}


def needs_confirm(name, args):
    """Confirm deletes, moves, form filling, clicks, and changes to a file that already exists."""
    if name in ALWAYS_CONFIRM:
        return True
    if name == "write_note":
        return note_path(args.get("filename", "")).exists()
    return False


def reason(name, args):
    """A short note shown with the y/n question, when the call itself isn't clear enough."""
    if name == "write_note":
        return f"{note_path(args.get('filename', '')).name} already exists; this adds to it."
    return ""


def parse_answer(text):
    """True for yes, False for no, None if unclear. Tolerates dictation like 'Yes.'"""
    t = re.sub(r"[^a-z]", "", text.lower())
    if t in ("y", "yes", "yeah", "yep", "ok", "okay"):
        return True
    if t in ("n", "no", "nope"):
        return False
    return None
