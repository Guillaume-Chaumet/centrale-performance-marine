import config

_BARO_ADDR = config.BARO_I2C_ADDRESS

if config.IS_PI:
    import smbus2

    class Barometer:
        def __init__(self):
            self._bus = smbus2.SMBus(1)
            self._ok = False
            try:
                chip_id = self._bus.read_byte_data(_BARO_ADDR, 0xD0)
                if chip_id not in (0x56, 0x57, 0x58, 0x60):
                    raise RuntimeError(f"Chip ID inattendu : 0x{chip_id:02X}")
                self._read_calibration()
                # normal mode, osrs_t=x2, osrs_p=x16
                self._bus.write_byte_data(_BARO_ADDR, 0xF4, 0xB7)
                self._ok = True
            except Exception as e:
                print(f"[WARN] Baromètre absent ou erreur I2C : {e}")

        def _read_calibration(self):
            c = self._bus.read_i2c_block_data(_BARO_ADDR, 0x88, 24)
            self._T1 = (c[1] << 8) | c[0]
            self._T2 = _s16((c[3] << 8) | c[2])
            self._T3 = _s16((c[5] << 8) | c[4])
            self._P1 = (c[7] << 8) | c[6]
            self._P2 = _s16((c[9] << 8) | c[8])
            self._P3 = _s16((c[11] << 8) | c[10])
            self._P4 = _s16((c[13] << 8) | c[12])
            self._P5 = _s16((c[15] << 8) | c[14])
            self._P6 = _s16((c[17] << 8) | c[16])
            self._P7 = _s16((c[19] << 8) | c[18])
            self._P8 = _s16((c[21] << 8) | c[20])
            self._P9 = _s16((c[23] << 8) | c[22])

        def read(self) -> dict:
            if not self._ok:
                return {"pressure_hpa": None, "temperature_c": None}
            raw = self._bus.read_i2c_block_data(_BARO_ADDR, 0xF7, 6)
            raw_p = (raw[0] << 12) | (raw[1] << 4) | (raw[2] >> 4)
            raw_t = (raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4)
            temp, press = _compensate(raw_t, raw_p, self._T1, self._T2, self._T3,
                                       self._P1, self._P2, self._P3, self._P4,
                                       self._P5, self._P6, self._P7, self._P8, self._P9)
            return {"pressure_hpa": press, "temperature_c": temp}

else:
    import math, time

    class Barometer:
        """Stub sinusoïdal pour développement Mac."""
        def __init__(self):
            self._t0 = time.monotonic()

        def read(self) -> dict:
            t = time.monotonic() - self._t0
            pressure = 1013.0 + 3.0 * math.sin(2 * math.pi * t / 3600)
            temperature = 18.0 + 2.0 * math.sin(t / 900)
            return {
                "pressure_hpa": round(pressure, 1),
                "temperature_c": round(temperature, 1),
            }


def _s16(val: int) -> int:
    return val - 65536 if val > 32767 else val


def _compensate(raw_t, raw_p, T1, T2, T3, P1, P2, P3, P4, P5, P6, P7, P8, P9):
    var1 = raw_t / 16384.0 - T1 / 1024.0
    var2 = (raw_t / 131072.0 - T1 / 8192.0) ** 2
    t_fine = var1 * T2 + var2 * T3
    temp = round(t_fine / 5120.0, 1)

    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * P6 / 32768.0 + var1 * P5 * 2.0
    var2 = var2 / 4.0 + P4 * 65536.0
    var1 = (P3 * var1 * var1 / 524288.0 + P2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * P1
    if var1 == 0:
        return temp, 0.0
    press = 1048576.0 - raw_p
    press = (press - var2 / 4096.0) * 6250.0 / var1
    var1 = P9 * press * press / 2147483648.0
    var2 = press * P8 / 32768.0
    press = press + (var1 + var2 + P7) / 16.0
    return temp, round(press / 100.0, 1)
