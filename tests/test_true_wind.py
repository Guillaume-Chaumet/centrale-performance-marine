"""Tests du vent réel /fond/ (src.true_wind.vent_reel).

Exécutable sous pytest OU en standalone :  python tests/test_true_wind.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.true_wind import vent_reel


def _close(a, b, tol=0.15):
    return abs(a - b) <= tol


# ── Cas trivial : bateau immobile → vent réel = vent apparent ─────────────
def test_immobile_vent_reel_egale_apparent():
    Vwf, Dwf = vent_reel(Cv=0, Gwa=0, Vwa=10, Rf=0, Vf=0)
    assert _close(Vwf, 10.0)          # même vitesse
    assert _close(Dwf, 0.0)           # vent de face à quai → vient du cap (000)


def test_immobile_cap_90_vent_de_face():
    Vwf, Dwf = vent_reel(Cv=90, Gwa=0, Vwa=8, Rf=0, Vf=0)
    assert _close(Vwf, 8.0)
    assert _close(Dwf, 90.0)          # vent de face → vient du cap


def test_immobile_rf_none_ne_plante_pas():
    # À l'arrêt le GPS peut ne pas donner de cap : Rf=None doit passer si Vf=0.
    res = vent_reel(Cv=0, Gwa=45, Vwa=5, Rf=None, Vf=0)
    assert res is not None
    Vwf, Dwf = res
    assert _close(Vwf, 5.0)
    assert _close(Dwf, 45.0)


# ── Cas en marche, résultats vérifiables à la main ───────────────────────
def test_vent_de_face_en_marche():
    # Cap N, route N 5 kt, apparent de face 15 kt → vrai 10 kt venant du N.
    Vwf, Dwf = vent_reel(Cv=0, Gwa=0, Vwa=15, Rf=0, Vf=5)
    assert _close(Vwf, 10.0)
    assert _close(Dwf, 0.0)


def test_vent_de_travers_tribord():
    # Cap N, route N 6 kt, apparent au travers tribord (Gwa=90) 12 kt.
    Vwf, Dwf = vent_reel(Cv=0, Gwa=90, Vwa=12, Rf=0, Vf=6)
    assert _close(Vwf, math.hypot(12, 6))   # 13.42 kt
    assert _close(Dwf, 116.6, 0.4)          # vent réel plus en arrière du travers


def test_direction_from_pas_toward():
    # Vérifie qu'on retourne bien la direction D'OÙ vient le vent (pas vers où).
    Vwf, Dwf = vent_reel(Cv=180, Gwa=0, Vwa=10, Rf=180, Vf=0)
    assert _close(Dwf, 180.0)               # cap sud, vent de face → vient du sud


# ── Valeurs manquantes / invalides ───────────────────────────────────────
def test_valeurs_manquantes_retournent_none():
    assert vent_reel(None, 0, 10, 0, 5) is None      # pas de cap
    assert vent_reel(0, None, 10, 0, 5) is None      # pas d'angle apparent
    assert vent_reel(0, 0, None, 0, 5) is None       # pas de vitesse apparente
    assert vent_reel(0, 0, 10, 0, None) is None      # pas de fix GPS (Vf)
    assert vent_reel(0, 0, 10, None, 5) is None      # Vf>0 mais pas de Rf
    assert vent_reel(0, 0, -1, 0, 5) is None         # Vwa négatif


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            ok += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{ok}/{len(tests)} tests OK")
    sys.exit(0 if ok == len(tests) else 1)
