"""Adam's long-term memory: one markdown file of facts, read into every prompt."""
from config import MEMORY_FILE

MAX_FACT_CHARS = 300
MAX_PROMPT_CHARS = 4000


def _facts():
    if not MEMORY_FILE.exists():
        return []
    lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
    return [l[2:].strip() for l in lines if l.startswith("- ") and l[2:].strip()]


def _save(facts):
    MEMORY_FILE.write_text("".join(f"- {f}\n" for f in facts), encoding="utf-8")


def for_prompt():
    """The remembered facts as prompt text, newest kept if the file grows too long."""
    lines, size = [], 0
    for fact in reversed(_facts()):
        size += len(fact) + 3
        if size > MAX_PROMPT_CHARS:
            break
        lines.append(f"- {fact}")
    return "\n".join(reversed(lines))


def remember(fact):
    fact = " ".join(str(fact).split())[:MAX_FACT_CHARS]
    if not fact:
        return "Error: nothing to remember."
    facts = _facts()
    if fact.lower() in (f.lower() for f in facts):
        return f"Already remembered: {fact}"
    _save(facts + [fact])
    return f"Remembered: {fact}"


def forget(text):
    q = str(text).strip().lower()
    if not q:
        return "Error: say what to forget."
    facts = _facts()
    keep = [f for f in facts if q not in f.lower()]
    gone = [f for f in facts if q in f.lower()]
    if not gone:
        return f"Nothing remembered matches '{text}'."
    _save(keep)
    return "Forgot:\n" + "\n".join(f"- {f}" for f in gone)
