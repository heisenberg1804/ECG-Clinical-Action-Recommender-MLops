# ============================================================
# FILE: src/ml/training/metrics.py
# ============================================================
"""Evaluation metrics for multi-label ECG classification."""
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, roc_auc_score

AGE_BINS = [0, 40, 65, float("inf")]  # PTB-XL encodes ages > 89 as 300
AGE_LABELS = ['lt40', '40to65', 'gt65']


def per_class_auc(y_true: np.ndarray, y_prob: np.ndarray, classes: list[str]) -> dict[str, float]:
    """ROC AUC per class; classes with a single label value are skipped."""
    return {
        c: float(roc_auc_score(y_true[:, i], y_prob[:, i]))
        for i, c in enumerate(classes)
        if len(np.unique(y_true[:, i])) > 1
    }


def macro_auc(y_true: np.ndarray, y_prob: np.ndarray, classes: list[str]) -> float:
    aucs = per_class_auc(y_true, y_prob, classes)
    return float(np.mean(list(aucs.values()))) if aucs else float("nan")


def tune_thresholds(y_true: np.ndarray, y_prob: np.ndarray, classes: list[str]) -> dict[str, float]:
    """Per-class threshold maximizing F1. Tune on validation, never on test."""
    grid = np.linspace(0.05, 0.95, 91)
    return {
        c: round(float(grid[np.argmax([
            f1_score(y_true[:, i], y_prob[:, i] >= t, zero_division=0) for t in grid
        ])]), 2)
        for i, c in enumerate(classes)
    }


def threshold_metrics(
    y_true: np.ndarray, y_prob: np.ndarray, classes: list[str], thresholds: dict[str, float]
) -> dict[str, dict[str, float]]:
    """F1, sensitivity and specificity per class at the given thresholds."""
    out = {}
    for i, c in enumerate(classes):
        pred = y_prob[:, i] >= thresholds[c]
        true = y_true[:, i].astype(bool)
        tp, tn = np.sum(pred & true), np.sum(~pred & ~true)
        fp, fn = np.sum(pred & ~true), np.sum(~pred & true)
        out[c] = {
            'f1': float(f1_score(true, pred, zero_division=0)),
            'sensitivity': float(tp / (tp + fn)) if tp + fn else float("nan"),
            'specificity': float(tn / (tn + fp)) if tn + fp else float("nan"),
        }
    return out


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """ECE for one binary output: weighted |accuracy - confidence| over probability bins."""
    bins = np.minimum((y_prob * n_bins).astype(int), n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        mask = bins == b
        if mask.any():
            ece += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece)


def subgroup_auc(
    y_true: np.ndarray, y_prob: np.ndarray, meta: pd.DataFrame, classes: list[str]
) -> dict[str, float]:
    """
    Macro AUC per demographic subgroup (performance parity against ground truth).

    Unlike demographic parity on predictions, this does not penalize the model
    for real differences in disease prevalence between groups.

    Args:
        meta: Rows aligned with y_true; needs PTB-XL `sex` (0=male, 1=female) and `age`
    """
    groups = {
        'sex_male': (meta.sex == 0).values,
        'sex_female': (meta.sex == 1).values,
    }
    age_group = pd.cut(meta.age, bins=AGE_BINS, labels=AGE_LABELS, right=False)
    for label in AGE_LABELS:
        groups[f'age_{label}'] = (age_group == label).values
    return {
        name: macro_auc(y_true[mask], y_prob[mask], classes)
        for name, mask in groups.items()
        if mask.sum() > 0
    }
