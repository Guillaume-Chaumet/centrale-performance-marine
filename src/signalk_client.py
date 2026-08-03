"""
Lit les données instruments depuis Signal K via WebSocket.
Tourne dans un thread background — fournit un InstrumentData thread-safe.
Parse aussi les cibles AIS reçues sur le même flux.
"""

import asyncio
import copy
import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

import websockets

import config

RAD2DEG = 180.0 / math.pi
MS2KTS = 1.94384

DATA_MAX_AGE_S = 10.0
_AIS_MAX_AGE_S = 300.0  # cibles non vues depuis 5 min → retirées


@dataclass
class InstrumentData:
    awa_deg: Optional[float] = None   # Angle vent apparent (degrés)
    aws_kts: Optional[float] = None   # Vitesse vent apparent (nœuds)
    twa_deg: Optional[float] = None   # Angle vent réel (degrés)
    tws_kts: Optional[float] = None   # Vitesse vent réel (nœuds)
    stw_kts: Optional[float] = None   # Vitesse sur l'eau — loch (nœuds)
    sog_kts: Optional[float] = None   # Vitesse sur le fond — GPS (nœuds)
    cog_deg: Optional[float] = None   # Cap sur le fond (degrés)
    heel_deg: Optional[float] = None  # Gîte (degrés, positif = tribord)
    pitch_deg: Optional[float] = None
    hdg_true_deg: Optional[float] = None  # Cap vrai (HDT)
    hdg_mag_deg: Optional[float] = None   # Cap magnétique (HDG/HDM)
    mag_var_deg: Optional[float] = None   # Déclinaison magnétique (Est positif)
    lat: Optional[float] = None
    lon: Optional[float] = None
    gps_sats: Optional[int] = None        # nombre de satellites vus
    gps_hdop: Optional[float] = None      # dilution horizontale (précision du fix)
    gps_quality: Optional[str] = None     # qualité du fix (GNSS Fix, DGPS...)
    gps_datetime: Optional[str] = None    # heure GPS ISO 8601 (UTC)
    updated_at: float = 0.0           # time.monotonic() du dernier update reçu

    def is_fresh(self, max_age_s: float = DATA_MAX_AGE_S) -> bool:
        return (time.monotonic() - self.updated_at) < max_age_s


# path Signal K → (attribut InstrumentData, fonction de conversion vers l'unité UI)
_PATHS = {
    "environment.wind.angleApparent":  ("awa_deg",      lambda v: v * RAD2DEG),
    "environment.wind.speedApparent":  ("aws_kts",      lambda v: v * MS2KTS),
    "environment.wind.angleTrueWater": ("twa_deg",      lambda v: v * RAD2DEG),
    "environment.wind.speedTrue":      ("tws_kts",      lambda v: v * MS2KTS),
    "navigation.speedThroughWater":    ("stw_kts",      lambda v: v * MS2KTS),
    "navigation.speedOverGround":      ("sog_kts",      lambda v: v * MS2KTS),
    "navigation.courseOverGroundTrue": ("cog_deg",      lambda v: v * RAD2DEG),
    "navigation.attitude.roll":        ("heel_deg",     lambda v: v * RAD2DEG),
    "navigation.attitude.pitch":       ("pitch_deg",    lambda v: v * RAD2DEG),
    "navigation.headingTrue":          ("hdg_true_deg", lambda v: v * RAD2DEG),
    "navigation.headingMagnetic":      ("hdg_mag_deg",  lambda v: v * RAD2DEG),
    "navigation.magneticVariation":    ("mag_var_deg",  lambda v: v * RAD2DEG),
    "navigation.gnss.satellites":         ("gps_sats",    lambda v: int(v)),
    "navigation.gnss.horizontalDilution": ("gps_hdop",    lambda v: round(v, 2)),
    "navigation.gnss.methodQuality":      ("gps_quality", lambda v: str(v)),
    "navigation.datetime":                ("gps_datetime", lambda v: str(v)),
}

_SUBSCRIBE = {
    "context": "vessels.self",
    "subscribe": (
        [{"path": p, "period": 1000} for p in _PATHS if p != "navigation.attitude.roll"]
        + [{"path": "navigation.attitude.roll", "period": 100}]
        + [{"path": "navigation.position", "period": 1000}]
    ),
}

