"""Config file and AgentSandbox folders. Both are created on first run."""
import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.json"

# C:\AgentSandbox on Windows; ~/AgentSandbox elsewhere so the code can be tested off Windows.
SANDBOX = Path(r"C:\AgentSandbox") if os.name == "nt" else Path.home() / "AgentSandbox"
NOTES_DIR = SANDBOX / "notes"
SCREENSHOTS_DIR = SANDBOX / "screenshots"
LOGS_DIR = SANDBOX / "logs"
LOG_FILE = LOGS_DIR / "adam_log.txt"
MEMORY_FILE = SANDBOX / "memory.md"
VOICES_DIR = SANDBOX / "voices"

# Link to the Adam Bridge Chrome extension (extension/ folder).
EXTENSION_DIR = PROJECT_DIR / "extension"
BRIDGE_PORT = 47615
BRIDGE_TOKEN_FILE = SANDBOX / "bridge_token.txt"

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "deepseek/deepseek-chat",
    "obsidian_vault": "",
    "speak_replies": True,
    "max_tokens": 4096,
    "fallback_models": [],
}


def ensure_sandbox():
    for d in (NOTES_DIR, SCREENSHOTS_DIR, LOGS_DIR, VOICES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    LOG_FILE.touch(exist_ok=True)


def load_config():
    """Return the config dict, creating config.json with empty fields if it doesn't exist."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {**DEFAULT_CONFIG, **data}


def save_setting(key, value):
    """Change one field in config.json, keeping the rest as the user wrote it."""
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    data[key] = value
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
