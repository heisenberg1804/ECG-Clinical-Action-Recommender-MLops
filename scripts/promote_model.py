#!/usr/bin/env python3
# ============================================================
# FILE: scripts/promote_model.py
# ============================================================
"""
Promote the MLflow "challenger" to "champion" if it passes the release gates,
then export its serving artifacts to models/ for the API image.

Gates:
  1. Performance: test macro AUC >= champion's + --min-delta (or no champion yet)
  2. Fairness:    max - min subgroup AUC (sex, age bands) <= --max-subgroup-gap

Usage:
    uv run python scripts/promote_model.py               # evaluate gates, promote, export
    uv run python scripts/promote_model.py --dry-run     # report only
    uv run python scripts/promote_model.py --export-only # re-export current champion
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBGROUP_PREFIX = "test_auc_sex_", "test_auc_age_"
# What the API's predictor can load. Serving changes once, at the end of the
# experiment program (D-51); until then a ResNet-34 can't be promoted
SERVABLE_ARCHS = {"resnet18"}


def alias_run(client: MlflowClient, model_name: str, alias: str):
    """Return (model_version, run) for an alias, or (None, None) if unset."""
    try:
        mv = client.get_model_version_by_alias(model_name, alias)
    except MlflowException:
        return None, None
    return mv, client.get_run(mv.run_id)


def subgroup_gap(metrics: dict[str, float]) -> float:
    vals = [v for k, v in metrics.items() if k.startswith(SUBGROUP_PREFIX)]
    return max(vals) - min(vals) if vals else 0.0


def export(client: MlflowClient, run_id: str, dest: Path) -> None:
    """Copy the run's exact serving artifacts (weights + meta) into models/."""
    local = Path(client.download_artifacts(run_id, "serving"))
    for name in ("best_model.pth", "model_meta.json"):
        shutil.copy2(local / name, dest / name)
    print(f"Exported run {run_id} -> {dest}/best_model.pth, model_meta.json")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model-name", default="ecg-resnet1d")
    p.add_argument("--min-delta", type=float, default=0.0)
    p.add_argument("--max-subgroup-gap", type=float, default=0.05)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--export-only", action="store_true")
    p.add_argument("--dest", type=Path, default=PROJECT_ROOT / "models")
    a = p.parse_args()

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT}/mlflow.db"))
    client = MlflowClient()

    if a.export_only:
        mv, run = alias_run(client, a.model_name, "champion")
        if mv is None:
            print("No champion to export")
            return 1
        export(client, run.info.run_id, a.dest)
        return 0

    chal_mv, chal = alias_run(client, a.model_name, "challenger")
    if chal_mv is None:
        print("No challenger registered; run scripts/train.py first")
        return 1
    champ_mv, champ = alias_run(client, a.model_name, "champion")

    chal_auc = chal.data.metrics["test_macro_auc"]
    gap = subgroup_gap(chal.data.metrics)
    champ_auc = champ.data.metrics["test_macro_auc"] if champ else None

    print(f"Challenger v{chal_mv.version}: test macro AUC {chal_auc:.4f}, subgroup gap {gap:.4f}")
    print("Champion:   " + (f"v{champ_mv.version}: {champ_auc:.4f}" if champ else "none"))

    arch = chal.data.params.get("arch", "resnet18")  # Older runs predate the param
    checks = {
        "performance": champ is None or chal_auc >= champ_auc + a.min_delta,
        "fairness": gap <= a.max_subgroup_gap,
        "servable": arch in SERVABLE_ARCHS,
    }
    for name, ok in checks.items():
        print(f"  {name:<12} {'PASS' if ok else 'FAIL'}")

    if not all(checks.values()):
        print("Not promoted.")
        return 1
    if a.dry_run:
        print("Dry run: would promote.")
        return 0

    client.set_registered_model_alias(a.model_name, "champion", chal_mv.version)
    client.delete_registered_model_alias(a.model_name, "challenger")
    print(f"Promoted v{chal_mv.version} to champion.")
    export(client, chal.info.run_id, a.dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
