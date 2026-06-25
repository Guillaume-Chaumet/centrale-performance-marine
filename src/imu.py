import config

if config.IS_PI:
    import smbus2

    class IMU:
        def __init__(self):
            self.bus = smbus2.SMBus(1)
            self.addr = config.IMU_I2C_ADDRESS
            self._init_bno055()

        def _init_bno055(self):
            # Mode NDOF (fusion complète)
            self.bus.write_byte_data(self.addr, 0x3D, 0x0C)

        def read(self) -> dict:
            """Retourne gîte (roll), tangage (pitch), cap (yaw) en degrés."""
            # Registres Euler BNO055 : 0x1A-0x1F
            data = self.bus.read_i2c_block_data(self.addr, 0x1A, 6)
            def to_signed(high, low):
                val = (high << 8) | low
                return val - 65536 if val > 32767 else val
            yaw   = to_signed(data[1], data[0]) / 16.0
            roll  = to_signed(data[3], data[2]) / 16.0
            pitch = to_signed(data[5], data[4]) / 16.0
            return {"roll": roll, "pitch": pitch, "yaw": yaw}

else:
    import math, time

    class IMU:
        """Stub de simulation pour développement Mac."""
        def __init__(self):
            self._t = 0.0

        def read(self) -> dict:
            self._t += 0.1
            # Simule un roulis sinusoïdal de ±8° à 0.2 Hz (houle)
            roll  = 8.0 * math.sin(2 * math.pi * 0.2 * self._t)
            pitch = 3.0 * math.sin(2 * math.pi * 0.15 * self._t + 0.5)
            yaw   = 45.0
            return {"roll": roll, "pitch": pitch, "yaw": yaw}
