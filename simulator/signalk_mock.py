"""
Mock Signal K minimal pour tests en simulation (sans Signal K réel).
- Écoute les phrases NMEA en TCP :10110 (nmea_sim.py)
- Sert les deltas Signal K via WebSocket :3000 (signalk_client.py)
"""

import asyncio
import json
import math
from datetime import datetime, timezone

import pynmea2
import websockets

DEG2RAD = math.pi / 180.0
KTS2MS = 0.514444

_ws_clients: set = set()


def nmea_to_values(raw: str) -> list[dict]:
    try:
        msg = pynmea2.parse(raw.strip())
    except Exception:
        return []

    t = msg.sentence_type
    values = []

    if t == "MWV":
        try:
            angle = float(msg.wind_angle)
            speed = float(msg.wind_speed)
            unit = msg.wind_speed_units
            speed_ms = speed * KTS2MS if unit == "N" else speed / 3.6 if unit == "K" else speed
            if msg.reference == "R":
                values += [
                    {"path": "environment.wind.angleApparent", "value": angle * DEG2RAD},
                    {"path": "environment.wind.speedApparent", "value": speed_ms},
                ]
            elif msg.reference == "T":
                values += [
                    {"path": "environment.wind.angleTrueWater", "value": angle * DEG2RAD},
                    {"path": "environment.wind.speedTrue", "value": speed_ms},
                ]
        except Exception:
            pass

    elif t == "RMC" and msg.status == "A":
        try:
            sog = float(msg.spd_over_grnd or 0)
            cog = float(msg.true_course or 0)
            values += [
                {"path": "navigation.position", "value": {"latitude": msg.latitude, "longitude": msg.longitude}},
                {"path": "navigation.speedOverGround", "value": sog * KTS2MS},
                {"path": "navigation.courseOverGroundTrue", "value": cog * DEG2RAD},
            ]
        except Exception:
            pass

    elif t == "VHW":
        try:
            stw = float(msg.water_speed_knots or 0)
            values.append({"path": "navigation.speedThroughWater", "value": stw * KTS2MS})
        except Exception:
            pass

    return values


async def broadcast(values: list[dict]):
    if not _ws_clients or not values:
        return
    delta = {
        "context": "vessels.self",
        "updates": [{
            "source": {"label": "sim"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "values": values,
        }],
    }
    msg = json.dumps(delta)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


async def handle_tcp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    print("[mock-SK] Simulateur connecté")
    buf = b""
    try:
        while True:
            chunk = await reader.read(512)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                raw = line.decode(errors="ignore").strip()
                if raw.startswith("$"):
                    values = nmea_to_values(raw)
                    if values:
                        await broadcast(values)
    except Exception:
        pass
    writer.close()
    print("[mock-SK] Simulateur déconnecté")


async def handle_ws(ws):
    hello = {"name": "mock-signalk", "version": "1.0.0", "self": "vessels.self", "roles": ["master"]}
    await ws.send(json.dumps(hello))
    _ws_clients.add(ws)
    try:
        async for _ in ws:
            pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(ws)


async def main():
    print("=== Mock Signal K ===")
    tcp = await asyncio.start_server(handle_tcp, "localhost", 10110)
    print("[mock-SK] NMEA TCP  :10110")
    async with tcp:
        async with websockets.serve(handle_ws, "localhost", 3000, ping_interval=None):
            print("[mock-SK] WebSocket :3000")
            await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
