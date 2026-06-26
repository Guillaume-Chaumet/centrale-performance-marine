"""
Rejoue un log NMEA brut (.nmea ou .txt) à la vitesse réelle vers le mock Signal K.
Utile pour tester avec des données réelles collectées à bord sans être sur le bateau.

Usage :
    # Enregistrer à bord (via socat ou screen) :
    #   socat /dev/ttyACM0,b38400 - > /tmp/log.nmea
    #
    # Rejouer à la maison :
    python simulator/replay.py logs/sortie_2024-06-15.nmea
    python simulator/replay.py logs/sortie.nmea --speed 4   # 4× plus vite
    python simulator/replay.py logs/sortie.nmea --loop      # boucle infinie
"""

import argparse
import socket
import time


def replay(path: str, host: str, port: int, speed: float, loop: bool):
    lines = []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("$"):
                lines.append(line)

    print(f"Replay : {len(lines)} phrases NMEA — vitesse ×{speed}")

    iteration = 0
    while True:
        iteration += 1
        if iteration > 1:
            print(f"Boucle #{iteration}...")

        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                print(f"Connecté à {host}:{port}")
                t_prev = None
                for line in lines:
                    sock.sendall((line + "\r\n").encode())
                    # Pause d'1/speed secondes entre chaque phrase
                    # (on suppose ~1 phrase/seconde comme le simulateur)
                    time.sleep(1.0 / speed)
        except (ConnectionRefusedError, OSError) as e:
            print(f"Connexion perdue ({e}), retry dans 3s...")
            time.sleep(3.0)
            continue

        if not loop:
            break

    print("Replay terminé.")


def main():
    parser = argparse.ArgumentParser(description="Replay log NMEA → Signal K")
    parser.add_argument("file", help="Fichier log NMEA")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=10110)
    parser.add_argument("--speed", type=float, default=1.0, help="Multiplicateur de vitesse")
    parser.add_argument("--loop", action="store_true", help="Reboucler en continu")
    args = parser.parse_args()

    replay(args.file, args.host, args.port, args.speed, args.loop)


if __name__ == "__main__":
    main()
