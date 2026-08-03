import csv
import os
from datetime import datetime

import config
from src.signalk_client import InstrumentData

FIELDS = [
    "timestamp", "sail_config",
    "awa_raw_deg", "awa_filtered_deg", "aws_kts",
    "twa_deg", "tws_kts", "stw_kts", "sog_kts", "cog_deg",
    "heel_deg", "pitch_deg", "lat", "lon", "gps_source",
    "pressure_hpa", "temperature_c",
]


class DataLogger:
    def __init__(self):
        os.makedirs(config.LOG_DIR, exist_ok=True)
        self._file = None
        self._writer = None
        self._path: str | None = None

    @property
    def is_active(self) -> bool:
        return self._file is not None and not self._file.closed

    @property
    def path(self) -> str | None:
        return self._path

    def start(self, sail_config: str = "gv_genois"):
        if self.is_active:
            self._file.close()
        filename = datetime.now().strftime("%Y-%m-%d_%Hh%M") + f"_{sail_config}.csv"
        self._path = os.path.join(config.LOG_DIR, filename)
        self._file = open(self._path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        self._writer.writeheader()
        self._file.flush()

    def write(self, data: InstrumentData, awa_filtered: float | None = None,
              sail_config: str = "", gps_source: str = "",
              pressure_hpa: float | None = None, temperature_c: float | None = None):
        if not self.is_active:
            return
        self._writer.writerow({
            "timestamp": datetime.utcnow().isoformat(),
            "sail_config": sail_config,
            "awa_raw_deg": _fmt(data.awa_deg),
            "awa_filtered_deg": _fmt(awa_filtered),
            "aws_kts": _fmt(data.aws_kts),
            "twa_deg": _fmt(data.twa_deg),
            "tws_kts": _fmt(data.tws_kts),
            "stw_kts": _fmt(data.stw_kts),
            "sog_kts": _fmt(data.sog_kts),
            "cog_deg": _fmt(data.cog_deg),
            "heel_deg": _fmt(data.heel_deg),
            "pitch_deg": _fmt(data.pitch_deg),
            "lat": _fmt(data.lat, 6),
            "lon": _fmt(data.lon, 6),
            "gps_source": gps_source,
            "pressure_hpa": _fmt(pressure_hpa, 1),
            "temperature_c": _fmt(temperature_c, 1),
        })
        self._file.flush()

    def stop(self):
        if self._file and not self._file.closed:
            self._file.close()
        self._file = None
        self._writer = None

    def close(self):
        self.stop()


def _fmt(val, decimals: int = 2) -> str:
    if val is None:
        return ""
    return f"{val:.{decimals}f}"


TELEMETRY_FIELDS = [
    "timestamp", "awa_deg", "aws_kts", "twa_deg", "tws_kts",
    "stw_kts", "sog_kts", "heel_deg", "vmg", "rendement",
    "pressure_hpa", "temperature_c",
    "heading_deg", "drift_deg", "polar_rec",
]


class TelemetryLogger:
    """Enregistre en continu tous les capteurs (1 pt/10s).
    Un fichier par démarrage du programme — une session = un fichier."""

    def __init__(self):
        os.makedirs(config.LOG_DIR, exist_ok=True)
        filename = datetime.utcnow().strftime("%Y-%m-%d_%Hh%M") + "_telemetry.csv"
        self._path = os.path.join(config.LOG_DIR, filename)
        self._file = open(self._path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=TELEMETRY_FIELDS)
        self._writer.writeheader()
        self._file.flush()

    def write(self, data: InstrumentData, awa_filtered: float | None,
              vmg: float | None, rendement: float | None,
              roll: float | None, pressure_hpa: float | None,
              temperature_c: float | None, polar_rec: bool,
              heading: float | None = None, drift: float | None = None):
        self._writer.writerow({
            "timestamp":        datetime.utcnow().isoformat(),
            "awa_deg":          _fmt(awa_filtered),
            "aws_kts":          _fmt(data.aws_kts),
            "twa_deg":          _fmt(data.twa_deg),
            "tws_kts":          _fmt(data.tws_kts),
            "stw_kts":          _fmt(data.stw_kts),
            "sog_kts":          _fmt(data.sog_kts),
            "heel_deg":         _fmt(roll),
            "vmg":              _fmt(vmg),
            "rendement":        _fmt(rendement, 3),
            "pressure_hpa":     _fmt(pressure_hpa, 1),
            "temperature_c":    _fmt(temperature_c, 1),
            "heading_deg":      _fmt(heading, 0),
            "drift_deg":        _fmt(drift, 1),
            "polar_rec":        "1" if polar_rec else "0",
        })
        self._file.flush()

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()
