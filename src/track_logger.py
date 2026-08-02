"""
Enregistreur de trace GPX.

Une trace par démarrage du programme. Ajoute un point tous les TRACK_PERIOD_S
quand la position est valide, pour rejouer la nav sur carte et corréler la
performance polaire avec la position / le courant.
"""

import os
import time
from datetime import datetime, timezone

import config

TRACK_PERIOD_S = 10.0

_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="Centrale de Performance Marine" '
    'xmlns="http://www.topografix.com/GPX/1/1">\n'
    '<trk><name>{name}</name><trkseg>\n'
)
_FOOTER = '</trkseg></trk></gpx>\n'


class TrackLogger:
    def __init__(self):
        os.makedirs(config.LOG_DIR, exist_ok=True)
        name = datetime.utcnow().strftime("%Y-%m-%d_%Hh%M")
        self._path = os.path.join(config.LOG_DIR, name + "_track.gpx")
        self._file = open(self._path, "w")
        self._file.write(_HEADER.format(name=name))
        self._file.flush()
        self._last = 0.0

    @property
    def path(self) -> str:
        return self._path

    def maybe_write(self, lat, lon, sog_kts=None, cog_deg=None) -> None:
        if lat is None or lon is None or self._file.closed:
            return
        now = time.monotonic()
        if now - self._last < TRACK_PERIOD_S:
            return
        self._last = now
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        extra = ""
        if sog_kts is not None:
            extra += f"<speed>{sog_kts * 0.514444:.2f}</speed>"  # nœuds -> m/s
        if cog_deg is not None:
            extra += f"<course>{cog_deg:.0f}</course>"
        self._file.write(
            f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"><time>{ts}</time>{extra}</trkpt>\n'
        )
        self._file.flush()

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.write(_FOOTER)
            self._file.close()
