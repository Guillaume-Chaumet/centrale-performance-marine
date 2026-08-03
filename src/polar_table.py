"""Polaire de référence au format .pol (qtVlm / Expedition).

Grille TWA (lignes) × TWS (colonnes) de vitesse bateau. Sert de polaire
d'amorçage tant que le modèle ML n'a pas assez de données, et de fond
pour le radar polaire de l'UI.
"""
from __future__ import annotations

import os
from bisect import bisect_left


class PolarTable:
    def __init__(self, tws_axis: list[float], twa_axis: list[float],
                 speeds: list[list[float]]):
        # speeds[i][j] = vitesse (kn) à twa_axis[i], tws_axis[j]
        self.tws_axis = tws_axis
        self.twa_axis = twa_axis
        self.speeds = speeds

    @classmethod
    def from_file(cls, path: str) -> "PolarTable | None":
        if not path or not os.path.exists(path):
            return None
        rows: list[list[float]] = []
        tws_axis: list[float] = []
        twa_axis: list[float] = []
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                parts = line.replace(",", ".").split()
                # entête : "TWA\TWS" suivi des valeurs de TWS
                if parts[0].upper().startswith("TWA") or "\\" in parts[0]:
                    tws_axis = [float(x) for x in parts[1:]]
                    continue
                try:
                    vals = [float(x) for x in parts]
                except ValueError:
                    continue
                twa_axis.append(vals[0])
                rows.append(vals[1:])
        if not tws_axis or not twa_axis or not rows:
            return None
        return cls(tws_axis, twa_axis, rows)

    @staticmethod
    def _interp_axis(axis: list[float], v: float) -> tuple[int, int, float]:
        """Retourne (i0, i1, alpha) pour interpoler v sur axis croissant."""
        if v <= axis[0]:
            return 0, 0, 0.0
        if v >= axis[-1]:
            n = len(axis) - 1
            return n, n, 0.0
        i1 = bisect_left(axis, v)
        i0 = i1 - 1
        span = axis[i1] - axis[i0]
        alpha = (v - axis[i0]) / span if span > 0 else 0.0
        return i0, i1, alpha

    def speed(self, tws_kts: float, twa_deg: float) -> float:
        """Vitesse bateau interpolée (bilinéaire) pour un TWS/TWA donné."""
        twa = abs(twa_deg)
        ti0, ti1, ta = self._interp_axis(self.twa_axis, twa)
        wi0, wi1, wa = self._interp_axis(self.tws_axis, tws_kts)
        s00 = self.speeds[ti0][wi0]
        s01 = self.speeds[ti0][wi1]
        s10 = self.speeds[ti1][wi0]
        s11 = self.speeds[ti1][wi1]
        s0 = s00 + wa * (s01 - s00)
        s1 = s10 + wa * (s11 - s10)
        return s0 + ta * (s1 - s0)

    def curve(self, tws_kts: float, twa_step: float = 5.0) -> list[tuple[float, float]]:
        """Courbe polaire (twa, vitesse) pour un TWS donné, de 0 à 180°."""
        out: list[tuple[float, float]] = []
        twa = 0.0
        while twa <= 180.0 + 1e-6:
            out.append((twa, round(self.speed(tws_kts, twa), 3)))
            twa += twa_step
        return out

    def optimal_twa(self, tws_kts: float, upwind: bool = True) -> float:
        """TWA optimisant la VMG (près ou portant) sur la table."""
        import math
        best_twa, best_vmg = (45.0 if upwind else 150.0), -1e9
        twa = 25.0 if upwind else 90.0
        end = 90.0 if upwind else 175.0
        while twa <= end:
            spd = self.speed(tws_kts, twa)
            vmg = spd * math.cos(math.radians(twa))
            vmg = vmg if upwind else -vmg
            if vmg > best_vmg:
                best_vmg, best_twa = vmg, twa
            twa += 1.0
        return best_twa
