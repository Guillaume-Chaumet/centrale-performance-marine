# CLAUDE.md — Centrale de Performance Marine DIY

## Projet
Boîte noire embarquée sur Raspberry Pi 5 connectée au réseau NMEA 0183 d'un voilier.  
Trois objectifs : polaires réelles (ML), filtrage inertiel du vent (Kalman), optimisation VMG pilote automatique Simrad TP22.

## Environnements
- **Dev** : macOS (cet ordi). Pas de hardware. Simulateur NMEA → Signal K → notre code.
- **Prod** : Raspberry Pi 5 sous OpenPlotter. MiniPlex-3USB → Signal K → notre code.

`config.py` détecte automatiquement l'environnement via `platform.machine()`. Ne jamais hardcoder de chemins de ports série — tout passe par `config.py` ou variables d'env.

## Architecture
```
MiniPlex USB (prod) / Simulateur TCP (dev)
        ↓ NMEA 0183
    Signal K :3000
        ↓ WebSocket ws://localhost:3000/signalk/v1/stream
    src/signalk_client.py  ←─── src/imu.py (BNO055 I2C @ 10Hz)
        │  └── parse AIS vessels (context vessels.*)
        ↓ InstrumentData + get_vessels()
    src/kalman_wind.py     (filtre de Kalman AWA)
        ↓ AWA filtrée
    src/data_logger.py     (CSV → data/)
    src/polar_model.py     (XGBoost — entraînement + inférence)
    src/autopilot.py       (MWV → serial → MiniPlex Out1 → TP22)
    src/barometer.py       (BMP280 I2C — pression + temp, stub Mac)
    src/gps.py             (GPS backup USB GNSS, thread daemon)
    src/web_ui.py          (HTTP :8080 + WebSocket :8081 → webapp/)
    webapp/index.html      (UI tablet/mobile, thème jour/nuit, AIS)
```

## Points critiques matériel

### MiniPlex-3USB
- **In4 est lié à Out1 speed** — GX2200 (38400 bauds) sur In1, jamais sur In4
- **Out1 en mode Override** — quand le Pi envoie des MWV, ils ont priorité exclusive sur Out1. Si le Pi s'arrête, le MiniPlex rebascule automatiquement vers les instruments bruts après 10 secondes.
- La table de routage n'a pas besoin de gérer TP22 — Override s'en charge.

### Simrad TP22
- Actuellement en **mode compas seul** (pas de câble NMEA branché).
- Câble à tirer pour le jalon 3 : Out1-A MiniPlex → Signal/Rouge TP22, Out1-B → Commun/Bleu TP22.
- En mode Conservateur d'Allure, il suit l'angle de vent apparent reçu via `MWV` ou `VWR`.
- **Un seul émetteur autorisé** vers le TP22 — géré par Override, ne pas router d'autres sources vers Out1.

### IMU BNO055
- Connecté en I2C sur le Pi (adresse 0x28). Orienter X→étrave, Y→bâbord/tribord, Z→zénith.
- Sur Mac : stub sinusoïdal réaliste dans `src/imu.py` (roulis ±8° à 0.2 Hz).
- La correction Kalman utilise l'angle de roulis : `Δ_AWA ≈ roll * sin(AWA)`.
- Le roulis IMU est affiché comme gîte dans l'UI (champ `heel`).

### Baromètre BMP280
- I2C adresse 0x76 (SDO→GND) ou 0x77 (SDO→VCC), configurable via `BARO_I2C_ADDRESS`.
- Sur Mac : stub sinusoïdal (1013 ± 3 hPa). Compensation BMP280 datasheet exacte sur Pi.
- L'historique de pression (1 sample/minute, 3h) déclenche l'alerte dépression si Δp < −3 hPa/3h.

### GPS backup (Neo-M9N USB)
- Port `/dev/ttyUSB1` (Pi), configurable via `GPS_PORT`. Baud par défaut : 9600.
- Thread daemon `src/gps.py` — parse `$GPRMC`/`$GNRMC`, actif seulement si Signal K n'a pas de fix GPS.

### Connexion Pi 5 ↔ MiniPlex-3USB
- Câble USB-A (Pi hôte) → USB-B (MiniPlex appareil). Pi 5 a 4 ports USB-A.

## Commandes utiles

