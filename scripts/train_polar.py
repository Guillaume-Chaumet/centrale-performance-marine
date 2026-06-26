"""
Entraîne un modèle XGBoost par configuration de voilure.

Usage :
    python scripts/train_polar.py data/*.csv
    python scripts/train_polar.py data/*.csv --config gv_genois
"""

import argparse
import glob
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from src.polar_model import PolarModel

REQUIRED_COLS = {"tws_kts", "twa_deg", "heel_deg", "stw_kts"}
ALL_CONFIGS = ["gv_genois", "gv_spi", "1ris_genois", "1ris_spi", "2ris_genois", "2ris_spi"]


def load_csvs(paths: list[str]) -> pd.DataFrame:
    frames = []
    for path in paths:
        df = pd.read_csv(path)
        missing = REQUIRED_COLS - set(df.columns)
        if missing:
            print(f"  WARN {path} : colonnes manquantes {missing}, ignoré")
            continue
        frames.append(df)
        print(f"  {path} : {len(df)} lignes")
    if not frames:
        print("Aucun fichier valide.")
        sys.exit(1)
    return pd.concat(frames, ignore_index=True)


def train_one(df: pd.DataFrame, config_name: str, save: bool = True) -> dict:
    model_path = f"models/polar_{config_name}.pkl"
    model = PolarModel(model_path=model_path)
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as tmp:
        df.to_csv(tmp.name, index=False)
        result = model.train(tmp.name, save=save)
    os.unlink(tmp.name)
    return result, model


def main():
    parser = argparse.ArgumentParser(description="Entraînement polaires XGBoost")
    parser.add_argument("csvs", nargs="+", help="Fichiers CSV de log")
    parser.add_argument("--config", default=None,
                        help="Entraîne uniquement cette config (ex: gv_genois)")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    paths = []
    for pattern in args.csvs:
        expanded = glob.glob(pattern)
        paths.extend(expanded if expanded else [pattern])

    print(f"Chargement de {len(paths)} fichier(s)…")
    df = load_csvs(paths)
    print(f"Total : {len(df)} lignes\n")

    if "sail_config" in df.columns:
        configs = [args.config] if args.config else sorted(df["sail_config"].dropna().unique())
        for cfg in configs:
            sub = df[df["sail_config"] == cfg].reset_index(drop=True)
            print(f"── {cfg} ({len(sub)} lignes)")
            if len(sub) < 100:
                print(f"   Pas assez de données (min 100), ignoré\n")
                continue
            result, model = train_one(sub, cfg, save=not args.no_save)
            print(f"   RMSE={result['rmse_kts']:.3f}kt  n={result['n_samples']}")
            if not args.no_save:
                print(f"   → models/polar_{cfg}.pkl")
            _print_vmg_table(model, cfg)
            print()
    else:
        # Pas de colonne sail_config — comportement ancien (un seul modèle)
        cfg = args.config or "gv_genois"
        print(f"Pas de colonne sail_config — entraînement comme '{cfg}'")
        result, model = train_one(df, cfg, save=not args.no_save)
        print(f"RMSE={result['rmse_kts']:.3f}kt  n={result['n_samples']}")
        if not args.no_save:
            print(f"→ models/polar_{cfg}.pkl")
        _print_vmg_table(model, cfg)


def _print_vmg_table(model: PolarModel, config_name: str):
    print(f"   VMG table [{config_name}] — TWS=12kt, gîte=8° :")
    for twa in [35, 45, 60, 90, 120, 150]:
        stw = model.predict_target_stw(12.0, float(twa), 8.0)
        if stw:
            vmg = stw * math.cos(math.radians(twa))
            print(f"   TWA={twa:3d}°  STW={stw:.2f}kt  VMG={vmg:+.2f}kt")
    opt_up = model.predict_optimal_twa(12.0, 8.0, upwind=True)
    opt_dw = model.predict_optimal_twa(12.0, 8.0, upwind=False)
    print(f"   → Optimaux : près={opt_up:.0f}°  portant={opt_dw:.0f}°")


if __name__ == "__main__":
    main()
