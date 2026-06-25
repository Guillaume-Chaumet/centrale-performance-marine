import os
import platform

# Détection automatique de l'environnement
IS_PI = platform.machine().startswith("aarch") or os.path.exists("/proc/device-tree/model")

# Signal K
SIGNALK_HOST = os.getenv("SIGNALK_HOST", "localhost")
SIGNALK_PORT = int(os.getenv("SIGNALK_PORT", "10110"))

# Port série MiniPlex → Pi (USB)
MINIPLEX_PORT = os.getenv("MINIPLEX_PORT", "/dev/ttyACM0" if IS_PI else None)
MINIPLEX_BAUD = 38400

# Port série Out1 → TP22 (via MiniPlex retour)
TP22_PORT = os.getenv("TP22_PORT", "/dev/ttyUSB0" if IS_PI else None)
TP22_BAUD = 4800

# IMU BNO055 (I2C)
IMU_I2C_ADDRESS = 0x28
IMU_SAMPLE_RATE_HZ = 10

# GPS backup
GPS_PORT = os.getenv("GPS_PORT", "/dev/ttyUSB1" if IS_PI else None)
GPS_BAUD = 115200

# Data logging
LOG_DIR = os.getenv("LOG_DIR", "data")
