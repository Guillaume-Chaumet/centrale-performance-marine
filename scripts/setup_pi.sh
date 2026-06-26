#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Setup Centrale de Performance Marine ==="

# Activer I2C
sudo raspi-config nonint do_i2c 0
echo "✓ I2C activé"

# Droits port série
sudo usermod -aG dialout "$USER"
echo "✓ Droits série ajoutés (reconnexion nécessaire)"

# Dépendances système
sudo apt-get update -q
sudo apt-get install -y python3-pip python3-venv socat i2c-tools python3-dev

# Venv Python
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== Setup Python terminé ==="
echo ""
echo "══════════════════════════════════════════════════════"
echo "  ÉTAPES MANUELLES (à faire une seule fois)"
echo "══════════════════════════════════════════════════════"
echo ""
echo "── 1. Droits et matériel ──────────────────────────────"
echo "  Déconnectez-vous et reconnectez-vous (droits série)"
echo "  Testez IMU    : i2cdetect -y 1      → doit afficher 0x28"
echo "  Testez MiniPlex : ls /dev/ttyACM*"
echo ""
echo "── 2. WiFi AP (via OpenPlotter) ───────────────────────"
echo "  Ouvrir OpenPlotter → 'OpenPlotter Network'"
echo "  → Créer un Access Point :"
echo "      SSID     : Centrale_DIY"
echo "      Password  : (au choix)"
echo "      IP du Pi  : 10.10.10.1"
echo "  Une fois actif, l'iPad/téléphone voit 'Centrale_DIY'"
echo ""
echo "── 3. Signal K — source NMEA ──────────────────────────"
echo "  Ouvrir http://localhost:3000 → Server → Connections"
echo "  → Add Connection :"
echo "      Type     : NMEA 0183"
echo "      Device   : /dev/ttyACM0  (MiniPlex USB)"
echo "      Baudrate : 38400"
echo ""
echo "── 4. Signal K — sortie TCP pour Navionics ────────────"
echo "  → Server → Plugin Config → 'Signal K to NMEA 0183'"
echo "  → Activer le plugin"
echo "  → Ajouter une sortie TCP :"
echo "      Port : 10110"
echo "      Sentences à activer : RMC, VHW, MWV, VDM (AIS)"
echo "  Sauvegarder + Redémarrer Signal K"
echo ""
echo "── 5. Navionics (iPad/Android) ────────────────────────"
echo "  → Se connecter au WiFi 'Centrale_DIY'"
echo "  → Navionics → Paramètres → Instruments externes"
echo "      Type     : NMEA (TCP)"
echo "      Adresse  : 10.10.10.1"
echo "      Port     : 10110"
echo "  → GPS, AIS et vent apparaissent sur la carte"
echo ""
echo "── 6. Service systemd (démarrage auto au boot) ─────────"
echo "  sudo cp scripts/centrale.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable centrale"
echo "  sudo systemctl start centrale"
echo "  sudo journalctl -u centrale -f   # voir les logs"
echo ""
echo "── 7. Changer le mode (log / coach / auto) ─────────────"
echo "  Éditer /etc/systemd/system/centrale.service"
echo "  Modifier : ExecStart=...python main.py --mode auto"
echo "  sudo systemctl daemon-reload && sudo systemctl restart centrale"
echo ""
