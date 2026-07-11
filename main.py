import argparse
import glob
import math
import os
import signal
import subprocess
import sys
import threading
import time

import config
from src.signalk_client import SignalKClient
from src.imu import IMU
from src.kalman_wind import KalmanWind
from src.data_logger import DataLogger, TelemetryLogger
from src.polar_model import PolarModel
from src.autopilot import Autopilot
from src.barometer import Barometer
from src.gps import GPSBackup
from src.web_ui import UIState, WebUI

LOOP_HZ = 10
LOOP_PERIOD = 1.0 / LOOP_HZ

WIND_ALERT_KN = 25.0        # TWS au-delà duquel l'alerte vent fort se déclenche
DEP_ALERT_HPA_3H = -3.0     # chute de pression / 3h déclenchant l'alerte dépression
PRESSURE_WINDOW_S = 3 * 3600

SAIL_CONFIGS = [
    "gv_genois", "gv_spi",
    "1ris_genois", "1ris_spi",
    "2ris_genois", "2ris_spi",
]


def _load_polar(sail_config: str) -> PolarModel:
    return PolarModel(model_path=f"models/polar_{sail_config}.pkl")


def _retrain_loop():
    """
    Daemon : toutes les 10 min, réentraîne les polaires pour chaque config
    qui a accumulé assez de données CSV. Le fichier pkl est écrit sur disque ;
    la boucle principale recharge le modèle actif via reload_if_updated().
    """
    import pandas as pd
    INTERVAL_S = 600
    RETRAIN_STEP = 50  # réentraîne seulement si +50 points depuis le dernier run

    last_n: dict[str, int] = {cfg: 0 for cfg in SAIL_CONFIGS}

    while True:
        time.sleep(INTERVAL_S)
        for sail_cfg in SAIL_CONFIGS:
            csvs = glob.glob(os.path.join(config.LOG_DIR, f"*_{sail_cfg}.csv"))
            if not csvs:
                continue
            try:
                df = pd.concat(
                    [pd.read_csv(f) for f in csvs],
                    ignore_index=True,
                )
                model = PolarModel(model_path=f"models/polar_{sail_cfg}.pkl")
                valid_n = len(df.dropna(subset=["tws_kts", "twa_deg", "stw_kts"])
                               .query("stw_kts > 1.0 and tws_kts > 2.0"))
                if valid_n < last_n[sail_cfg] + RETRAIN_STEP:
                    continue
                result = model.train_from_df(df)
                last_n[sail_cfg] = result["n_samples"]
                print(
                    f"\n[polar] {sail_cfg} réentraîné — "
                    f"{result['n_samples']} pts  RMSE={result['rmse_kts']:.2f}kt"
                )
            except ValueError:
                pass  # pas assez de données, on attend
            except Exception as e:
                print(f"\n[polar] erreur {sail_cfg}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Centrale de performance marine")
    parser.add_argument("--mode", choices=["log", "coach", "auto"], default="log")
    parser.add_argument("--sail", choices=SAIL_CONFIGS, default="gv_genois",
                        help="Configuration voilure au démarrage")
    args = parser.parse_args()

    env_label = "Pi" if config.IS_PI else "Mac/sim"
    print(f"Démarrage — mode={args.mode}  env={env_label}")

    sk = SignalKClient()
    sk.start()

    imu = IMU()
    baro = Barometer()
    gps_backup = GPSBackup()
    kalman = KalmanWind()
    logger = DataLogger()
    telemetry = TelemetryLogger()

    sail_config: str = args.sail
    polar = _load_polar(sail_config)

    ui_state = UIState(sail_config=sail_config)
    WebUI(ui_state).start()

    rec_started_at: float | None = None

    pressure_history: list[tuple[float, float]] = []  # (timestamp, hPa)
    last_pressure_sample = 0.0

    autopilot = Autopilot()
    autopilot_active = False
    status = "connecté" if autopilot.connected else "port absent — commandes simulées"
    print(f"Autopilot TP22 : {status}")

    polar_status = "ML entraînée" if polar.is_trained else "générique"
    if args.mode in ("coach", "auto"):
        print(f"Polaire : {polar_status} [{sail_config}]")

    threading.Thread(target=_retrain_loop, daemon=True, name="polar-trainer").start()

    print()

    last_telemetry_s = 0.0

    def shutdown(sig, frame):
        print("\nArrêt propre...")
        logger.close()
        telemetry.close()
        autopilot.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    prev_awa = None
    awa_filtered: float | None = None
    autopilot_active = False

    while True:
        t0 = time.monotonic()
        now_wall = time.time()

        imu_data = imu.read()
        roll = imu_data["roll"]
        baro_data = baro.read()
        data = sk.get()

        # ── GPS backup ────────────────────────────────────────────────────────
        gps_source = "signalk"
        if data.lat is None and gps_backup.connected:
            gps = gps_backup.get()
            if gps["lat"] is not None:
                data.lat = gps["lat"]
                data.lon = gps["lon"]
                if data.sog_kts is None:
                    data.sog_kts = gps["sog_kts"]
                if data.cog_deg is None:
                    data.cog_deg = gps["cog_deg"]
                gps_source = "backup"

        # ── Kalman ────────────────────────────────────────────────────────────
        if data.awa_deg is not None:
            if data.awa_deg != prev_awa:
                awa_filtered = kalman.update(data.awa_deg, roll)
                prev_awa = data.awa_deg
            else:
                awa_filtered = kalman.predict_only()

        # ── VMG ───────────────────────────────────────────────────────────────
        vmg: float | None = None
        if data.stw_kts and data.twa_deg:
            vmg = round(data.stw_kts * math.cos(math.radians(data.twa_deg)), 2)

        # ── Rendement ─────────────────────────────────────────────────────────
        rendement: float | None = None
        if args.mode in ("coach", "auto") and polar.is_trained:
            if data.stw_kts and data.tws_kts and data.twa_deg:
                rendement = polar.performance_ratio(
                    data.stw_kts, data.tws_kts, data.twa_deg, data.heel_deg or 0
                )

        # ── Pression historique + alertes ─────────────────────────────────────
        if baro_data["pressure_hpa"] is not None and now_wall - last_pressure_sample >= 60:
            pressure_history.append((now_wall, baro_data["pressure_hpa"]))
            last_pressure_sample = now_wall
            cutoff = now_wall - PRESSURE_WINDOW_S - 600
            pressure_history = [(t, p) for t, p in pressure_history if t > cutoff]

        pressure_trend: float | None = None
        if len(pressure_history) >= 2:
            ref_t = now_wall - PRESSURE_WINDOW_S
            older = [(t, p) for t, p in pressure_history if t <= ref_t]
            if older:
                _, p_old = max(older, key=lambda x: x[0])
                _, p_now = pressure_history[-1]
                pressure_trend = round(p_now - p_old, 1)
            else:
                _, p_old = pressure_history[0]
                _, p_now = pressure_history[-1]
                pressure_trend = round(p_now - p_old, 1)

        wind_alert = data.tws_kts is not None and data.tws_kts > WIND_ALERT_KN
        dep_alert = pressure_trend is not None and pressure_trend < DEP_ALERT_HPA_3H

        # ── AIS vessels avec CPA ──────────────────────────────────────────────
        raw_vessels = sk.get_vessels()
        ais_vessels: list[dict] = []
        for v in raw_vessels:
            vlat, vlon = v.get("lat"), v.get("lon")
            if vlat is None or vlon is None:
                continue
            dist = _distance_nm(data.lat, data.lon, vlat, vlon) if data.lat else None
            bearing = _bearing(data.lat, data.lon, vlat, vlon) if data.lat else None
            cpa = None
            if (data.lat and data.cog_deg is not None and data.sog_kts is not None
                    and v.get("cog") is not None and v.get("sog") is not None):
                cpa = _cpa_nm(data.lat, data.lon, data.cog_deg, data.sog_kts,
                              vlat, vlon, v["cog"], v["sog"])
            ais_vessels.append({
                "mmsi":     v.get("mmsi"),
                "name":     v.get("name"),
                "type":     v.get("type"),
                "length":   v.get("length"),
                "bearing":  round(bearing) if bearing is not None else None,
                "distance": round(dist, 1) if dist is not None else None,
                "cpa":      cpa,
                "sog":      v.get("sog"),
                "cog":      v.get("cog"),
            })
        ais_vessels.sort(key=lambda v: (v["cpa"] if v["cpa"] is not None else 999))

        # ── Durée enregistrement ──────────────────────────────────────────────
        rec_duration = (now_wall - rec_started_at) if rec_started_at else None

        # ── Commandes UI ──────────────────────────────────────────────────────
        for cmd in ui_state.pop_cmds():
            ctype = cmd.get("type")

            if ctype == "sail_config":
                new_cfg = cmd.get("value", "")
                if new_cfg in SAIL_CONFIGS and new_cfg != sail_config:
                    sail_config = new_cfg
                    polar = _load_polar(sail_config)
                    ui_state.update(sail_config=sail_config)
                    print(f"\r[voilure] → {sail_config}   ")

            elif ctype == "autopilot":
                val = cmd.get("value")
                if val == "engage":
                    autopilot_active = True
                    print("\r[pilote] engagé   ")
                elif val == "disengage":
                    autopilot_active = False
                    print("\r[pilote] dégagé — MiniPlex rebascule dans 10s   ")

            elif ctype == "shutdown":
                print("\n[shutdown] Arrêt demandé depuis l'UI...")
                logger.close()
                telemetry.close()
                autopilot.close()
                subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
                sys.exit(0)

            elif ctype == "recording":
                val = cmd.get("value")
                if val == "start" and not logger.is_active:
                    logger.start(sail_config)
                    rec_started_at = time.time()
                    print(f"\r[rec] démarré → {logger.path}   ")
                elif val == "stop" and logger.is_active:
                    logger.stop()
                    rec_started_at = None
                    print("\r[rec] arrêté   ")

        # ── Telemetry always-on (1 pt / 10s) ─────────────────────────────────
        if now_wall - last_telemetry_s >= 10.0:
            telemetry.write(data, awa_filtered, vmg, rendement, roll,
                            baro_data["pressure_hpa"], baro_data["temperature_c"],
                            logger.is_active)
            last_telemetry_s = now_wall

        # ── Hot-reload polaire (thread réentraînement écrit sur disque) ───────
        if polar.reload_if_updated():
            print(f"\r[polar] {sail_config} → ML chargée   ")

        # ── Log CSV ───────────────────────────────────────────────────────────
        logger.write(data, awa_filtered, sail_config,
                     gps_source=gps_source,
                     pressure_hpa=baro_data["pressure_hpa"],
                     temperature_c=baro_data["temperature_c"])

        # ── UI state ──────────────────────────────────────────────────────────
        ui_state.update(
            awa=_r(data.awa_deg),
            awa_filtered=_r(awa_filtered),
            aws=_r(data.aws_kts),
            twa=_r(data.twa_deg),
            tws=_r(data.tws_kts),
            stw=_r(data.stw_kts),
            heel=_r(roll),
            vmg=vmg,
            rendement=_r(rendement, 3),
            pressure_hpa=baro_data["pressure_hpa"],
            temperature_c=baro_data["temperature_c"],
            pressure_trend=pressure_trend,
            gps_source=gps_source,
            is_recording=logger.is_active,
            rec_duration=_r(rec_duration, 0),
            is_fresh=data.is_fresh(),
            autopilot_active=autopilot_active,
            wind_alert=wind_alert,
            dep_alert=dep_alert,
            ais_vessels=ais_vessels,
        )

        # ── Affichage terminal ────────────────────────────────────────────────
        if args.mode in ("coach", "auto"):
            _print_status(data, awa_filtered, polar, sail_config, vmg, rendement)

        # ── Autopilot TP22 ────────────────────────────────────────────────────
        if autopilot_active and data.aws_kts:
            if not data.is_fresh():
                print("\r[WARN] données périmées — TP22 en attente   ", end="", flush=True)
            else:
                awa_to_send = _compute_target_awa(polar, data, awa_filtered)
                if awa_to_send is not None:
                    sentence = autopilot.send_wind(awa_to_send, data.aws_kts)
                    if sentence and not autopilot.connected:
                        print(f"\r[sim] {sentence.strip()}", end="")

        elapsed = time.monotonic() - t0
        sleep = LOOP_PERIOD - elapsed
        if sleep > 0:
            time.sleep(sleep)


