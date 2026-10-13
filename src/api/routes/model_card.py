# ============================================================
# FILE: src/api/routes/model_card.py
# ============================================================
"""Model card for the learner UI: what the served model is, how good it is, and its limits."""
from fastapi import APIRouter, HTTPException

from src.api.routes import cases
from src.ml.inference.predictor import get_predictor

router = APIRouter()

STATIC_LIMITATIONS = [
    "Educational use only: not a medical device and not for patient care.",
    "PTB-XL's MI labels don't distinguish acute from old infarction.",
    "Validated on one dataset (PTB-XL); performance elsewhere is unknown.",
]


def derived_limitations(meta: dict) -> list[str]:
    """Limitations computed from the metrics, so they track the served model."""
    out = []
    auc = meta.get("test_per_class_auc", {})
    if auc:
        weakest = min(auc, key=auc.get)
        out.append(f"Weakest class: {weakest} (test AUC {auc[weakest]:.3f}).")
    groups = meta.get("test_subgroup_auc", {})
    if groups:
        lo, hi = min(groups, key=groups.get), max(groups, key=groups.get)
        out.append(f"Accuracy varies by patient group: {lo.replace('_', ' ')} AUC "
                   f"{groups[lo]:.3f} vs {hi.replace('_', ' ')} {groups[hi]:.3f}.")
    return out


@router.get("/model/card")
async def model_card() -> dict:
    predictor = get_predictor()
    meta = predictor.meta
    if not meta:
        raise HTTPException(status_code=503, detail="No model_meta.json matches the served weights")
    bank = cases._bank
    return {
        "model_version": predictor.model_version,
        "architecture": "1D ResNet-18, 12-lead ECG at 500 Hz, 10 s",
        "classes": meta["classes"],
        "thresholds": meta["thresholds"],
        "evaluation": {
            "split": meta["split"],
            "test_macro_auc": meta["test_macro_auc"],
            "test_per_class_auc": meta["test_per_class_auc"],
            "test_at_threshold": meta["test_at_threshold"],
            "test_ece": meta["test_ece"],
            "test_subgroup_auc": meta["test_subgroup_auc"],
        },
        "lineage": {k: meta.get(k) for k in ("mlflow_run_id", "git_commit", "data_dvc_md5")},
        "case_bank": None if bank is None else {
            k: bank.manifest[k] for k in ("n_cases", "source", "built_at", "selection")
        },
        "limitations": derived_limitations(meta) + STATIC_LIMITATIONS,
    }
