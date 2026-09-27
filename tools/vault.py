"""Obsidian vault tools. Read-only: Adam never writes to the vault."""
import os
from pathlib import Path

from config import load_config

MAX_READ_CHARS = 20000
MAX_RESULTS = 30


def _vault():
    v = load_config().get("obsidian_vault", "").strip()
    if not v:
        raise ValueError("obsidian_vault is not set in config.json.")
    p = Path(os.path.expanduser(v))
    if not p.is_dir():
        raise ValueError(f"Vault folder not found: {p}")
    return p.resolve()


def _notes(vault):
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]  # skip .obsidian, .trash
        for f in filenames:
            if f.lower().endswith(".md"):
                yield Path(dirpath) / f


def read_note(filename):
    vault = _vault()
    name = filename.strip()
    if not name.lower().endswith(".md"):
        name += ".md"
    direct = (vault / name).resolve()
    if direct.is_relative_to(vault) and direct.is_file():
        path = direct
    else:
        target = Path(name).name.lower()
        matches = [n for n in _notes(vault) if n.name.lower() == target]
        if not matches:
            return f"Note not found: {filename}"
        if len(matches) > 1:
            return "Several notes have that name; use the path:\n" + \
                "\n".join(str(m.relative_to(vault)) for m in matches)
        path = matches[0]
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > MAX_READ_CHARS:
        text = text[:MAX_READ_CHARS] + f"\n... [truncated, note is {len(text):,} chars]"
    return f"{path.relative_to(vault)}\n\n{text}"


def search_vault(query):
    vault = _vault()
    q = query.lower()
    title_hits, content_hits = [], []
    for note in _notes(vault):
        rel = str(note.relative_to(vault))
        if q in note.stem.lower():
            title_hits.append(f"[title] {rel}")
            continue
        try:
            text = note.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if q in line.lower():
                content_hits.append(f"[text]  {rel}: {line.strip()[:160]}")
                break
    hits = title_hits + content_hits
    if not hits:
        return f"No notes match '{query}'."
    more = f"\n... and {len(hits) - MAX_RESULTS} more" if len(hits) > MAX_RESULTS else ""
    return "\n".join(hits[:MAX_RESULTS]) + more
