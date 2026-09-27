"""Screen recording through OBS Studio, for demos.

Adam controls OBS through its built-in WebSocket server (Tools > WebSocket Server
Settings), using the password OBS stores in its own settings. Recordings capture
the whole screen in a scene called 'Adam Demo', with desktop sound and microphone.
"""
import json
import logging
import subprocess
import time
from pathlib import Path

SCENE = "Adam Demo"
SCREEN_INPUT = "Adam Demo Screen"
STARTUP_WAIT = 60  # seconds for OBS to open
SETTLE = 8  # OBS answers before it has finished loading; asking too early can freeze it
FLATPAK_ID = "com.obsproject.Studio"
logging.getLogger("obsws_python").setLevel(logging.CRITICAL)  # "refused" is expected while OBS opens
CONFIG_DIRS = [Path.home() / ".var/app" / FLATPAK_ID / "config/obs-studio",
               Path.home() / ".config/obs-studio"]


def _settings():
    for d in CONFIG_DIRS:
        f = d / "plugin_config/obs-websocket/config.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    raise RuntimeError("OBS Studio isn't set up on this computer.")


def _connect():
    import obsws_python as obs
    s = _settings()
    if not s.get("server_enabled"):
        raise RuntimeError("OBS remote control is off. In OBS, open Tools > WebSocket Server "
                           "Settings and tick Enable WebSocket server.")
    cl = obs.ReqClient(host="localhost", port=s.get("server_port", 4455),
                       password=s.get("server_password", "") if s.get("auth_required") else "", timeout=15)
    cl.get_version()  # fails until OBS has finished loading
    return cl


def _launch():
    """Open OBS in the tray (so its window stays out of the recording) and wait for it."""
    flatpak = (Path.home() / ".local/share/flatpak/app" / FLATPAK_ID).exists() or \
        Path("/var/lib/flatpak/app", FLATPAK_ID).exists()
    cmd = ["flatpak", "run", FLATPAK_ID] if flatpak else ["obs"]
    subprocess.Popen(cmd + ["--minimize-to-tray", "--disable-shutdown-check"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.time() + STARTUP_WAIT
    while time.time() < deadline:
        time.sleep(1)
        try:
            cl = _connect()
            time.sleep(SETTLE)
            return cl
        except RuntimeError:
            raise
        except Exception:  # refused or timed out while OBS is still loading
            continue
    raise RuntimeError("OBS didn't open in time. Open OBS yourself and ask again.")


def _client():
    try:
        return _connect()
    except (ConnectionError, OSError):
        return _launch()


def _prepare(cl):
    """Make sure the 'Adam Demo' scene exists, shows the whole screen, and is live."""
    scenes = [s["sceneName"] for s in cl.get_scene_list().scenes]
    if SCENE not in scenes:
        cl.create_scene(SCENE)
    inputs = [i["inputName"] for i in cl.get_input_list().inputs]
    if SCREEN_INPUT not in inputs:
        kinds = cl.get_input_kind_list(False).input_kinds
        kind = next((k for k in ("xshm_input_v2", "xshm_input") if k in kinds), None)
        if not kind:
            raise RuntimeError("This OBS can't capture the screen on this desktop.")
        cl.create_input(SCENE, SCREEN_INPUT, kind, {"screen": 0, "show_cursor": True}, True)
    cl.set_current_program_scene(SCENE)


def start_recording():
    cl = _client()
    if cl.get_record_status().output_active:
        return "Already recording."
    _prepare(cl)
    cl.start_record()
    return "Recording the screen now."


def stop_recording():
    try:
        cl = _connect()
    except (ConnectionError, OSError):
        return "Nothing is being recorded (OBS isn't open)."
    if not cl.get_record_status().output_active:
        return "Nothing is being recorded."
    path = cl.stop_record().output_path
    for _ in range(20):  # wait for OBS to finish writing the file
        if not cl.get_record_status().output_active:
            break
        time.sleep(0.5)
    return f"Recording saved: {path}"
