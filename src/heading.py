"""Cap vrai du bateau à partir du cap magnétique de l'IMU (BNO055).

Version légère : cap magnétique fusionné (yaw NDOF, tilt-compensé) + déclinaison
locale + offset de montage. La déviation propre au bateau est supposée
négligeable (coque bois, mât alu non ferromagnétique, moteur hors-bord éloigné) ;
elle est de toute façon absorbée par HEADING_OFFSET_DEG s'il reste un biais
constant, réglé au cross-check contre le COG. Si la déviation variait fortement
avec le cap, il faudrait un swing (courbe A..E) — non nécessaire ici a priori.
"""

import config


def cap_vrai(yaw_mag_deg):
    """Cap vrai (0-359) = cap magnétique IMU + déclinaison + offset montage.

    Retourne None si le cap magnétique est absent.
    """
    if yaw_mag_deg is None:
        return None
    return (yaw_mag_deg
            + config.MAGNETIC_DECLINATION_DEG
            + config.HEADING_OFFSET_DEG) % 360.0
