"""The Adam window: a dark HUD with a living orb, the conversation, and a command bar.

The orb's colour and motion show what Adam is doing: idle (blue), listening (teal),
working (violet), speaking (sky blue), waiting for your OK (amber), error (red).
Its frames are drawn once in the background and cached on disk.
"""
import hashlib
import queue
import random
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageTk

import orb
from config import SANDBOX
from notify import Notifier

WIDTH, HEIGHT = 440, 480
ORB = 128                # orb frame size in pixels
THUMB = (380, 220)       # screenshot preview size
ORB_CACHE = SANDBOX / "cache"

BG = "#060912"
FIELD = "#0d1430"
EDGE = "#1c2a52"
TEXT = "#dfe8ff"
DIM = "#8190bb"
FAINT = "#4c5878"
CYAN = "#39e0ff"
AMBER = "#ffb547"
RED = "#ff5d73"
GREEN = "#3dffa8"

LABELS = {"idle": "STANDING BY", "listening": "LISTENING", "thinking": "WORKING",
          "speaking": "SPEAKING", "waiting": "NEEDS YOUR OK", "error": "SOMETHING WENT WRONG"}
ORDER = ["idle", "thinking", "listening", "speaking", "waiting", "error"]  # render order
ERROR_PREFIXES = ("Error", "Model error", "Microphone error", "Could not", "Chrome isn't")
ERROR_SECONDS = 4
IDLE_MS, ACTIVE_MS = 125, 50   # orb frame time: a slow breath at rest, lively otherwise
POLL_MS = 100                  # how often messages from other threads are picked up
HINT = "Super+A to talk   ·   Enter to send"


def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def _mix(a, b, amount):
    """Blend colour a toward colour b by amount (0..1)."""
    return tuple(x + (y - x) * amount for x, y in zip(a, b))


def _family(root, *names):
    have = set(tkfont.families(root))
    return next((n for n in names if n in have), "TkDefaultFont")


def _button_image(kind, ring, icon, fill, size=34):
    """A round, anti-aliased icon button drawn at 4x and scaled down."""
    s = 4
    n = size * s
    im = Image.new("RGB", (n, n), _rgb(BG))
    d = ImageDraw.Draw(im)
    d.ellipse((s, s, n - s, n - s), fill=fill, outline=ring, width=int(1.5 * s))
    c, w = n / 2, int(1.7 * s)
    if kind == "mic":
        cy = c - 0.07 * n
        d.rounded_rectangle((c - 0.1 * n, cy - 0.17 * n, c + 0.1 * n, cy + 0.08 * n), radius=0.1 * n, fill=icon)
        d.arc((c - 0.19 * n, cy - 0.19 * n, c + 0.19 * n, cy + 0.19 * n), 10, 170, fill=icon, width=w)
        d.line((c, cy + 0.19 * n, c, c + 0.23 * n), fill=icon, width=w)
        d.line((c - 0.1 * n, c + 0.23 * n, c + 0.1 * n, c + 0.23 * n), fill=icon, width=w)
    elif kind.startswith("speaker"):
        x = c - 0.07 * n
        d.rectangle((x - 0.14 * n, c - 0.07 * n, x - 0.04 * n, c + 0.07 * n), fill=icon)
        d.polygon([(x - 0.05 * n, c - 0.07 * n), (x + 0.08 * n, c - 0.18 * n),
                   (x + 0.08 * n, c + 0.18 * n), (x - 0.05 * n, c + 0.07 * n)], fill=icon)
        if kind == "speaker_on":
            for r in (0.12, 0.21):
                d.arc((x + 0.08 * n - r * n, c - r * n, x + 0.08 * n + r * n, c + r * n), -45, 45, fill=icon, width=w)
        else:
            d.line((x + 0.16 * n, c - 0.08 * n, x + 0.3 * n, c + 0.08 * n), fill=icon, width=w)
            d.line((x + 0.16 * n, c + 0.08 * n, x + 0.3 * n, c - 0.08 * n), fill=icon, width=w)
    else:  # stop
        d.rounded_rectangle((c - 0.12 * n, c - 0.12 * n, c + 0.12 * n, c + 0.12 * n), radius=0.035 * n, fill=icon)
    return im.resize((size, size), Image.LANCZOS)


# look -> (ring, icon, fill)
LOOKS = {
    "normal":   (EDGE, DIM, "#0b1128"),
    "hover":    (CYAN, TEXT, "#0d1936"),
    "active":   (CYAN, "#bff6ff", "#0a2e40"),
    "disabled": ("#121a33", "#2a3456", BG),
}


