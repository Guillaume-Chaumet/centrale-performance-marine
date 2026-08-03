import os
import platform

# Détection automatique de l'environnement
IS_PI = platform.machine().startswith("aarch") or os.path.exists("/proc/device-tree/model")

# Signal K
SIGNALK_HOST = os.getenv("SIGNALK_HOST", "localhost")
SIGNALK_WS_PORT = int(os.getenv("SIGNALK_WS_PORT", "3000"))    # WebSocket API
SIGNALK_NMEA_PORT = int(os.getenv("SIGNALK_NMEA_PORT", "10110"))  # TCP NMEA input (simulateur)

# Port série MiniPlex → Pi (USB) — symlink udev stable, port host à 460800
MINIPLEX_PORT = os.getenv("MINIPLEX_PORT", "/dev/miniplex" if IS_PI else None)
MINIPLEX_BAUD = int(os.getenv("MINIPLEX_BAUD", "460800"))

# Port série Out1 → TP22 (via MiniPlex retour)
TP22_PORT = os.getenv("TP22_PORT", "/dev/ttyUSB0" if IS_PI else None)
TP22_BAUD = 4800

# IMU BNO055 (I2C)
IMU_I2C_ADDRESS = 0x28
IMU_SAMPLE_RATE_HZ = 10

# Cap magnétique IMU → cap vrai (pour le vent réel)
MAGNETIC_DECLINATION_DEG = float(os.getenv("MAGNETIC_DECLINATION_DEG", "3.0"))  # ~+3°E Marseille 2026
HEADING_OFFSET_DEG = float(os.getenv("HEADING_OFFSET_DEG", "0.0"))  # offset montage/résiduel, réglé au cross-check COG

# Baromètre BMP280 (I2C) — SDO→GND = 0x76, SDO→VCC = 0x77
BARO_I2C_ADDRESS = int(os.getenv("BARO_I2C_ADDRESS", "0x76"), 16)

# GPS backup (USB GNSS dongle)
GPS_PORT = os.getenv("GPS_PORT", "/dev/ttyUSB1" if IS_PI else None)
GPS_BAUD = int(os.getenv("GPS_BAUD", "9600"))

# Data logging
LOG_DIR = os.getenv("LOG_DIR", "data")

# Polaire d'amorçage (fallback tant que le modèle ML n'est pas entraîné)
BASE_POLAR_PATH = os.getenv("BASE_POLAR_PATH", os.path.join("polars", "Muscadet.pol"))