_AIS_SUBSCRIBE = {
    "context": "vessels.*",
    "subscribe": [
        {"path": "navigation.position",             "period": 5000},
        {"path": "navigation.speedOverGround",      "period": 5000},
        {"path": "navigation.courseOverGroundTrue", "period": 5000},
        {"path": "name",                            "period": 60000},
        {"path": "design.aisShipType",              "period": 60000},
        {"path": "design.length.overall",           "period": 60000},
    ],
}

_AIS_TYPES = {
    30: 'Pêche', 31: 'Remorqueur', 32: 'Remorqueur', 36: 'Voilier',
    37: 'Plaisance', 51: 'SAR', 52: 'Remorqueur',
}


def _ais_type_label(code) -> str | None:
    if code is None:
        return None
    if code in _AIS_TYPES:
        return _AIS_TYPES[code]
    if 60 <= code <= 69:
        return 'Passagers'
    if 70 <= code <= 79:
        return 'Cargo'
    if 80 <= code <= 89:
        return 'Tanker'
    return None


class SignalKClient:
    def __init__(self, host: str = None, port: int = None):
        self._host = host or config.SIGNALK_HOST
        self._port = port or config.SIGNALK_WS_PORT
        self._data = InstrumentData()
        self._lock = threading.Lock()
        self._self_context = "vessels.self"  # remplacé par l'URN réel au message d'accueil
        self._ais: dict[str, dict] = {}
        self._ais_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def get(self) -> InstrumentData:
        with self._lock:
            return copy.copy(self._data)

    def get_vessels(self) -> list[dict]:
        now = time.monotonic()
        with self._ais_lock:
            return [dict(v) for v in self._ais.values()
                    if now - v.get("updated_at", 0) < _AIS_MAX_AGE_S]

    def _run(self):
        asyncio.run(self._listen())

    async def _listen(self):
        url = f"ws://{self._host}:{self._port}/signalk/v1/stream?subscribe=none"
        while True:
            try:
                async with websockets.connect(url) as ws:
                    await ws.send(json.dumps(_SUBSCRIBE))
                    await ws.send(json.dumps(_AIS_SUBSCRIBE))
                    async for msg in ws:
                        self._parse(json.loads(msg))
            except Exception:
                await asyncio.sleep(3.0)

    def _parse(self, msg: dict):
        # Message d'accueil Signal K : porte l'identité "self" (URN du bateau)
        if "self" in msg and "updates" not in msg:
            self._self_context = msg["self"]
            return
        context = msg.get("context", self._self_context)
        if context not in (self._self_context, "vessels.self") and context.startswith("vessels."):
            mmsi = context.split(":")[-1] if ":" in context else context.split(".")[-1]
            self._parse_ais(mmsi, msg)
            return
        for update in msg.get("updates", []):
            for value in update.get("values", []):
                path = value.get("path", "")
                val = value.get("value")
                if val is None:
                    continue
                if path == "navigation.position" and isinstance(val, dict):
                    with self._lock:
                        self._data.lat = val.get("latitude")
                        self._data.lon = val.get("longitude")
                        self._data.updated_at = time.monotonic()
                    continue
                if path in _PATHS:
                    attr, conv = _PATHS[path]
                    with self._lock:
                        setattr(self._data, attr, conv(val))
                        self._data.updated_at = time.monotonic()

    def _parse_ais(self, mmsi: str, msg: dict):
        now = time.monotonic()
        with self._ais_lock:
            v = self._ais.setdefault(mmsi, {"mmsi": mmsi})
            v["updated_at"] = now
            for update in msg.get("updates", []):
                for item in update.get("values", []):
                    path = item.get("path", "")
                    val = item.get("value")
                    if val is None:
                        continue
                    if path == "navigation.position" and isinstance(val, dict):
                        v["lat"] = val.get("latitude")
                        v["lon"] = val.get("longitude")
                    elif path == "navigation.speedOverGround":
                        v["sog"] = round(val * MS2KTS, 1)
                    elif path == "navigation.courseOverGroundTrue":
                        v["cog"] = round(val * RAD2DEG, 0)
                    elif path == "name":
                        v["name"] = str(val)
                    elif path == "design.aisShipType":
                        code = int(val) if isinstance(val, (int, float)) else None
                        v["type"] = _ais_type_label(code)
                    elif path == "design.length.overall":
                        if isinstance(val, dict):
                            v["length"] = round(val.get("overall", 0))
                        elif isinstance(val, (int, float)):
                            v["length"] = round(val)
