import threading
import config

if config.IS_PI and config.GPS_PORT:
    import serial

    class GPSBackup:
        def __init__(self):
            self._lat: float | None = None
            self._lon: float | None = None
            self._sog: float | None = None
            self._cog: float | None = None
            self._lock = threading.Lock()
            self.connected = False
            threading.Thread(target=self._run, daemon=True, name="gps-backup").start()

        def _run(self):
            try:
                with serial.Serial(config.GPS_PORT, config.GPS_BAUD, timeout=2) as ser:
                    self.connected = True
                    print(f"GPS backup connecté sur {config.GPS_PORT}")
                    while True:
                        try:
                            line = ser.readline().decode("ascii", errors="ignore").strip()
                        except Exception:
                            continue
                        if line.startswith(("$GNRMC", "$GPRMC")):
                            self._parse_rmc(line)
            except Exception as e:
                print(f"[WARN] GPS backup absent : {e}")
                self.connected = False

        def _parse_rmc(self, sentence: str):
            try:
                parts = sentence.split(",")
                if len(parts) < 10 or parts[2] != "A":
                    return
                lat_r = float(parts[3])
                lat = int(lat_r / 100) + (lat_r % 100) / 60
                if parts[4] == "S":
                    lat = -lat
                lon_r = float(parts[5])
                lon = int(lon_r / 100) + (lon_r % 100) / 60
                if parts[6] == "W":
                    lon = -lon
                sog = float(parts[7]) if parts[7] else None
                cog = float(parts[8]) if parts[8] else None
                with self._lock:
                    self._lat = round(lat, 6)
                    self._lon = round(lon, 6)
                    self._sog = round(sog, 1) if sog is not None else None
                    self._cog = round(cog, 1) if cog is not None else None
            except (ValueError, IndexError):
                pass

        def get(self) -> dict:
            with self._lock:
                return {
                    "lat": self._lat,
                    "lon": self._lon,
                    "sog_kts": self._sog,
                    "cog_deg": self._cog,
                }

else:
    class GPSBackup:
        """Stub inactif — Signal K fournit le GPS en dev et sans module backup."""
        def __init__(self):
            self.connected = False

        def get(self) -> dict:
            return {"lat": None, "lon": None, "sog_kts": None, "cog_deg": None}
