"""
Vérifie et guide la calibration du BNO055.
À lancer sur le Pi avant la première utilisation en mer.

Usage :
    python scripts/calibrate_imu.py
"""

import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

if not config.IS_PI:
    print("Ce script ne tourne que sur le Pi (BNO055 requis).")
    sys.exit(0)

import smbus2

ADDR = config.IMU_I2C_ADDRESS
REG_CALIB_STAT = 0x35
REG_OPR_MODE   = 0x3D
MODE_NDOF      = 0x0C
MODE_CONFIG    = 0x00


def read_calib(bus):
    stat = bus.read_byte_data(ADDR, REG_CALIB_STAT)
    sys_cal  = (stat >> 6) & 0x03
    gyr_cal  = (stat >> 4) & 0x03
    acc_cal  = (stat >> 2) & 0x03
    mag_cal  = (stat >> 0) & 0x03
    return sys_cal, gyr_cal, acc_cal, mag_cal


def bar(val):
    return "█" * val + "░" * (3 - val)


bus = smbus2.SMBus(1)

print("=== Calibration BNO055 ===")
print()
print("Instructions :")
print("  Gyro  : poser le capteur immobile 2-3 secondes")
print("  Accel : le tenir dans 6 positions différentes (~45°)")
print("  Mag   : tracer des 8 dans l'air lentement")
print()
print("Barre de progression : ░=0  ▓=1  ██=2  ███=3 (3=calibré)")
print()

try:
    while True:
        sys_c, gyr_c, acc_c, mag_c = read_calib(bus)
        line = (
            f"\r  SYS {bar(sys_c)}  "
            f"GYR {bar(gyr_c)}  "
            f"ACC {bar(acc_c)}  "
            f"MAG {bar(mag_c)}   "
        )
        print(line, end="", flush=True)

        if sys_c == 3 and gyr_c == 3 and acc_c == 3 and mag_c == 3:
            print("\n\nCalibration complète ! Vous pouvez lancer main.py.")
            break

        time.sleep(0.5)

except KeyboardInterrupt:
    sys_c, gyr_c, acc_c, mag_c = read_calib(bus)
    print(f"\n\nÉtat final — SYS:{sys_c} GYR:{gyr_c} ACC:{acc_c} MAG:{mag_c}")
    if sys_c >= 1 and gyr_c == 3:
        print("Calibration suffisante pour naviguer (MAG non critique pour le roulis).")
    else:
        print("Calibration incomplète — les corrections Kalman seront moins précises.")
