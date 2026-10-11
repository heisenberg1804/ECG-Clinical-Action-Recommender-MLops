#!/usr/bin/env python3
# ============================================================
# FILE: scripts/train.py
# ============================================================
"""
Train ResNet-18 1D on PTB-XL (patient-wise strat_fold split) with MLflow tracking.

Usage:
    uv run python scripts/train.py
    uv run python scripts/train.py --loss focal --epochs 40
    uv run python scripts/train.py --limit 256 --epochs 1 --no-register   # smoke test
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ml.training.train import TrainConfig, train  # noqa: E402

DEFAULT_DATA = (
    "data/ptb-xl/ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--patience", type=int, default=5)
    p.add_argument("--loss", choices=["bce", "focal"], default="bce")
    p.add_argument("--num-workers", type=int, default=4)
    p.add_argument("--device", default=None, help="cpu / mps / cuda (auto if omitted)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=None, help="records per split (smoke test)")
    p.add_argument("--experiment", default="ecg-ptbxl")
    p.add_argument("--run-name", default=None)
    p.add_argument("--no-register", action="store_true", help="skip Model Registry")
    a = p.parse_args()

    train(TrainConfig(
        data_dir=Path(a.data_dir),
        epochs=a.epochs,
        batch_size=a.batch_size,
        lr=a.lr,
        patience=a.patience,
        loss=a.loss,
        num_workers=a.num_workers,
        device=a.device,
        seed=a.seed,
        limit=a.limit,
        experiment=a.experiment,
        run_name=a.run_name,
        registered_model=None if a.no_register else "ecg-resnet1d",
    ))


if __name__ == "__main__":
    main()
