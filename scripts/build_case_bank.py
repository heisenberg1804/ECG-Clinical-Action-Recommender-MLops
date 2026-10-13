#!/usr/bin/env python3
# ============================================================
# FILE: scripts/build_case_bank.py
# ============================================================
"""
Build the case bank for the served champion (models/best_model.pth).

Re-run after every promotion: the API refuses a bank whose model_version
doesn't match the weights it serves.

Usage:
    uv run python scripts/build_case_bank.py            # or: make case-bank
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.casebank.build import build_case_bank  # noqa: E402

DEFAULT_DATA = "data/ptb-xl/ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.3"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--data-dir", default=DEFAULT_DATA)
    p.add_argument("--model", default="models/best_model.pth")
    p.add_argument("--out", default="models/case_bank")
    p.add_argument("--per-class", type=int, default=60)
    p.add_argument("--error-share", type=float, default=0.25)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--device", default=None)
    a = p.parse_args()

    m = build_case_bank(
        data_dir=PROJECT_ROOT / a.data_dir,
        model_path=PROJECT_ROOT / a.model,
        out_dir=PROJECT_ROOT / a.out,
        cache_dir=PROJECT_ROOT / "data" / "cache",
        per_class=a.per_class,
        error_share=a.error_share,
        seed=a.seed,
        device=a.device,
    )
    sel = m["selection"]
    print(f"Built {sel['per_class']} x {len(m['classes'])} cases for {m['model_version']} "
          f"({sel['model_errors_in_bank']} model errors) -> {a.out}")


if __name__ == "__main__":
    main()
