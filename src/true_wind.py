"""Vent réel /fond/ (géographique) à partir du GPS et du cap vrai.

À ne pas confondre avec le TWA/TWS relatif au bateau (main._true_wind), qui
sert aux polaires/VMG/pilote. Ici on calcule la DIRECTION vraie du vent
(azimut compas d'où il vient, Dwf) et sa vitesse /fond/ (Vwf), indépendantes
du courant et de la dérive.

Convention des angles (degrés, 0-359, sens horaire depuis le Nord vrai) :
- Cv  : cap vrai du bateau (HDT, ou HDG + déclinaison)
- Gwa : gisement du vent apparent par rapport à l'étrave (MWV,R du NASA :
        0 = pile dans l'axe/étrave, 90 = travers tribord). ATTENTION : le
        chemin Signal K angleApparent est signé (-180..180) ; le passer en
        0-359 avant appel (Gwa = awa_deg % 360).
- Vwa : vitesse du vent apparent (même unité que Vf, ex. nœuds)
- Rf  : route fond / COG (navigation.courseOverGroundTrue)
- Vf  : vitesse fond / SOG (navigation.speedOverGround)

Pourquoi la dérive n'intervient pas :
Le vent apparent est mesuré par rapport à l'axe du bateau (donc au cap vrai Cv),
et on le somme avec la vitesse FOND issue du GPS (Rf, Vf), pas avec la vitesse
surface (loch). La route surface Rs = Cv + δ (δ = angle de dérive) et le
courant sont déjà intégrés dans le vecteur fond mesuré par le GPS. En partant
du GPS on obtient donc directement le vent réel /fond/ sans estimer ni δ ni le
courant : ils s'annulent algébriquement. (Si on partait du loch, il faudrait
corriger la dérive et le courant à la main.)
"""

import math
from typing import Optional, Tuple


def vent_reel(Cv, Gwa, Vwa, Rf, Vf) -> Optional[Tuple[float, float]]:
    """Vent réel /fond/ par somme vectorielle vent apparent + vitesse fond.

    Retourne (Vwf, Dwf) :
      - Vwf : vitesse du vent réel (même unité que Vwa/Vf)
      - Dwf : direction D'OÙ vient le vent réel (azimut compas 0-359)
    Retourne None si une entrée nécessaire manque ou est invalide (pas de fix
    GPS, MWV invalide...), suivant le pattern Optional du reste du code.
    """
    # ── Validation (valeurs manquantes / invalides sans planter) ──────────
    if Cv is None or Gwa is None or Vwa is None or Vf is None:
        return None
    if Vwa < 0 or Vf < 0:
        return None
    if Vf > 0 and Rf is None:      # à l'arrêt le GPS ne fournit pas de cap ;
        return None                # mais dès qu'on avance il faut Rf.

    # ── 1. Azimut du vecteur vent apparent ────────────────────────────────
    # Gwa est référencé à l'étrave → azimut = cap + gisement. Le +180 oriente
    # le vecteur dans la direction VERS laquelle le vent apparent souffle.
    Zwa = (Cv + Gwa + 180.0) % 360.0

    # ── 2. Composantes (Est = x, Nord = y) ────────────────────────────────
    zr = math.radians(Zwa)
    wa_x = Vwa * math.sin(zr)
    wa_y = Vwa * math.cos(zr)

    if Vf == 0.0:                  # bateau immobile : vitesse fond nulle
        uf_x = uf_y = 0.0
    else:
        rr = math.radians(Rf)
        uf_x = Vf * math.sin(rr)
        uf_y = Vf * math.cos(rr)

    # ── 3. Somme vectorielle : vent réel = vent apparent + vitesse fond ────
    wf_x = wa_x + uf_x
    wf_y = wa_y + uf_y

    # ── 4. Norme + direction D'OÙ vient le vent (azimut + 180) ────────────
    Vwf = math.hypot(wf_x, wf_y)
    Dwf = (math.degrees(math.atan2(wf_x, wf_y)) + 180.0) % 360.0
    return round(Vwf, 2), round(Dwf, 1)
