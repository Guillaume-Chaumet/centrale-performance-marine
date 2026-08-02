"""
Détecteur de bascules de vent.

Suit la direction géographique du vent (TWD) sur une fenêtre glissante et
compare l'orientation instantanée récente à une ligne de base (moyenne
circulaire de la fenêtre). Le décalage signé indique une bascule :
positif = le vent adonne dans le sens horaire (droite), négatif = refuse.

L'interprétation tactique (adonnante/refus) dépend de l'amure ; on expose
la valeur brute signée et l'UI la lit selon le bord.
"""

import math
import time
from collections import deque

WINDOW_S = 600.0      # fenêtre de référence (10 min)
RECENT_S = 30.0       # fenêtre "instantané" récent
MIN_SAMPLES = 8       # minimum d'échantillons avant de renvoyer une valeur
MIN_SPAN_S = 120.0    # il faut au moins 2 min d'historique


def _circular_mean(angles_deg):
    if not angles_deg:
        return None
    s = sum(math.sin(math.radians(a)) for a in angles_deg)
    c = sum(math.cos(math.radians(a)) for a in angles_deg)
    if s == 0 and c == 0:
        return None
    return math.degrees(math.atan2(s, c)) % 360.0


def _signed_diff(a, b):
    """Écart signé a - b ramené dans [-180, 180]."""
    return ((a - b + 180.0) % 360.0) - 180.0


class WindShiftTracker:
    def __init__(self, window_s: float = WINDOW_S):
        self._window_s = window_s
        self._samples: deque[tuple[float, float]] = deque()

    def update(self, twd_deg, now: float | None = None):
        """Ajoute un relevé TWD et renvoie la bascule signée (°) ou None."""
        if twd_deg is None:
            return None
        now = now if now is not None else time.monotonic()
        self._samples.append((now, twd_deg % 360.0))
        cutoff = now - self._window_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        if len(self._samples) < MIN_SAMPLES:
            return None
        span = self._samples[-1][0] - self._samples[0][0]
        if span < MIN_SPAN_S:
            return None

        baseline = _circular_mean([a for _, a in self._samples])
        recent = _circular_mean([a for t, a in self._samples if t >= now - RECENT_S])
        if baseline is None or recent is None:
            return None
        return round(_signed_diff(recent, baseline), 1)