def _r(val, decimals: int = 2):
    return round(val, decimals) if val is not None else None


def _bearing(own_lat, own_lon, tgt_lat, tgt_lon) -> float | None:
    if None in (own_lat, own_lon, tgt_lat, tgt_lon):
        return None
    mid = math.radians((own_lat + tgt_lat) / 2)
    dlat = tgt_lat - own_lat
    dlon = (tgt_lon - own_lon) * math.cos(mid)
    return math.degrees(math.atan2(dlon, dlat)) % 360


def _distance_nm(own_lat, own_lon, tgt_lat, tgt_lon) -> float | None:
    if None in (own_lat, own_lon, tgt_lat, tgt_lon):
        return None
    mid = math.radians((own_lat + tgt_lat) / 2)
    dlat = (tgt_lat - own_lat) * 60
    dlon = (tgt_lon - own_lon) * 60 * math.cos(mid)
    return math.sqrt(dlat ** 2 + dlon ** 2)


def _cpa_nm(own_lat, own_lon, own_cog, own_sog,
            tgt_lat, tgt_lon, tgt_cog, tgt_sog) -> float | None:
    if None in (own_lat, own_lon, own_cog, own_sog, tgt_lat, tgt_lon, tgt_cog, tgt_sog):
        return None
    mid = math.radians((own_lat + tgt_lat) / 2)
    rx = (tgt_lon - own_lon) * 60 * math.cos(mid)
    ry = (tgt_lat - own_lat) * 60
    own_vx = own_sog * math.sin(math.radians(own_cog))
    own_vy = own_sog * math.cos(math.radians(own_cog))
    tgt_vx = tgt_sog * math.sin(math.radians(tgt_cog))
    tgt_vy = tgt_sog * math.cos(math.radians(tgt_cog))
    dvx, dvy = tgt_vx - own_vx, tgt_vy - own_vy
    dv2 = dvx ** 2 + dvy ** 2
    dist = math.sqrt(rx ** 2 + ry ** 2)
    if dv2 < 1e-6:
        return round(dist, 2)
    tcpa = -(rx * dvx + ry * dvy) / dv2
    if tcpa < 0:
        return round(dist, 2)
    return round(math.sqrt((rx + dvx * tcpa) ** 2 + (ry + dvy * tcpa) ** 2), 2)


