"""
Synchronisation de l'horloge système sur l'heure GPS.

En mer il n'y a ni internet ni RTC garanti : l'horloge du Pi dérive, ce qui
fausse les timestamps de la télémétrie (donc l'entraînement ML des polaires).
On cale l'horloge sur `navigation.datetime` fourni par le GPS via Signal K.

Ne fait rien hors Pi. Nécessite sudo sans mot de passe pour `date` (OpenPlotter).
"""

import subprocess
import time
from datetime import datetime, timezone

import config

CHECK_INTERVAL_S = 30.0   # on ne vérifie pas plus souvent
DRIFT_THRESHOLD_S = 3.0   # recale seulement si l'écart dépasse ce seuil

_last_check = 0.0


def maybe_sync(gps_iso: str | None) -> None:
    global _last_check
    if not config.IS_PI or not gps_iso:
        return
    now = time.monotonic()
    if now - _last_check < CHECK_INTERVAL_S:
        return
    _last_check = now

    try:
        gps_dt = datetime.fromisoformat(gps_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return
    drift = abs((gps_dt - datetime.now(timezone.utc)).total_seconds())
    if drift < DRIFT_THRESHOLD_S:
        return

    stamp = gps_dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        subprocess.run(["sudo", "date", "-u", "-s", stamp],
                       check=False, capture_output=True, timeout=5)
        print(f"[gps-time] horloge recalée sur le GPS (dérive {drift:.0f}s)")
    except Exception:
        pass
