import asyncio
import csv
import glob
import json
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import websockets
import config

_HTML = Path(__file__).parent.parent / "webapp" / "index.html"
HTTP_PORT = 8080
WS_PORT = 8081


def _list_sessions() -> bytes:
    files = sorted(glob.glob(os.path.join(config.LOG_DIR, "*_telemetry.csv")), reverse=True)
    sessions = []
    for f in files:
        try:
            with open(f, newline="") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                continue
            sessions.append({
                "file":       os.path.basename(f),
                "start":      rows[0]["timestamp"],
                "end":        rows[-1]["timestamp"],
                "n_points":   len(rows),
                "duration_h": round(len(rows) * 10 / 3600, 1),
                "has_polar":  any(r.get("polar_rec") == "1" for r in rows),
            })
        except Exception:
            pass
    return json.dumps(sessions).encode()


def _build_history_file(filename: str) -> bytes:
    if "/" in filename or "\\" in filename or not filename.endswith("_telemetry.csv"):
        return json.dumps([]).encode()
    path = os.path.join(config.LOG_DIR, filename)
    rows = []
    try:
        with open(path, newline="") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        pass
    if len(rows) > 600:
        step = max(1, len(rows) // 600)
        rows = rows[::step]
    return json.dumps(rows).encode()


class UIState:
    def __init__(self, sail_config: str = "gv_genois"):
        self._lock = threading.Lock()
        self._data: dict = {
            "awa": None,
            "awa_filtered": None,
            "aws": None,
            "twa": None,
            "tws": None,
            "stw": None,
            "sog": None,
            "cog": None,
            "heel": None,
            "vmg": None,
            "rendement": None,
            "pressure_hpa": None,
            "temperature_c": None,
            "temperature_air_c": None,
            "heading": None,
            "drift": None,
            "pressure_trend": None,
            "gps_source": "signalk",
            "sail_config": sail_config,
            "is_recording": False,
            "rec_duration": None,
            "is_fresh": False,
            "autopilot_active": False,
            "wind_alert": False,
            "dep_alert": False,
            "ais_vessels": [],
        }
        self._cmds: list[dict] = []

    def update(self, **kw):
        with self._lock:
            self._data.update(kw)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def push_cmd(self, cmd: dict):
        with self._lock:
            self._cmds.append(cmd)

    def pop_cmds(self) -> list[dict]:
        with self._lock:
            cmds, self._cmds = self._cmds, []
            return cmds


class WebUI:
    def __init__(self, state: UIState):
        self._state = state

    def start(self):
        threading.Thread(target=self._http, daemon=True, name="web-http").start()
        threading.Thread(target=self._ws, daemon=True, name="web-ws").start()
        print(f"UI → http://localhost:{HTTP_PORT}  (Pi : http://10.10.10.1:{HTTP_PORT})")

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _http(self):
        html_path = _HTML

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/api/sessions"):
                    try:
                        body = _list_sessions()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        self.wfile.write(body)
                    except Exception:
                        self.send_error(500)
                elif self.path.startswith("/api/history"):
                    try:
                        params = self.path.split("?")[1] if "?" in self.path else ""
                        if "file=" in params:
                            fname = params.split("file=")[1].split("&")[0]
                            body = _build_history_file(fname)
                        else:
                            body = json.dumps([]).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        self.wfile.write(body)
                    except Exception:
                        self.send_error(500)
                else:
                    try:
                        body = html_path.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                    except Exception:
                        self.send_error(404)

            def log_message(self, *_):
                pass

        HTTPServer(("0.0.0.0", HTTP_PORT), Handler).serve_forever()

    # ── WebSocket ─────────────────────────────────────────────────────────────

    def _ws(self):
        asyncio.run(self._ws_serve())

    async def _ws_serve(self):
        async with websockets.serve(self._ws_handler, "0.0.0.0", WS_PORT):
            await asyncio.Future()

    async def _ws_handler(self, ws):
        push = asyncio.create_task(self._push(ws))
        try:
            async for raw in ws:
                try:
                    self._state.push_cmd(json.loads(raw))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            push.cancel()

    async def _push(self, ws):
        while True:
            try:
                await ws.send(json.dumps(self._state.snapshot()))
            except Exception:
                break
            await asyncio.sleep(1.0)