```bash
# Dev — lancer le simulateur NMEA (dans un terminal)
python simulator/nmea_sim.py --wind 15 --twa 45 --stw 6

# Dev — lancer le programme principal (mode logging seul)
python main.py --mode log

# Dev — tester la sortie TP22 (ports série virtuels)
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# puis : export TP22_PORT=/dev/pts/X

# Pi — setup initial (une seule fois)
bash scripts/setup_pi.sh

# Pi — démarrer tout
bash scripts/start.sh
```

## Modes de main.py
- `--mode log` : jalon 1 — enregistre les données en CSV, rien d'autre
- `--mode coach` : jalon 2 — log + affiche rendement polaire en temps réel
- `--mode auto` : jalon 3 — log + coach + contrôle TP22 via MWV filtré

## Structure des fichiers
```
config.py               détection env, ports série, adresses I2C, GPS
main.py                 boucle principale, argparse --mode, CPA AIS, alertes

src/
  signalk_client.py     WebSocket Signal K — InstrumentData + AIS vessels
  imu.py                BNO055 réel (Pi) ou stub sinusoïdal (Mac)
  kalman_wind.py        filtre de Kalman 1D sur AWA + correction roulis
  data_logger.py        CSV logging (data/YYYY-MM-DD_HHhMM.csv)
  polar_model.py        entraînement XGBoost + inférence target STW (fallback polaire .pol)
  polar_table.py        parse .pol (qtVlm) + interpolation bilinéaire — polaire d'amorçage
  autopilot.py          forge MWV + envoi série vers TP22
  nmea_utils.py         build_sentence, checksum, build_mwv
  barometer.py          BMP280 I2C — pression/temp (stub sinusoïdal Mac)
  gps.py                GPS backup USB GNSS — thread daemon, parse RMC
  web_ui.py             HTTP :8080 (index.html) + WebSocket :8081 (données live)

webapp/
  index.html            UI responsive : tablet 1040px + mobile — thème jour/nuit,
                        compass AWA, AIS radar+table, alertes vent/dépression

simulator/
  nmea_sim.py           génère RMC, VHW, MWV, AIS → TCP

scripts/
  setup_pi.sh           install deps Pi, active I2C, droits série
  start.sh              démarre Signal K + main.py sur le Pi

polars/                 polaires de référence .pol (Muscadet.pol — amorçage)
data/                   CSV logs (gitignorés)
models/                 modèles XGBoost sérialisés (gitignorés)
```

## Variables d'environnement utiles (dev)
```bash
BARO_I2C_ADDRESS=0x77   # si SDO→VCC (défaut : 0x76)
GPS_PORT=/dev/ttyUSB1   # port GPS backup
GPS_BAUD=9600           # baud GPS (défaut usine Neo-M9N)
TP22_PORT=/dev/pts/3    # port série virtuel (socat) pour tester TP22
SIGNALK_HOST=localhost
SIGNALK_WS_PORT=3000
```

## UIState — champs WebSocket (ws://10.10.10.1:8081)
Tous les champs envoyés par le serveur vers le browser :
`awa`, `awa_filtered`, `aws`, `twa`, `tws`, `stw`, `sog`, `cog`, `heel`, `vmg`, `rendement`,
`polar_curve` (liste [twa, stw] 0-180°, fond du radar), `polar_source` (`ml`|`base`|`none`),
`pressure_hpa`, `temperature_c`, `heading`, `drift`, `twd`, `wind_shift`, `pressure_trend`,
`gps_source`, `gps_sats`, `gps_hdop`, `gps_quality`,
`sail_config`, `is_recording`, `rec_duration`, `is_fresh`, `autopilot_active`,
`wind_alert`, `dep_alert`, `ais_vessels` (liste de dicts : mmsi, name, type, length, bearing, distance, cpa, tcpa, sog, cog)

## Ce qu'on ne fait pas
- Pas de connexion internet en mer — tout est offline
- Pas de dashboard custom côté serveur — on utilise Signal K Instrument Panel existant
- Pas de NMEA 2000 — on reste sur NMEA 0183 pur
- Le Pi ne lit pas directement le port USB du MiniPlex — Signal K s'en charge, on lit via WebSocket

## Ce qu'on fait
- Poser des questions s'il y a un doute

## Jalons
1. **Intégration + data logging** — Signal K tourne, données remontent, CSV généré
2. **Modèle polaires** — collecte données en mer, entraînement XGBoost, dashboard rendement
3. **Kalman + TP22** — filtre actif, câble TP22 branché, mode `auto` validé en mer
