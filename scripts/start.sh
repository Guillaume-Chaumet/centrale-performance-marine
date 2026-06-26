#!/bin/bash
set -e

cd "$(dirname "$0")/.."

MODE=${1:-log}
PYTHON="./venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Venv absent — lancez d'abord : bash scripts/setup_pi.sh"
    exit 1
fi

echo "=== Centrale de Performance Marine — mode=$MODE ==="

# Vérifier Signal K
if ! curl -s --max-time 2 http://localhost:3000/signalk > /dev/null 2>&1; then
    echo "Signal K non détecté sur :3000"
    echo "  → Démarrez-le via OpenPlotter"
    echo "  → Ou : sudo systemctl start signalk"
    exit 1
fi
echo "Signal K OK"

# Vérifier MiniPlex
if [ -e /dev/ttyACM0 ]; then
    echo "MiniPlex détecté : /dev/ttyACM0"
else
    echo "WARN : /dev/ttyACM0 absent — vérifiez le câble USB MiniPlex"
fi

exec "$PYTHON" main.py --mode "$MODE"
