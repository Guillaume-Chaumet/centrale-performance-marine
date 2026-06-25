# Centrale de Performance Marine — DIY

Boîte noire embarquée sur Raspberry Pi 5 connectée au réseau NMEA 0183 existant.  
Trois objectifs : **polaires réelles par ML**, **filtrage inertiel du vent (Kalman)**, **optimisation VMG du pilote automatique**.

---

## Matériel

### Existant (sur le bateau)
| Équipement | Rôle | Protocole |
|---|---|---|
| Standard Horizon GX2200 | GPS fixe + AIS double canal + VHF | NMEA 0183 @ 38400 bauds |
| Simrad TP22 | Vérin de barre franche (pilote auto) | NMEA 0183 in @ 4800 bauds |
| Loch / Speedomètre | Vitesse surface (STW) | NMEA 0183 @ 4800 bauds |
| MiniPlex-3USB (ShipModul) | Multiplexeur NMEA — gare de triage centrale | USB bidirectionnel vers Pi |

### À acquérir
| Équipement | Rôle | Connexion |
|---|---|---|
| Raspberry Pi 5 (8 GB) | CPU central, serveur Signal K, runtime Python | — |
| Alim DC-DC 12V→5V isolée (ex. Traco TMR) | Alimentation Pi depuis batterie 12V | PWR Pi |
| BNO055 (Adafruit) | IMU 9-DOF — gîte, tangage, cap magnétique | I2C (GPIO Pi) |
| Ublox Neo-M9N USB | GPS backup haute fréquence (10 Hz) | USB Pi |
| NASA Marine NMEA | Girouette-anémomètre tête de mât | NMEA 0183 @ 4800 bauds → MiniPlex In3 |
| Glomex RA106 Inox | Antenne VHF/AIS dédiée | Coaxial RG-8X → GX2200 |
| Col de cygne inox A4 | Passage de pont câbles mât | — |
| Boîtier étanche Pi | Protection table à cartes | — |

**Batteries : LiFePO4 (panneau solaire existant) — consommation Pi ≈ 1A @ 12V.**

---

## Architecture réseau NMEA

```
[Tête de mât]
  NASA anémomètre ──────────────────────────────────────────┐
  Glomex RA106 (antenne) ──→ GX2200 (VHF/AIS/GPS)          │
                                  │ NMEA @ 38400 bauds       │ NMEA @ 4800 bauds
                                  ▼                          ▼
[Table à cartes]         MiniPlex-3USB ←──────── Loch/Speedomètre
                          In1: GX2200 @ 38400       In2: Loch @ 4800
                          In3: NASA   @ 4800         In4: libre (⚠ lié à Out1)
                                  │
                    ┌─────────────┤ USB bidirectionnel
                    ▼             │
              Raspberry Pi 5      │ MWV filtré (Kalman + VMG)
              Signal K            │
              Python ML/Kalman    │
                    └─────────────┘
                          │
                        Out1 @ 4800 bauds
                          │
                    Simrad TP22
```

### Règle critique MiniPlex : In4 ↔ Out1 speed
> La vitesse de In4 est liée à celle de Out1. Ne jamais mettre la GX2200 (38400 bauds) sur In4 sous peine de casser la sortie TP22.

---

## Configuration MiniPlex (MPXConfig3)

### Entrées
| Port | Source | Vitesse |
|---|---|---|
| In1 | GX2200 (GPS + AIS) | 38400 bauds |
| In2 | Loch | 4800 bauds |
| In3 | NASA anémomètre | 4800 bauds |
| In4 | Libre | 4800 bauds (ne pas modifier) |

### Sorties
| Port | Destination | Host Data |
|---|---|---|
| Out1 | Simrad TP22 | **Override** |
| PC (USB) | Raspberry Pi | — |

### Mode Override sur Out1
Quand le Pi envoie des phrases NMEA via USB, elles arrivent **exclusivement** sur Out1 (le TP22).  
Quand le Pi s'arrête, le MiniPlex rebascule automatiquement sur les instruments bruts **après 10 secondes**.  
→ Réversibilité totale sans intervention manuelle.

### Conversions à activer
- `VWR ↔ MWV` : conversion automatique si la NASA envoie du VWR
- `MWV,R → MWV,T` : vent apparent → vent réel via STW (simplifie le code Python)

### Table de routage
| # | Input | Sentence | Out1 | PC | Note |
|---|---|---|---|---|---|
| 1 | In1 | `--RMC` | | ✓ | GPS → Pi |
| 2 | In1 | `--VDM` | | ✓ | AIS → Pi |
| 3 | In2 | `--VHW` | | ✓ | Loch → Pi |
| 4 | In3 | `--MWV` | | ✓ | Vent brut → Pi uniquement |
| 5 | In3 | `--VWR` | | ✓ | Vent brut → Pi uniquement |
| Default | — | — | — | ✓ | Tout le reste vers Pi |

*Out1 est géré par Override, pas par la table de routage.*

---

## Contrôle du pilote automatique TP22

Le TP22 en **mode Conservateur d'Allure** écoute les phrases `MWV` et `VWR` (vent apparent).  
Il verrouille l'angle de vent apparent reçu et maintient cet angle.

