# ============================================================
# FILE: src/casebank/build.py
# ============================================================
"""
Build the case bank (D-54): a stratified set of test-fold ECGs with the
champion model's predictions and per-class explanations precomputed.

Only test fold 10 is used, so the model is never shown a case it trained on.
Each class contributes the same number of cases, and a fixed share of each is
deliberately drawn from cases the model gets wrong: those are the most useful
for teaching, and they keep the tool honest about the model's limits.
"""
import ast
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy.signal import resample_poly

from src.casebank.store import write_bank
from src.ml.explainability.explainer import HEATMAP_RATE, LEAD_NAMES, ECGExplainer
from src.ml.inference.predictor import ClinicalActionPredictor
from src.ml.preprocessing.signal import TARGET_FS, prepare_ecg
from src.ml.training.data import SUPERCLASSES, build_signal_cache, load_metadata, split_by_fold
from src.ml.training.train import lineage_tags

DISPLAY_FS = 250  # Hz; plenty for display, half the size of the model's 500 Hz
QUALITY_COLUMNS = ["baseline_drift", "static_noise", "burst_noise", "electrodes_problems",
                   "extra_beats", "pacemaker"]


def superclass_likelihoods(scp_codes: str, code_to_class: dict[str, str]) -> dict[str, float]:
    """Highest cardiologist likelihood (0-100) per diagnostic superclass."""
    out: dict[str, float] = {}
    for code, likelihood in ast.literal_eval(scp_codes).items():
        cls = code_to_class.get(code)
        if cls:
            out[cls] = max(out.get(cls, 0.0), float(likelihood))
    return out


def primary_class(likelihoods: dict[str, float]) -> str:
    """The superclass with the highest likelihood; ties go to the earlier class."""
    return max(SUPERCLASSES, key=lambda c: (likelihoods.get(c, -1.0), -SUPERCLASSES.index(c)))


def select_cases(
    primary: np.ndarray,
    correct: np.ndarray,
    per_class: int,
    error_share: float,
    seed: int,
) -> np.ndarray:
    """
    Stratified, deterministic selection of record indices.

    For each class, take `per_class` records whose primary class is that class,
    of which round(per_class * error_share) are model errors (or all available
    errors, if fewer). The result is shuffled so classes are interleaved.
    """
    rng = np.random.default_rng(seed)
    chosen = []
    for cls in SUPERCLASSES:
        idx = np.flatnonzero(primary == cls)
        wrong, right = idx[~correct[idx]], idx[correct[idx]]
        # Round half up explicitly: Python's round() is banker's rounding (round(0.5) == 0)
        n_wrong = min(len(wrong), int(per_class * error_share + 0.5))
        n_right = min(len(right), per_class - n_wrong)
        chosen.append(rng.choice(wrong, n_wrong, replace=False))
        chosen.append(rng.choice(right, n_right, replace=False))
    picked = np.concatenate(chosen)
    rng.shuffle(picked)
    return picked


def display_age(age: float) -> str | None:
    if pd.isna(age):
        return None
    return ">89" if age > 89 else str(int(age))  # PTB-XL encodes ages over 89 as 300


