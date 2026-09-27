"""Desktop tools: open apps, open files/folders, list and switch windows.

Apps and windows use Linux desktop tools (gio, wmctrl); open_path also works on Windows.
Only installed desktop apps (.desktop entries) can be launched, never raw commands.
"""
import configparser
import os
import subprocess
import sys
from pathlib import Path

ADAM_TITLE = "Adam"


def _detached(cmd):
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


# ---- apps ----

def _app_dirs():
    data = os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    dirs = [Path.home() / ".local/share"] + [Path(d) for d in data if d]
    dirs += [Path("/var/lib/flatpak/exports/share"), Path.home() / ".local/share/flatpak/exports/share"]
    seen, out = set(), []
    for d in dirs:
        a = d / "applications"
        if a.is_dir() and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _apps():
    """Yield (name, generic_name, path) for every launchable desktop app."""
    seen = set()
    for d in _app_dirs():
        for f in sorted(d.glob("*.desktop")):
            if f.name in seen:
                continue
            seen.add(f.name)
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("Type") != "Application" or e.get("NoDisplay") == "true" or e.get("Hidden") == "true":
                continue
            yield e.get("Name", f.stem), e.get("GenericName", ""), f


def open_app(name):
    if not sys.platform.startswith("linux"):
        return "Error: open_app is only supported on Linux."
    q = name.strip().lower()
    apps = list(_apps())
    tiers = (
        lambda n, g, f: n.lower() == q or f.stem.lower() == q,
        lambda n, g, f: n.lower().startswith(q),
        lambda n, g, f: q in n.lower() or q in g.lower() or q in f.stem.lower(),
    )
    for exact, match in zip((True, False, False), tiers):
        hits = [a for a in apps if match(*a)]
        if len(hits) == 1 or (hits and exact):
            n, _, f = hits[0]
            _detached(["gio", "launch", str(f)])
            return f"Opened {n}."
        if hits:
            names = ", ".join(sorted({h[0] for h in hits})[:15])
            return f"Several apps match '{name}': {names}. Say which one."
    return f"No installed app matches '{name}'."


# ---- files and folders ----

def open_path(path):
    p = Path(os.path.expanduser(str(path).strip().strip('"')))
    if not p.exists():
        return f"Error: not found: {p}"
    if os.name == "nt":
        os.startfile(str(p))
    else:
        _detached(["xdg-open", str(p)])
    return f"Opened {p}"


# ---- windows ----

def _windows():
    """[(id, title)] of normal windows, excluding Adam's own."""
    out = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5).stdout
    wins = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or parts[1] == "-1":
            continue
        if parts[3] != ADAM_TITLE:
            wins.append((parts[0], parts[3]))
    return wins


def _find(window):
    wins = _windows()
    w = window.strip()
    if w.lower().startswith("0x"):
        hits = [x for x in wins if int(x[0], 16) == int(w, 16)]
    else:
        hits = [x for x in wins if x[1].lower() == w.lower()] or \
               [x for x in wins if w.lower() in x[1].lower()]
    if not hits:
        raise ValueError(f"No window matches '{window}'.")
    if len(hits) > 1:
        raise ValueError(f"Several windows match '{window}':\n" +
                         "\n".join(f"{i}  {t}" for i, t in hits) + "\nUse the id.")
    return hits[0]


def _wm(*args):
    if not sys.platform.startswith("linux"):
        raise ValueError("Window tools are only supported on Linux.")
    subprocess.run(["wmctrl", *args], check=True, timeout=5)


def list_windows():
    if not sys.platform.startswith("linux"):
        return "Error: window tools are only supported on Linux."
    wins = _windows()
    return "\n".join(f"{i}  {t}" for i, t in wins) if wins else "No open windows."


def focus_window(window):
    wid, title = _find(window)
    _wm("-i", "-a", wid)
    return f"Brought to front: {title}"


def minimize_window(window):
    wid, title = _find(window)
    from Xlib import X, display, protocol  # Linux only; wmctrl can't minimize on Cinnamon

    d = display.Display()
    try:
        win = d.create_resource_object("window", int(wid, 16))
        event = protocol.event.ClientMessage(
            window=win, client_type=d.intern_atom("WM_CHANGE_STATE"),
            data=(32, [3, 0, 0, 0, 0]),  # 3 = IconicState
        )
        d.screen().root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        d.flush()
    finally:
        d.close()
    return f"Minimized: {title}"


def close_window(window):
    wid, title = _find(window)
    _wm("-i", "-c", wid)
    return f"Asked to close: {title}"
