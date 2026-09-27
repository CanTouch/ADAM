"""Browser tools that act in the user's own Google Chrome.

Adam runs a small WebSocket server on 127.0.0.1. The Adam Bridge extension (the
extension/ folder, loaded once in Chrome) connects to it and carries out each command
in one tab, grouped and labelled "Adam". Only the extension, holding the token that
Adam writes into extension/config.js, is accepted.
"""
import asyncio
import base64
import itertools
import json
import secrets
import threading
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from websockets.asyncio.server import serve

from config import BRIDGE_PORT, BRIDGE_TOKEN_FILE, EXTENSION_DIR, SCREENSHOTS_DIR

MAX_TEXT_CHARS = 15000
CONNECT_WAIT = 15   # seconds to wait for Chrome to connect before giving up
CALL_TIMEOUT = 45

def _token():
    """Load (or create) the shared secret and make sure the extension has it."""
    if BRIDGE_TOKEN_FILE.exists():
        token = BRIDGE_TOKEN_FILE.read_text().strip()
    else:
        token = secrets.token_hex(16)
        BRIDGE_TOKEN_FILE.write_text(token)
    js = f'const ADAM_PORT = {BRIDGE_PORT};\nconst ADAM_TOKEN = "{token}";\n'
    cfg = EXTENSION_DIR / "config.js"
    if not cfg.exists() or cfg.read_text() != js:
        cfg.write_text(js)
    return token


class Bridge:
    def __init__(self):
        self._loop = None
        self._conn = None
        self._connected = threading.Event()
        self._pending = {}
        self._ids = itertools.count(1)
        self._token = None
        self.error = None

    @property
    def connected(self):
        return self._connected.is_set()

    def start(self):
        self._token = _token()
        ready = threading.Event()
        threading.Thread(target=self._run, args=(ready,), daemon=True).start()
        ready.wait(5)

    def _run(self, ready):
        self._loop = asyncio.new_event_loop()

        async def main():
            async with serve(self._handler, "127.0.0.1", BRIDGE_PORT, max_size=32 * 1024 * 1024):
                ready.set()
                await asyncio.Future()

        try:
            self._loop.run_until_complete(main())
        except OSError as e:
            self.error = f"Could not start the Chrome bridge on port {BRIDGE_PORT} ({e}). Is Adam already running?"
            ready.set()

    async def _handler(self, conn):
        origin = conn.request.headers.get("Origin", "")
        token = parse_qs(urlparse(conn.request.path).query).get("token", [""])[0]
        if not origin.startswith("chrome-extension://") or not secrets.compare_digest(token, self._token):
            await conn.close(1008, "unauthorized")
            return
        self._conn = conn
        self._connected.set()
        try:
            async for raw in conn:
                msg = json.loads(raw)
                fut = self._pending.get(msg.get("id"))
                if fut and not fut.done():
                    fut.set_result(msg)
        finally:
            if self._conn is conn:
                self._conn = None
                self._connected.clear()
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(ConnectionError("Chrome disconnected."))

    async def _send(self, cmd, args, timeout):
        conn = self._conn
        if conn is None:
            raise ConnectionError("Chrome disconnected.")
        i = next(self._ids)
        fut = self._loop.create_future()
        self._pending[i] = fut
        try:
            await conn.send(json.dumps({"id": i, "cmd": cmd, "args": args}))
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(i, None)

    def call(self, cmd, timeout=CALL_TIMEOUT, **args):
        if self.error:
            raise RuntimeError(self.error)
        if not self._connected.wait(CONNECT_WAIT):
            raise RuntimeError("Chrome isn't connected. Open Google Chrome (with the Adam Bridge "
                               "extension turned on) and try again.")
        msg = asyncio.run_coroutine_threadsafe(self._send(cmd, args, timeout), self._loop).result(timeout + 5)
        if not msg.get("ok"):
            raise RuntimeError(msg.get("error", "unknown error"))
        return msg.get("result")


bridge = Bridge()


def open_url(url):
    return bridge.call("open_url", url=url)


def use_current_tab():
    return bridge.call("use_current_tab")


def click(selector):
    return bridge.call("click", selector=selector)


def fill_form(selector, value):
    return bridge.call("fill_form", selector=selector, value=value)


def get_page_text():
    text = bridge.call("get_page_text")
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n... [truncated, page is {len(text):,} chars]"
    return text


def screenshot():
    data_url = bridge.call("screenshot")
    path = SCREENSHOTS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.png"
    path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    return f"Screenshot saved: {path}"