def _dot(color, size=12):
    """A small glowing status light."""
    n = size * 4
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    r = np.hypot(x - (n - 1) / 2, y - (n - 1) / 2) / (n / 2)
    a = np.clip((0.42 - r) * 12, 0, 1) + np.exp(-((r / 0.55) ** 2)) * 0.45
    a = np.clip(a, 0, 1)[..., None]
    img = np.array(_rgb(BG), np.float32) * (1 - a) + np.array(color, np.float32) * a
    return Image.fromarray(img.astype(np.uint8), "RGB").resize((size, size), Image.LANCZOS)


class IconButton(tk.Label):
    """A round image button with hover, active and disabled looks."""

    def __init__(self, parent, window, kind, command, tip):
        super().__init__(parent, bg=BG, bd=0, cursor="hand2")
        self.window, self.kind, self.command, self.tip = window, kind, command, tip
        self.active = self.disabled = self._hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: None if self.disabled else self.command())
        self._draw()

    def _set_hover(self, on):
        self._hover = on
        self.window.show_hint(self.tip if on else None)
        self._draw()

    def update_look(self, kind=None, active=None, disabled=None):
        changed = False
        for name, value in (("kind", kind), ("active", active), ("disabled", disabled)):
            if value is not None and getattr(self, name) != value:
                setattr(self, name, value)
                changed = True
        if changed:
            self._draw()

    def _draw(self):
        look = ("disabled" if self.disabled else "active" if self.active
                else "hover" if self._hover else "normal")
        self.configure(image=self.window.button_photo(self.kind, look))


