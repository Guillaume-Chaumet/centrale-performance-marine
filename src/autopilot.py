import math
import time

import config
from src.nmea_utils import build_mwv

MAX_RATE_DEG_PER_S = 5.0   # changement max d'angle par seconde vers le TP22
MIN_SEND_INTERVAL = 0.5    # pas la peine d'envoyer plus vite que 2 Hz


class Autopilot:
    """Envoie des phrases MWV au TP22 via port série (MiniPlex Override Out1)."""

    def __init__(self):
        self._serial = None
        if config.TP22_PORT:
            import serial
            self._serial = serial.Serial(config.TP22_PORT, config.TP22_BAUD, timeout=1)
        self._current_awa: float | None = None
        self._last_sent: float = 0.0

    def send_wind(self, awa_target: float, aws_kts: float) -> str | None:
        now = time.monotonic()
        if now - self._last_sent < MIN_SEND_INTERVAL:
            return None

        awa_out = self._rate_limit(awa_target, now - self._last_sent)
        self._current_awa = awa_out
        self._last_sent = now

        sentence = build_mwv(awa_out, aws_kts)
        if self._serial and self._serial.is_open:
            self._serial.write(sentence.encode())
        return sentence

    def _rate_limit(self, target: float, dt: float) -> float:
        if self._current_awa is None:
            return target
        max_delta = MAX_RATE_DEG_PER_S * min(dt, 2.0)  # cap à 2s pour éviter les sauts post-pause
        diff = target - self._current_awa
        diff = max(-max_delta, min(max_delta, diff))
        return self._current_awa + diff

    def close(self):
        if self._serial and self._serial.is_open:
            self._serial.close()

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def current_awa(self) -> float | None:
        return self._current_awa
