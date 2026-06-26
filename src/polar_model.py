import math
import os
import pickle

import numpy as np


MODEL_PATH = os.path.join("models", "polar.pkl")
MIN_TRAIN_SAMPLES = 300

# Plage de recherche TWA pour l'optimisation VMG
_TWA_MIN, _TWA_MAX, _TWA_STEP = 25.0, 170.0, 1.0

# Polaire générique voilier de croisière/régate (~10m).
# TWS (kt) → (TWA_upwind_opt °, TWA_downwind_opt °)
# Sert de fallback avant que le modèle ML soit entraîné.
_GENERIC_POLAR = [
    (0,   50, 170),
    (5,   48, 165),
    (8,   44, 158),
    (12,  42, 152),
    (16,  40, 147),
    (20,  38, 143),
    (25,  37, 140),
    (99,  37, 140),  # borne haute
]


def _generic_optimal_twa(tws_kts: float) -> tuple[float, float]:
    """Interpole TWA upwind/downwind optimal depuis la table générique."""
    tws = max(0.0, tws_kts)
    for i in range(1, len(_GENERIC_POLAR)):
        t0, up0, dw0 = _GENERIC_POLAR[i - 1]
        t1, up1, dw1 = _GENERIC_POLAR[i]
        if tws <= t1:
            alpha = (tws - t0) / (t1 - t0) if t1 > t0 else 0.0
            return up0 + alpha * (up1 - up0), dw0 + alpha * (dw1 - dw0)
    return _GENERIC_POLAR[-1][1], _GENERIC_POLAR[-1][2]


class PolarModel:
    def __init__(self, model_path: str = MODEL_PATH):
        self._model_path = model_path
        self._model = None
        self._last_load_mtime = 0.0
        if os.path.exists(model_path):
            self._load()

    def _load(self):
        with open(self._model_path, "rb") as f:
            self._model = pickle.load(f)
        self._last_load_mtime = os.path.getmtime(self._model_path)

    def reload_if_updated(self) -> bool:
        """Recharge le pkl si le fichier a été mis à jour sur disque."""
        if not os.path.exists(self._model_path):
            return False
        if os.path.getmtime(self._model_path) > self._last_load_mtime:
            self._load()
            return True
        return False

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def predict_target_stw(self, tws_kts: float, twa_deg: float, heel_deg: float) -> float | None:
        """STW cible selon la polaire ML. None si pas encore entraînée."""
        if not self._model:
            return None
        X = np.array([[tws_kts, abs(twa_deg), abs(heel_deg)]])
        return float(self._model.predict(X)[0])

    def predict_optimal_twa(self, tws_kts: float, heel_deg: float, upwind: bool = True) -> float:
        """
        TWA optimal VMG.
        - Si modèle ML entraîné : optimisation numérique sur la polaire réelle.
        - Sinon : table générique (toujours disponible dès le jour 1).
        """
        if self._model:
            if upwind:
                twas = np.arange(_TWA_MIN, 90.0, _TWA_STEP)
            else:
                twas = np.arange(90.0, _TWA_MAX + _TWA_STEP, _TWA_STEP)
            X = np.column_stack([
                np.full(len(twas), tws_kts),
                twas,
                np.full(len(twas), abs(heel_deg)),
            ])
            stws = self._model.predict(X)
            cos_twas = np.cos(np.radians(twas))
            vmgs = stws * cos_twas if upwind else -stws * cos_twas
            return float(twas[np.argmax(vmgs)])

        twa_up, twa_dw = _generic_optimal_twa(tws_kts)
        return twa_up if upwind else twa_dw

    def performance_ratio(self, actual_stw: float, tws_kts: float, twa_deg: float, heel_deg: float) -> float | None:
        """Rendement réel vs polaire ML. None si pas encore entraînée."""
        target = self.predict_target_stw(tws_kts, twa_deg, heel_deg)
        if not target or target <= 0:
            return None
        return actual_stw / target

    def train_from_df(self, df, save: bool = True) -> dict:
        """Entraîne XGBoost sur un DataFrame déjà chargé et filtre les données invalides."""
        from xgboost import XGBRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_squared_error

        df = df.copy()
        df["heel_deg"] = df["heel_deg"].fillna(0.0) if "heel_deg" in df.columns else 0.0
        df = df.dropna(subset=["tws_kts", "twa_deg", "stw_kts"])
        df = df[(df["stw_kts"] > 1.0) & (df["tws_kts"] > 2.0)]

        if len(df) < MIN_TRAIN_SAMPLES:
            raise ValueError(f"Pas assez de données : {len(df)} < {MIN_TRAIN_SAMPLES}")

        X = df[["tws_kts", "twa_deg", "heel_deg"]].abs().values
        y = df["stw_kts"].values

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        self._model = XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.05, n_jobs=-1)
        self._model.fit(X_train, y_train)

        rmse = float(mean_squared_error(y_test, self._model.predict(X_test)) ** 0.5)

        if save:
            os.makedirs(os.path.dirname(self._model_path) or "models", exist_ok=True)
            with open(self._model_path, "wb") as f:
                pickle.dump(self._model, f)
            self._last_load_mtime = os.path.getmtime(self._model_path)

        return {"rmse_kts": rmse, "n_samples": len(df)}

    def train(self, csv_path: str, save: bool = True) -> dict:
        import pandas as pd
        return self.train_from_df(pd.read_csv(csv_path), save=save)