**Stratégie du Pi :**
1. Le Pi reçoit le vent brut (NASA) + les accélérations angulaires (IMU BNO055)
2. Le filtre de Kalman corrige le signal vent des oscillations du mât
3. L'algo VMG consulte la polaire réelle et calcule l'angle optimal
4. Le Pi forges une phrase `$WIMWV,<angle>,R,<vitesse>,N,A*<checksum>` et l'envoie via USB
5. Le MiniPlex (Override) route cette phrase vers Out1 → TP22

**Câble à tirer (nouveau) :** Out1-A (borne A) → Signal/Rouge TP22 | Out1-B → Commun/Bleu TP22

---

## Stack logicielle

```
OS        : OpenPlotter (image Pi 5, basée Raspberry Pi OS)
Serveur   : Signal K Server (Node.js)
              └── input TCP NMEA @ localhost:10110 (dev) ou USB MiniPlex (prod)
              └── output WiFi AP "Centrale_DIY" @ 10.10.10.1
              └── port TCP 10110 → Navionics (iPad/Android)

Python    : 3.11+
  pynmea2     — parsing et génération phrases NMEA
  filterpy    — filtre de Kalman (fusion IMU 10Hz + vent 1Hz)
  smbus2      — lecture IMU BNO055 via I2C
  scikit-learn / xgboost — modèle polaires (Random Forest ou XGBoost)
  pandas      — data logging CSV
  pyserial    — envoi MWV vers MiniPlex (port USB)

Outils dev : socat (ports série virtuels pour simuler Out1→TP22 à la maison)
```

---

## Jalons

### Jalon 1 — Intégration physique & data logging
**Objectif :** tout remonte dans Signal K, Navionics fonctionne via WiFi Pi.

- [ ] Flash OpenPlotter sur Pi 5
- [ ] Configurer Signal K : source TCP en dev, source USB MiniPlex en prod
- [ ] Configurer WiFi AP `Centrale_DIY` @ 10.10.10.1
- [ ] Connecter BNO055 sur I2C, valider lecture gîte/tangage
- [ ] Connecter GPS Neo-M9N USB, valider 10 Hz
- [ ] Premier passage bateau : brancher MiniPlex USB, valider remontée GX2200 + Loch + NASA
- [ ] Configurer table routage MiniPlex + Override Out1
- [ ] Valider Navionics : GPS + AIS affichés via Pi
- [ ] Lancer data logging CSV : `TWS, TWA, STW, gîte, timestamp`

### Jalon 2 — Collecte des données & modèle polaires
**Objectif :** polaire réelle du bateau entraînée et opérationnelle.

- [ ] Sorties en mer avec réglages manuels optimaux (données d'entraînement)
- [ ] Script de nettoyage des données (filtrage courant, conditions transitoires)
- [ ] Entraînement Random Forest / XGBoost : features `[TWS, TWA, gîte]` → label `STW`
- [ ] Validation du modèle (RMSE sur jeu de test)
- [ ] Dashboard Signal K : jauge rendement polaire `STW / STW_cible × 100`

### Jalon 3 — Filtre de Kalman & contrôle TP22
**Objectif :** TP22 piloté en VMG optimal via vent filtré.

- [ ] Implémenter filtre de Kalman : fusion BNO055 (10 Hz) + NASA (1 Hz)
- [ ] Tirer câble Out1 MiniPlex → TP22 (2 fils)
- [ ] **Test de fumée :** envoyer `$WIMWV,045.0,R,010.5,N,A*XX` manuellement, vérifier TP22 bascule en mode Conservateur d'Allure
- [ ] Script VMG : calcul angle optimal depuis polaire → forge `MWV` → envoie USB
- [ ] Valider lissage commandes TP22 en mer (réduction corrections intempestives)
- [ ] Dashboard : indicateur VMG + alerte gîte critique

---

## Workflow de développement

### À la maison (tout le dev)
```bash
# Signal K écoute en TCP
# Le simulateur injecte des phrases NMEA réalistes
python simulator/nmea_sim.py --host localhost --port 10110

# Ports série virtuels pour tester la sortie TP22
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# → /dev/pts/X (Pi écrit MWV) et /dev/pts/Y (lecture "TP22")
```

### Sur le bateau (intégration)
1. Basculer Signal K sur source USB MiniPlex
2. Valider remontée données réelles
3. Enregistrer un log NMEA 30 min pour tests de replay à la maison
4. Tests en navigation

---

## Points de vigilance

| # | Risque | Mitigation |
|---|---|---|
| 1 | In4 lié à Out1 speed | GX2200 sur In1, In4 laissé libre |
| 2 | Un seul émetteur vers TP22 | Override MiniPlex — géré nativement |
| 3 | Convergence modèle polaires lente | Varier les conditions de navigation (allures, forces de vent) |
| 4 | Kalman : calibration IMU | Effectuer la calibration BNO055 à bord avant utilisation |
| 5 | TP22 en mode compas si Pi tombe | Override → fallback auto 10s vers données brutes |