def build_case_bank(
    data_dir: Path,
    model_path: Path,
    out_dir: Path,
    cache_dir: Path,
    per_class: int = 60,
    error_share: float = 0.25,
    seed: int = 0,
    device: str | None = None,
) -> dict:
    lineage = lineage_tags()  # Captured once, at start (same rule as training, D-14)
    predictor = ClinicalActionPredictor(model_path=model_path, device=device)
    model, dev = predictor.model.eval(), predictor.device
    thresholds = np.array([predictor.thresholds[c] for c in SUPERCLASSES])

    df = load_metadata(data_dir)
    test = split_by_fold(df)["test"]
    cache = build_signal_cache(df, data_dir, cache_dir)
    signals = np.load(cache / "signals_500hz_f16.npy", mmap_mode="r")
    row_of = {int(e): i for i, e in enumerate(df.index)}
    raw = np.stack([signals[row_of[int(e)]].astype(np.float32) for e in test.index])

    # ---------------- Score the whole test fold ----------------
    probs = []
    with torch.no_grad():
        for start in range(0, len(raw), 64):
            batch = np.stack([prepare_ecg(s, TARGET_FS) for s in raw[start:start + 64]])
            probs.append(torch.sigmoid(model(torch.from_numpy(batch).to(dev))).cpu().numpy())
    probs = np.concatenate(probs)

    scp = pd.read_csv(data_dir / "scp_statements.csv", index_col=0)
    code_to_class = scp[scp.diagnostic == 1].diagnostic_class.to_dict()
    likelihoods = [superclass_likelihoods(c, code_to_class) for c in test.scp_codes]
    primary = np.array([primary_class(lk) for lk in likelihoods])
    predicted = probs > thresholds
    correct = np.array([predicted[i, SUPERCLASSES.index(p)] for i, p in enumerate(primary)])

    picked = select_cases(primary, correct, per_class, error_share, seed)

    # ---------------- Precompute everything for the picked cases ----------------
    explainer = ECGExplainer(model)
    n_classes, factor = len(SUPERCLASSES), TARGET_FS // HEATMAP_RATE
    n_heat = raw.shape[-1] // factor
    lead_imp = np.zeros((len(picked), n_classes, 12), np.float32)
    temporal = np.zeros((len(picked), n_classes, n_heat), np.float32)
    heatmap = np.zeros((len(picked), n_classes, 12, n_heat), np.float32)
    display = np.zeros((len(picked), 12, raw.shape[-1] * DISPLAY_FS // TARGET_FS), np.float32)
    cases = []

    for k, i in enumerate(picked):
        rec = test.iloc[i]
        tensor = predictor.preprocess_signal(raw[i]).to(dev)
        per_class_text = {}
        for c_idx, cls in enumerate(SUPERCLASSES):
            ex = explainer.explain_prediction(tensor, c_idx, cls)
            lead_imp[k, c_idx] = [ex["lead_importance_scores"][lead] for lead in LEAD_NAMES]
            temporal[k, c_idx] = ex["temporal_attention"]
            heatmap[k, c_idx] = ex["heatmap"]
            per_class_text[cls] = {"important_leads": ex["important_leads"],
                                   "important_segments": ex["important_segments"],
                                   "description": ex["description"]}
        display[k] = resample_poly(raw[i], DISPLAY_FS, TARGET_FS, axis=1)

        # e.g. {"baseline_drift": "V1", "pacemaker": "ja, pacemaker"}: raw PTB-XL detail
        quality = {col: rec[col].strip(" ,") for col in QUALITY_COLUMNS
                   if col in rec and isinstance(rec[col], str) and rec[col].strip(" ,")}
        cases.append({
            "case_id": f"case-{k + 1:03d}",
            "age": display_age(rec.age),
            "sex": "M" if rec.sex == 0 else "F",
            # Below here is answer material: the API withholds it until the student commits
            "ptbxl_ecg_id": int(test.index[i]),
            "labels": rec.superclasses,
            "primary_label": str(primary[i]),
            "label_likelihoods": likelihoods[i],
            "scp_codes": ast.literal_eval(rec.scp_codes),
            # Original cardiologist report, mostly German (e.g. "sinusrhythmus normales ekg")
            "report": rec.get("report") if isinstance(rec.get("report"), str) else None,
            "quality_flags": quality,
            "model": {
                "probabilities": {c: round(float(p), 4) for c, p in zip(SUPERCLASSES, probs[i])},
                "predicted": [c for c, hit in zip(SUPERCLASSES, predicted[i]) if hit],
                "primary_correct": bool(correct[i]),
                "explanations": per_class_text,
            },
        })

    manifest = {
        "model_version": predictor.model_version,
        "thresholds": predictor.thresholds,
        "classes": SUPERCLASSES,
        "lead_names": LEAD_NAMES,
        "display_fs": DISPLAY_FS,
        "heatmap_fs": HEATMAP_RATE,
        "source": "PTB-XL 1.0.3, strat_fold 10 (test) only",
        "selection": {
            "per_class_requested": per_class, "error_share": error_share, "seed": seed,
            "test_fold_size": len(test),
            # Actual counts: a class can fall short (few test records have HYP as primary label)
            "per_class": {c: int((primary[picked] == c).sum()) for c in SUPERCLASSES},
            "model_errors_per_class": {
                c: int(((primary[picked] == c) & ~correct[picked]).sum()) for c in SUPERCLASSES
            },
            "model_errors_in_bank": int((~correct[picked]).sum()),
        },
        "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "git_commit": lineage["git_commit"],
        "data_dvc_md5": lineage["data_dvc_md5"],
    }
    write_bank(out_dir, manifest, cases, display, lead_imp, temporal, heatmap)
    return {**manifest, "n_cases": len(cases)}  # Same as the manifest written to disk