class AdamWindow:
    def __init__(self, on_submit, on_close=None):
        """on_submit(text) is called on the UI thread each time the user presses Enter."""
        self.on_submit = on_submit
        self.on_close = on_close
        self._inbox = queue.Queue()  # Messages from worker threads, drained on the UI thread.
        self._notifier = Notifier()
        self._agent = self._voice = self._bridge = self._listen = None
        self._frames = {}            # state -> list of PhotoImage
        self._photos = {}            # other images that Tk must keep a reference to
        self._thumbs = []
        self._tick = 0
        self._state = None
        self._error_until = 0.0
        self._level = 0.0
        self._hint = None

        self.root = tk.Tk()
        self.root.title("Adam")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{WIDTH}x{HEIGHT}+{sw - WIDTH - 20}+40")
        self.root.minsize(360, 340)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        display = _family(self.root, "Orbitron", "Ubuntu Sans", "Cantarell")
        body = _family(self.root, "Ubuntu Sans", "Ubuntu", "Cantarell", "DejaVu Sans")
        mono = _family(self.root, "Ubuntu Sans Mono", "Ubuntu Mono", "DejaVu Sans Mono")
        self.fonts = {
            "title": (display, 17, "bold"), "tag": (display, 7), "state": (display, 9, "bold"),
            "light": (display, 7), "body": (body, 10), "reply": (body, 11), "bold": (body, 10, "bold"),
            "sys": (body, 9, "italic"), "mono": (mono, 9), "monob": (mono, 9, "bold"), "hint": (body, 8),
        }

        self._build_header()
        self._build_command_bar()
        self._build_transcript()

        threading.Thread(target=self._load_orb, daemon=True).start()
        self.root.after(POLL_MS, self._drain)
        self.root.after(100, self._animate)

    # ---- layout ----

    def _build_header(self):
        h = ORB + 6
        self.header = tk.Canvas(self.root, height=h, bg=BG, highlightthickness=0, bd=0)
        self.header.pack(fill="x")
        rng = random.Random(7)
        for _ in range(90):  # a faint star field behind the text
            x, y = rng.randint(0, 1600), rng.randint(2, h - 4)
            self.header.create_rectangle(x, y, x + 1, y + 1, width=0,
                                         fill=rng.choice(("#161e3a", "#1f2a4c", "#2c3a66", "#46558a")))
        self._orb_item = self.header.create_image(4, 0, anchor="nw")
        cx, cy = 4 + ORB // 2, ORB // 2
        self._orb_center = (cx, cy)
        self._level_rings = [self.header.create_oval(cx, cy, cx, cy, width=w, outline=BG, state="hidden")
                             for w in (1, 2)]
        x = ORB + 14
        self.header.create_text(x, 36, text="A.D.A.M", anchor="w", fill=TEXT, font=self.fonts["title"])
        self.header.create_text(x + 1, 58, text="PERSONAL COMPUTER AGENT", anchor="w",
                                fill=FAINT, font=self.fonts["tag"])
        self._state_text = self.header.create_text(x + 1, 81, text="", anchor="w", font=self.fonts["state"])
        self._lights = {}
        for i, name in enumerate(("CHROME", "VOICE")):
            lx = x + 1 + i * 92
            dot = self.header.create_image(lx, 104, anchor="w")
            self.header.create_text(lx + 16, 104, text=name, anchor="w", fill=DIM, font=self.fonts["light"])
            self._lights[name] = [dot, None]
        self._rule = self.header.create_image(0, h - 1, anchor="w")

    def _build_transcript(self):
        # height=1: take only the room left after the header and command bar.
        self.output = tk.Text(self.root, height=1, wrap="word", state="disabled", bg=BG, fg=TEXT, bd=0,
                              relief="flat", highlightthickness=0, padx=16, pady=10, cursor="arrow",
                              font=self.fonts["body"], selectbackground=EDGE, insertwidth=0,
                              spacing1=2, spacing3=2)
        self.output.pack(fill="both", expand=True, side="bottom")
        t = self.output.tag_configure
        t("you_mark", foreground=CYAN, font=self.fonts["bold"], spacing1=12)
        t("you", foreground="#bdf3ff", spacing1=12, lmargin2=16)
        t("adam_mark", foreground="#7fb8ff", font=self.fonts["bold"], spacing1=10)
        t("adam", foreground=TEXT, font=self.fonts["reply"], spacing1=10, lmargin2=18)
        t("act_name", foreground="#8fb5ff", font=self.fonts["monob"], lmargin1=18, spacing1=6)
        t("act", foreground="#6f7ea8", font=self.fonts["mono"], lmargin2=30)
        t("result", foreground=FAINT, font=self.fonts["mono"], lmargin1=30, lmargin2=30)
        t("ask", foreground=AMBER, font=self.fonts["bold"], lmargin1=18, lmargin2=18, spacing1=4)
        t("err", foreground=RED, lmargin1=18, lmargin2=18, spacing1=6)
        t("sys", foreground=DIM, font=self.fonts["sys"], spacing1=4)

    def _build_command_bar(self):
        self.hint = tk.Label(self.root, text=HINT, bg=BG, fg=FAINT, font=self.fonts["hint"])
        self.hint.pack(side="bottom", fill="x", pady=(3, 6))
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(side="bottom", fill="x", padx=12, pady=(4, 0))
        self.field = tk.Frame(bar, bg=FIELD, highlightthickness=1, highlightbackground=EDGE)
        self.field.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(self.field, bg=FIELD, fg=TEXT, insertbackground=CYAN, relief="flat", bd=0,
                              highlightthickness=0, font=self.fonts["reply"], selectbackground=EDGE)
        self.entry.pack(fill="x", padx=10, pady=7)
        self.entry.bind("<Return>", self._submit)
        self.entry.bind("<FocusIn>", lambda e: self.field.configure(highlightbackground=CYAN))
        self.entry.bind("<FocusOut>", lambda e: self.field.configure(highlightbackground=EDGE))
        self.entry.bind("<KeyRelease>", lambda e: self._placeholder())
        self._ph = tk.Label(self.field, text="Ask Adam anything...", bg=FIELD, fg=FAINT,
                            font=self.fonts["reply"], cursor="xterm")
        self._ph.bind("<Button-1>", lambda e: self.entry.focus_set())
        self._placeholder()

        self.mic = IconButton(bar, self, "mic", self._on_mic, "Talk to Adam (same as Super+A); press again when you're done")
        self.speaker = IconButton(bar, self, "speaker_on", self._on_speaker, "Spoken replies on or off")
        self.stop = IconButton(bar, self, "stop", self._on_stop, "Stop what Adam is doing or saying")
        for b in (self.stop, self.speaker, self.mic):
            b.pack(side="right", padx=(6, 0))

    def button_photo(self, kind, look):
        key = ("btn", kind, look)
        if key not in self._photos:
            self._photos[key] = ImageTk.PhotoImage(_button_image(kind, *LOOKS[look]))
        return self._photos[key]

    def _dot_photo(self, color):
        key = ("dot", color)
        if key not in self._photos:
            self._photos[key] = ImageTk.PhotoImage(_dot(_rgb(color)))
        return self._photos[key]

    def _placeholder(self):
        if self.entry.get():
            self._ph.place_forget()
        else:
            self._ph.place(in_=self.entry, x=4, rely=0.5, anchor="w")

    def show_hint(self, text=None):
        """UI thread: show text in the hint line, or the normal hint for None."""
        self._hint = text
        self._refresh_hint()

    def _refresh_hint(self):
        if self._hint:
            self.hint.configure(text=self._hint, fg=DIM)
        elif self._state == "waiting":
            self.hint.configure(text="Adam needs your OK: type y or n, or press Super+A and say it", fg=AMBER)
        else:
            self.hint.configure(text=HINT, fg=FAINT)

    # ---- wiring ----

    def attach(self, agent=None, voice=None, bridge=None, listen=None):
        """UI thread: give the window what it needs to show Adam's state and run its buttons."""
        self._agent = agent or self._agent
        self._voice = voice or self._voice
        self._bridge = bridge or self._bridge
        self._listen = listen or self._listen

    def _on_mic(self):
        if self._listen:
            self._listen()

    def _on_speaker(self):
        if self._voice:
            self._voice.set_enabled(not self._voice.enabled)
            self._append("Voice on." if self._voice.enabled else "Voice off.")

    def _on_stop(self):
        if self._voice:
            self._voice.stop_speaking()
        if self._agent and self._agent.busy:
            self._agent.handle_input("stop")

    # ---- public API ----

    def _submit(self, _event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._placeholder()
        self.submit_text(text)

    def submit_text(self, text):
        """UI thread only: send text as if it had been typed."""
        self._append(f"> {text}")
        self.on_submit(text)

    def call(self, fn):
        """Thread-safe: run fn() on the UI thread."""
        self._inbox.put(("call", fn))

    def summon(self):
        """UI thread only: bring the window forward with the cursor in the input field."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.entry.focus_set()

    def notify(self, title, body="", urgent=False):
        """Thread-safe: show a desktop pop-up, unless the user is already looking at Adam."""
        self.call(lambda: self._notify(title, body, urgent))

    def _notify(self, title, body, urgent):
        if urgent or self.root.state() != "normal" or self.root.focus_displayof() is None:
            self._notifier.show(title, body, urgent)

    def post(self, message):
        """Thread-safe: show a line in the conversation."""
        self._inbox.put(("text", message))

    def show_image(self, path):
        """Thread-safe: show a screenshot thumbnail in the conversation."""
        self._inbox.put(("image", path))

    def _drain(self):
        while not self._inbox.empty():
            kind, value = self._inbox.get_nowait()
            if kind == "text":
                self._append(value)
            elif kind == "call":
                value()
            else:
                self._show_preview(value)
        self.root.after(POLL_MS, self._drain)

    # ---- conversation ----

    def _append(self, message):
        """Style each line by what it is: you, Adam's reply, an action, its result, a question..."""
        parts = []
        if message.startswith("> "):
            parts = [("›  ", "you_mark"), (message[2:], "you")]
        elif message.startswith("Adam: "):
            parts = [("◆  ", "adam_mark"), (message[6:], "adam")]
        elif message.startswith("Adam -> "):
            name, _, args = message[8:].partition("(")
            parts = [("▸ " + name.replace("_", " ") + "  ", "act_name"), (args[:-1] if args.endswith(")") else args, "act")]
        elif message.startswith("  ") and not message.strip().startswith(ERROR_PREFIXES):
            parts = [(message.strip(), "result")]
        elif "(y/n)" in message or message == "Type y or n.":
            parts = [(message, "ask")]
        elif message.strip().startswith(ERROR_PREFIXES):
            parts = [(message.strip(), "err")]
            self._error_until = time.monotonic() + ERROR_SECONDS
        else:
            parts = [(message, "sys")]
        self.output.configure(state="normal")
        if self.output.index("end-1c") != "1.0":
            self.output.insert("end", "\n")
        for text, tag in parts:
            self.output.insert("end", text, tag)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _show_preview(self, path):
        """Put a screenshot thumbnail in the conversation; click it to open the full picture."""
        try:
            img = Image.open(path)
            # Fit the conversation's width, so the text never scrolls sideways.
            width = self.output.winfo_width()
            room = (width if width > 50 else WIDTH) - 2 * 16 - 2 * 18 - 4
            img.thumbnail((max(160, min(THUMB[0], room)), THUMB[1]))
        except OSError as e:
            self._append(f"Could not show screenshot: {e}")
            return
        photo = ImageTk.PhotoImage(img)
        self._thumbs.append(photo)
        label = tk.Label(self.output, image=photo, bd=0, highlightthickness=1,
                         highlightbackground=EDGE, cursor="hand2")
        label.bind("<Button-1>", lambda e: subprocess.Popen(["xdg-open", str(path)]))
        self.output.configure(state="normal")
        self.output.insert("end", "\n")
        self.output.window_create("end", window=label, padx=18, pady=6)
        self.output.see("end")
        self.output.xview_moveto(0)
        self.output.configure(state="disabled")

    # ---- orb ----

    def _load_orb(self):
        """Background thread: load each state's frames from the cache, drawing any that are missing."""
        key = hashlib.sha1(Path(orb.__file__).read_bytes()).hexdigest()[:10]
        ORB_CACHE.mkdir(parents=True, exist_ok=True)
        for old in ORB_CACHE.glob("orb-*.png"):
            if f"-{key}-{ORB}-" not in old.name:
                old.unlink(missing_ok=True)
        for state in ORDER:
            path = ORB_CACHE / f"orb-{key}-{ORB}-{state}.png"
            try:
                strip = Image.open(path)
                strip.load()
                if strip.size != (ORB * orb.FRAMES, ORB):
                    raise OSError("wrong size")
                images = [strip.crop((i * ORB, 0, (i + 1) * ORB, ORB)) for i in range(orb.FRAMES)]
            except OSError:
                images = orb.frames(state, ORB, _rgb(BG))
                strip = Image.new("RGB", (ORB * len(images), ORB))
                for i, im in enumerate(images):
                    strip.paste(im, (i * ORB, 0))
                strip.save(path)
            self.call(lambda s=state, im=images: self._frames_ready(s, im))

    def _frames_ready(self, state, images):
        self._frames[state] = [ImageTk.PhotoImage(im) for im in images]
        if state == "idle":
            self.root.iconphoto(True, self._frames["idle"][0])

    def _current_state(self):
        a, v = self._agent, self._voice
        if v and v.listening:
            return "listening"
        if a and a.awaiting:
            return "waiting"
        if time.monotonic() < self._error_until:
            return "error"
        if v and v.speaking:
            return "speaking"
        if a and a.busy:
            return "thinking"
        return "idle"

    def _set_state(self, state):
        self._state = state
        glow = orb.STATES[state][2]
        self.header.itemconfigure(self._state_text, text="●  " + LABELS[state], fill=_hex(glow))
        # A thin line under the header, bright by the orb and fading to the right.
        x = np.arange(1600, dtype=np.float32)
        a = (np.exp(-((x - 60) / 240) ** 2) * 0.9)[None, :, None]
        row = np.array(_rgb(BG), np.float32) * (1 - a) + np.array(glow, np.float32) * a
        self._photos["rule"] = ImageTk.PhotoImage(Image.fromarray(row.astype(np.uint8), "RGB"))
        self.header.itemconfigure(self._rule, image=self._photos["rule"])
        for i, ring in enumerate(self._level_rings):
            self.header.itemconfigure(ring, outline=_hex(_mix(_rgb(BG), glow, 0.35 + 0.3 * i)),
                                      state="normal" if state == "listening" else "hidden")
        self._refresh_hint()

    def _update_controls(self):
        v, b, a = self._voice, self._bridge, self._agent
        lights = {"CHROME": GREEN if b and b.connected else "#39425f",
                  "VOICE": CYAN if v and v.enabled else "#39425f"}
        for name, color in lights.items():
            item = self._lights[name]
            if item[1] != color:
                item[1] = color
                self.header.itemconfigure(item[0], image=self._dot_photo(color))
        self.mic.update_look(active=bool(v and v.listening), disabled=not self._listen)
        self.speaker.update_look(kind="speaker_on" if v and v.enabled else "speaker_off", disabled=not v)
        self.stop.update_look(disabled=not ((a and a.busy) or (v and v.speaking)))

    def _animate(self):
        if self.root.state() in ("iconic", "withdrawn") or not self.root.winfo_viewable():
            self.root.after(400, self._animate)  # nothing to see, so draw nothing
            return
        state = self._current_state()
        if state != self._state:
            self._set_state(state)
        frames = self._frames.get(state) or self._frames.get("idle")
        if frames:
            self._tick = (self._tick + 1) % len(frames)
            self.header.itemconfigure(self._orb_item, image=frames[self._tick])
        if state == "listening" and self._voice:
            self._level = self._level * 0.6 + self._voice.level * 0.4
            cx, cy = self._orb_center
            for i, ring in enumerate(self._level_rings):
                r = 36 + self._level * (14 + 10 * i)
                self.header.coords(ring, cx - r, cy - r, cx + r, cy + r)
        self._update_controls()
        self.root.after(IDLE_MS if state == "idle" else ACTIVE_MS, self._animate)

    def _close(self):
        if self.on_close:
            self.on_close()
        self.root.destroy()

    def run(self):
        self.entry.focus_set()
        self.root.mainloop()