def _compute_target_awa(polar: PolarModel, data, awa_filtered: float | None) -> float | None:
    if awa_filtered is None:
        return None
    if not data.tws_kts or not data.stw_kts:
        return awa_filtered

    upwind = abs(data.awa_deg or awa_filtered) < 90
    optimal_twa = polar.predict_optimal_twa(data.tws_kts, data.heel_deg or 0, upwind=upwind)

    twa_rad = math.radians(optimal_twa)
    tws = data.tws_kts
    stw = data.stw_kts
    side = math.copysign(1.0, data.awa_deg or awa_filtered)
    vx = tws * math.cos(twa_rad) + stw
    vy = tws * math.sin(twa_rad) * side
    return math.degrees(math.atan2(vy, vx))


def _print_status(data, awa_filtered, polar: PolarModel, sail_config: str, vmg, rendement):
    parts = []
    if awa_filtered is not None:
        parts.append(f"AWA_f={awa_filtered:+.1f}°")
    if data.aws_kts:
        parts.append(f"AWS={data.aws_kts:.1f}kt")
    if data.stw_kts:
        parts.append(f"STW={data.stw_kts:.1f}kt")
    if vmg is not None:
        parts.append(f"VMG={vmg:+.2f}kt")
    if data.tws_kts:
        upwind = abs(data.awa_deg or 90) < 90
        opt = polar.predict_optimal_twa(data.tws_kts, data.heel_deg or 0, upwind=upwind)
        label = "ML" if polar.is_trained else "~"
        parts.append(f"TWA_opt={opt:.0f}°[{label}]")
    if rendement is not None:
        parts.append(f"rend={rendement*100:.0f}%")
    parts.append(f"[{sail_config}]")
    print("\r" + "  ".join(parts) + "   ", end="", flush=True)


if __name__ == "__main__":
    main()
