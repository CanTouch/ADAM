"""File system tools. Nothing here asks for confirmation; approval.py decides that."""
import os
import shutil
import time
from pathlib import Path

from send2trash import send2trash

from config import NOTES_DIR

MAX_READ_CHARS = 20000
MAX_LIST = 500
MAX_SEARCH_RESULTS = 100
SEARCH_TIME_LIMIT = 30  # seconds


def _p(path):
    return Path(os.path.expandvars(os.path.expanduser(str(path).strip().strip('"'))))


def list_files(path):
    p = _p(path)
    if not p.is_dir():
        return f"Error: not a folder: {p}"
    entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    lines = []
    for e in entries[:MAX_LIST]:
        try:
            lines.append(f"[folder] {e.name}" if e.is_dir() else f"[file]   {e.name}  ({e.stat().st_size:,} bytes)")
        except OSError:
            lines.append(f"[?]      {e.name}")
    if len(entries) > MAX_LIST:
        lines.append(f"... and {len(entries) - MAX_LIST} more")
    return f"{p}: {len(entries)} items\n" + "\n".join(lines) if lines else f"{p} is empty"


def read_file(path):
    p = _p(path)
    if not p.is_file():
        return f"Error: file not found: {p}"
    with open(p, "rb") as f:
        head = f.read(4096)
    if b"\x00" in head:
        return f"{p} is a binary file ({p.stat().st_size:,} bytes); cannot show as text."
    text = p.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_READ_CHARS:
        return text[:MAX_READ_CHARS] + f"\n... [truncated, file is {len(text):,} chars]"
    return text


def search_files(query, root):
    base = _p(root)
    if not base.is_dir():
        return f"Error: not a folder: {base}"
    q = query.lower()
    hits, deadline = [], time.monotonic() + SEARCH_TIME_LIMIT
    for dirpath, dirnames, filenames in os.walk(base, onerror=lambda e: None):
        for name in dirnames + filenames:
            if q in name.lower():
                hits.append(os.path.join(dirpath, name))
                if len(hits) >= MAX_SEARCH_RESULTS:
                    return "\n".join(hits) + f"\n... stopped at {MAX_SEARCH_RESULTS} results"
        if time.monotonic() > deadline:
            return ("\n".join(hits) + "\n" if hits else "") + \
                f"... search stopped after {SEARCH_TIME_LIMIT}s; try a narrower root"
    return "\n".join(hits) if hits else f"No files matching '{query}' under {base}"


def move_file(src, dst):
    s, d = _p(src), _p(dst)
    if not s.exists():
        return f"Error: source not found: {s}"
    target = d / s.name if d.is_dir() else d
    if target.exists():
        return f"Error: {target} already exists; not overwriting."
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(target))
    return f"Moved {s} -> {target}"


def delete_file(path):
    p = _p(path)
    if not p.exists():
        return f"Error: not found: {p}"
    send2trash(str(p))
    return f"Sent to Recycle Bin: {p}"


def note_path(filename):
    """Where write_note puts a file: always inside AgentSandbox/notes, always .md."""
    name = Path(str(filename).strip()).name or "note"
    if not name.lower().endswith(".md"):
        name += ".md"
    return NOTES_DIR / name


def write_note(content, filename):
    p = note_path(filename)
    if p.exists():
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
        return f"Appended to {p}"
    p.write_text(content, encoding="utf-8")
    return f"Created {p}"
