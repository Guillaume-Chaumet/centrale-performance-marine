"""
Simulateur NMEA — injecte des phrases réalistes dans Signal K via TCP.

Usage :
    python simulator/nmea_sim.py
    python simulator/nmea_sim.py --host localhost --port 10110 --wind 15 --twa 45
"""

import argparse
import math
import socket
import time

CHECKSUM = lambda s: format(
    __import__("functools").reduce(lambda a, b: a ^ b, (ord(c) for c in s)), "02X"
)

def sentence(s: str) -> str:
    return f"${s}*{CHECKSUM(s)}\r\n"


class NMEASimulator:
    def __init__(self, tws: float = 12.0, twa: float = 50.0, stw: float = 5.5):
        self.tws = tws      # True Wind Speed (nœuds)
        self.twa = twa      # True Wind Angle (degrés)
        self.stw = stw      # Speed Through Water (nœuds)
        self.t = 0.0
        self.lat = 43.2965
        self.lon = 5.3698

    def _add_noise(self, val: float, sigma: float) -> float:
        import random
        return val + random.gauss(0, sigma)

    def _mast_motion_offset(self) -> float:
        """Simule l'oscillation de la girouette due au roulis."""
        roll = 8.0 * math.sin(2 * math.pi * 0.2 * self.t)
        return roll * 0.6  # offset apparent wind angle en degrés

    def generate(self) -> list[str]:
        self.t += 1.0
        sentences = []

        # RMC — position GPS
        lat_d = int(self.lat)
        lat_m = (self.lat - lat_d) * 60
        lon_d = int(self.lon)
        lon_m = (self.lon - lon_d) * 60
        rmc = (f"GPRMC,{int(time.time()) % 86400 * 100:06.2f},"
               f"A,{lat_d:02d}{lat_m:07.4f},N,"
               f"{lon_d:03d}{lon_m:07.4f},E,"
               f"{self.stw:.1f},045.0,,,,A")
        sentences.append(sentence(rmc))

        # VHW — vitesse surface (loch)
        stw_noise = self._add_noise(self.stw, 0.05)
        sentences.append(sentence(f"VWVHW,,,,,{stw_noise:.1f},N,,M"))

        # MWV — vent apparent (avec bruit + oscillation mât)
        aws = math.sqrt(
            (self.tws * math.cos(math.radians(self.twa)) + self.stw) ** 2
            + (self.tws * math.sin(math.radians(self.twa))) ** 2
        )
        awa = math.degrees(math.atan2(
            self.tws * math.sin(math.radians(self.twa)),
            self.tws * math.cos(math.radians(self.twa)) + self.stw,
        ))
        awa_with_motion = self._add_noise(awa + self._mast_motion_offset(), 1.5)
        aws_noise = self._add_noise(aws, 0.3)
        sentences.append(sentence(f"WIMWV,{awa_with_motion:.1f},R,{aws_noise:.1f},N,A"))

        # MWV — vent vrai
        tws_noise = self._add_noise(self.tws, 0.2)
        twa_noise = self._add_noise(self.twa, 1.0)
        sentences.append(sentence(f"WIMWV,{twa_noise:.1f},T,{tws_noise:.1f},N,A"))

        # AIS — cible fictive
        sentences.append(sentence("AIVDM,1,1,,A,15M67N0000G?Jp6E`FepT@000000,0"))

        return sentences


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=10110)
    parser.add_argument("--wind", type=float, default=12.0, help="TWS (nœuds)")
    parser.add_argument("--twa", type=float, default=50.0, help="TWA (degrés)")
    parser.add_argument("--stw", type=float, default=5.5, help="STW (nœuds)")
    args = parser.parse_args()

    sim = NMEASimulator(tws=args.wind, twa=args.twa, stw=args.stw)

    print(f"Simulateur NMEA → {args.host}:{args.port}  (TWS={args.wind}kt TWA={args.twa}° STW={args.stw}kt)")

    while True:
        try:
            with socket.create_connection((args.host, args.port), timeout=5) as sock:
                print("Connecté à Signal K")
                while True:
                    for s in sim.generate():
                        sock.sendall(s.encode())
                    time.sleep(1.0)
        except (ConnectionRefusedError, OSError) as e:
            print(f"Signal K non disponible ({e}), retry dans 5s...")
            time.sleep(5.0)


if __name__ == "__main__":
    main()
