"""The loop: propose -> execute -> report -> next (approval.py decides what waits for y/n).

Everything that touches the model, tools, or browser runs on one worker thread.
The window thread only calls handle_input(), which just hands text over.
"""
import json
import queue
import re
import threading
import uuid

import approval
import tools
from logger import log

MAX_STEPS = 25          # per task
MAX_HISTORY = 60        # messages kept across tasks
MAX_CONTEXT_CHARS = 120000  # about 30k tokens; each step resends the whole history
MAX_TOOL_RESULT = 20000
OLD_TOOL_RESULT = 1500  # older results shrink to this when the history gets too long
DISPLAY_CHARS = 300
VOICE_COMMANDS = {"voice on": True, "unmute": True, "voice off": False, "mute": False}


def _plain(text):
    """Strip the markdown some models add (bold stars, headings, code marks, links) so replies read and sound clean."""
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)   # [label](url) -> label (url)
    text = re.sub(r"(\*\*|__|\*|`)(.+?)\1", r"\2", text)                  # **bold**, *italic*, `code`
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)                       # headings
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)                    # bullet marks
    return text.strip()


def _short(value, n=DISPLAY_CHARS):
    s = str(value)
    return s if len(s) <= n else s[:n] + "..."


class Agent:
    def __init__(self, ui, brain, voice=None):
        """ui needs post(text), show_image(path) and notify(title, body, urgent), all thread-safe."""
        self.ui = ui
        self.brain = brain
        self.voice = voice
        self.history = []
        self._jobs = queue.Queue()
        self._answers = queue.Queue()
        self._busy = False
        self._awaiting = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    @property
    def busy(self):
        return self._busy

    @property
    def awaiting(self):
        """True while an action is waiting for the user's y/n."""
        return self._awaiting

    # ---- window thread ----

    def handle_input(self, text):
        cmd = text.strip().lower().rstrip(".!")
        if cmd in VOICE_COMMANDS and self.voice:
            self.voice.set_enabled(VOICE_COMMANDS[cmd])
            self.ui.post("Voice on." if VOICE_COMMANDS[cmd] else "Voice off.")
            return
        if cmd == "stop":
            if self.voice:
                self.voice.stop_speaking()
            if self._busy:
                self._stop.set()
                if self._awaiting:
                    self._answers.put(False)
                self.ui.post("Stopping.")
            else:
                self.ui.post("Nothing running.")
            return
        if self._awaiting:
            self._answers.put(text)
            return
        if self._busy:
            self.ui.post("Busy. Type stop to cancel the current task.")
            self.ui.notify("Adam is still busy", "Say or type stop to cancel the current task.")
            return
        self._busy = True
        self._jobs.put(("task", text))

    def shutdown(self, timeout=5):
        self._stop.set()
        if self._awaiting:
            self._answers.put(False)
        self._jobs.put(("quit", None))
        self._thread.join(timeout)

    # ---- worker thread ----

    def _worker(self):
        while True:
            kind, payload = self._jobs.get()
            if kind == "quit":
                return
            self._busy = True
            try:
                self._run_task(payload)
            except Exception as e:
                self.ui.post(f"Error: {e}")
                self.ui.notify("Adam hit an error", str(e))
            finally:
                self._stop.clear()
                self._busy = False

    def _ask(self):
        """Block until the user types y or n. Returns True/False."""
        self._awaiting = True
        try:
            while True:
                answer = self._answers.get()
                if isinstance(answer, bool):
                    return answer
                parsed = approval.parse_answer(answer)
                if parsed is not None:
                    return parsed
                self.ui.post("Type y or n.")
        finally:
            self._awaiting = False

    def _run_task(self, text):
        self.history.append({"role": "user", "content": text})
        for _ in range(MAX_STEPS):
            if self._stop.is_set():
                self.history.append({"role": "user", "content": "[User stopped the task.]"})
                break
            self._fit()
            try:
                msg = self.brain.next(self.history)
            except Exception as e:
                log("model", {}, "error", str(e))
                self.ui.post(f"Model error: {e}")
                self.ui.notify("Adam couldn't reach its AI model", _short(e, 200))
                break

            if not msg.tool_calls:
                reply = _plain(msg.content or "") or "Okay."
                self.history.append({"role": "assistant", "content": reply})
                self.ui.post(f"Adam: {reply}")
                self.ui.notify("Adam", reply)
                if self.voice:
                    self.voice.speak(reply)
                break

            call = msg.tool_calls[0]  # One action at a time; extra calls are dropped.
            call_id = call.id or f"call_{uuid.uuid4().hex[:8]}"
            name = call.function.name
            self.history.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [{"id": call_id, "type": "function",
                                "function": {"name": name, "arguments": call.function.arguments}}],
            })
            result = self._step(name, call.function.arguments)
            self.history.append({"role": "tool", "tool_call_id": call_id,
                                 "content": _short(result, MAX_TOOL_RESULT)})
        else:
            self.ui.post(f"Stopped after {MAX_STEPS} steps.")
            self.ui.notify("Adam stopped", f"It took more than {MAX_STEPS} steps.")
        self._trim()

    def _step(self, name, raw_args):
        """Show, approve, execute and log one action. Returns the result text for the model."""
        try:
            args = json.loads(raw_args) if raw_args and raw_args.strip() else {}
            if not isinstance(args, dict):
                raise ValueError("arguments must be an object")
        except (json.JSONDecodeError, ValueError) as e:
            log(name, {"raw": raw_args}, "invalid", str(e))
            self.ui.post(f"Adam -> {name}: bad parameters, asking again.")
            return f"Error: could not parse arguments: {e}"

        shown = ", ".join(f"{k}={_short(v, 200)!r}" for k, v in args.items())
        self.ui.post(f"Adam -> {name}({shown})")

        func = tools.FUNCTIONS.get(name)
        if func is None:
            log(name, args, "invalid", "unknown tool")
            return f"Error: unknown tool '{name}'."

        decision = "auto"
        if approval.needs_confirm(name, args):
            why = approval.reason(name, args)
            self.ui.post(f"{why} Approve? (y/n)" if why else "Approve? (y/n)")
            self.ui.notify(f"Adam wants to {name.replace('_', ' ')}",
                           f"{why + ' ' if why else ''}{shown}\nPress Super+A and say yes or no.", urgent=True)
            if self.voice:
                self.voice.speak(f"Okay to {name.replace('_', ' ')}?")
            if not self._ask():
                log(name, args, "rejected", "not executed")
                self.ui.post("Rejected.")
                return "User rejected this action."
            decision = "approved"

        try:
            result = func(**args)
        except TypeError as e:
            result = f"Error: wrong parameters: {e}"
        except Exception as e:
            result = f"Error: {e}"
        log(name, args, decision, result)
        self.ui.post(f"  {_short(result)}")
        if name == "screenshot" and not str(result).startswith("Error"):
            self.ui.show_image(str(result).split(": ", 1)[1])
        return result

    def _size(self):
        return sum(len(str(m.get("content", ""))) for m in self.history)

    def _fit(self):
        """Keep the history under MAX_CONTEXT_CHARS: shrink old tool results, then drop old tasks."""
        if self._size() <= MAX_CONTEXT_CHARS:
            return
        old_results = [m for m in self.history if m["role"] == "tool"][:-1]  # newest stays whole
        for m in old_results:
            if len(m["content"]) > OLD_TOOL_RESULT:
                m["content"] = m["content"][:OLD_TOOL_RESULT] + "... [trimmed]"
                if self._size() <= MAX_CONTEXT_CHARS:
                    return
        while self._size() > MAX_CONTEXT_CHARS and self._drop_oldest_task():
            pass

    def _drop_oldest_task(self):
        """Remove messages up to the second user message. False if only the current task is left."""
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        if len(starts) < 2:
            return False
        del self.history[:starts[1]]
        return True

    def _trim(self):
        self._fit()
        if len(self.history) <= MAX_HISTORY:
            return
        self.history = self.history[-MAX_HISTORY:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)
