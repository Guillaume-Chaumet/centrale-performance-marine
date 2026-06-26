"""
Capture les phrases NMEA brutes depuis le MiniPlex et les sauvegarde dans un fichier.
À lancer à bord pendant une sortie pour pouvoir rejouer les données à la maison.

Usage :
    python scripts/log_nmea.py
    python scripts/log_nmea.py --port /dev/ttyACM0 --out logs/sortie_2024-06-15.nmea

Replay ensuite à la maison :
    python simulator/replay.py logs/sortie_2024-06-15.nmea
"""

import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def main():
    parser = argparse.ArgumentParser(description="Capture NMEA brut depuis MiniPlex")
    parser.add_argument("--port", default=config.MINIPLEX_PORT or "/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=config.MINIPLEX_BAUD)
    parser.add_argument("--out", default=None, help="Fichier de sortie (défaut : logs/YYYY-MM-DD_HHhMM.nmea)")
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    out_path = args.out or os.path.join("logs", datetime.now().strftime("%Y-%m-%d_%Hh%M.nmea"))

    import serial
    try:
        ser = serial.Serial(args.port, args.baud, timeout=2)
    except serial.SerialException as e:
        print(f"Impossible d'ouvrir {args.port} : {e}")
        sys.exit(1)

    print(f"Capture NMEA  {args.port} @ {args.baud} bauds")
    print(f"Fichier       {out_path}")
    print("Ctrl+C pour arrêter\n")

    count = 0
    t_start = time.monotonic()

    try:
        with open(out_path, "w") as f:
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if line.startswith("$"):
                    f.write(line + "\n")
                    f.flush()
                    count += 1
                    elapsed = time.monotonic() - t_start
                    print(f"\r{count} phrases — {elapsed:.0f}s", end="", flush=True)
    except KeyboardInterrupt:
        elapsed = time.monotonic() - t_start
        print(f"\n\n{count} phrases capturées en {elapsed:.0f}s → {out_path}")
        ser.close()


if __name__ == "__main__":
    main()
