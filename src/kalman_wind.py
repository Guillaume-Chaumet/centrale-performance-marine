import math
import numpy as np
from filterpy.kalman import KalmanFilter


class KalmanWind:
    """
    Filtre de Kalman 1D sur l'angle de vent apparent (AWA).
    Fusionne mesure vent (~1 Hz) + correction roulis IMU (10 Hz).
    """

    def __init__(self, process_var: float = 0.5, measure_var: float = 8.0):
        kf = KalmanFilter(dim_x=1, dim_z=1)
        kf.x = np.array([[0.0]])
        kf.F = np.array([[1.0]])
        kf.H = np.array([[1.0]])
        kf.P = np.array([[50.0]])
        kf.Q = np.array([[process_var]])
        kf.R = np.array([[measure_var]])
        self._kf = kf
        self._initialized = False

    def update(self, awa_raw: float, roll_deg: float) -> float:
        """Nouvelle mesure vent + correction roulis → AWA filtrée."""
        roll_correction = roll_deg * math.sin(math.radians(abs(awa_raw))) * 0.5
        z = np.array([[awa_raw - roll_correction]])

        if not self._initialized:
            self._kf.x = z.copy()
            self._initialized = True

        self._kf.predict()
        self._kf.update(z)
        return float(self._kf.x[0, 0])

    def predict_only(self) -> float:
        """Tick IMU sans nouvelle mesure vent."""
        self._kf.predict()
        return float(self._kf.x[0, 0])

    @property
    def awa(self) -> float:
        return float(self._kf.x[0, 0])
