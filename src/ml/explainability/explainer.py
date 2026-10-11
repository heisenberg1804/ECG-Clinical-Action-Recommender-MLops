# ============================================================
# FILE: src/ml/explainability/explainer.py
# ============================================================
"""
Explainability module for ECG predictions.

Two complementary attributions are computed from a single backward pass:
- Grad-CAM on the last residual block -> *when* in the 10 s strip the model looked
- Gradient x input on the 12-lead input -> *which leads* drove the decision

Both operate on the exact preprocessed tensor the model scored, and use
torch.autograd.grad rather than module hooks, so explanations are thread-safe
and leave no state behind on the shared model.
"""
import os
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as fn

LEAD_NAMES = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
SAMPLING_RATE = 500  # Hz of the model input
HEATMAP_RATE = 50  # Hz of the heatmaps returned by the API (keeps payloads small)
SMOOTHING_SAMPLES = 51  # ~100 ms window for per-lead saliency
ATTENTION_THRESHOLD = 0.5
MAX_SEGMENTS = 3

DIAGNOSIS_NAMES = {
    'NORM': 'a normal ECG',
    'MI': 'myocardial infarction',
    'STTC': 'ST/T changes',
    'CD': 'a conduction disturbance',
    'HYP': 'hypertrophy',
}


def compute_attributions(
    model: nn.Module,
    signal_tensor: torch.Tensor,
    target_class: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute Grad-CAM (temporal) and gradient x input (per-lead) attributions.

    Args:
        model: ResNet1D exposing forward_features / forward_head
        signal_tensor: Preprocessed model input, shape (1, 12, T)
        target_class: Index of the class to explain

    Returns:
        cam: (T,) temporal importance, normalized to [0, 1]
        saliency: (12, T) per-lead importance, smoothed, normalized to [0, 1]
    """
    model.eval()
    x = signal_tensor.detach().clone().requires_grad_(True)

    with torch.enable_grad():
        features = model.forward_features(x)  # (1, C, T')
        logits = model.forward_head(features)
        grad_features, grad_input = torch.autograd.grad(
            logits[0, target_class], [features, x]
        )

    # Grad-CAM: channel weights = time-averaged gradients
    weights = grad_features[0].mean(dim=1, keepdim=True)  # (C, 1)
    cam = fn.relu((weights * features[0].detach()).sum(dim=0))  # (T',)
    cam = fn.interpolate(
        cam[None, None], size=x.shape[-1], mode='linear', align_corners=False
    )[0, 0]
    if cam.max() > 0:
        cam = cam / cam.max()

    # Gradient x input, smoothed so it highlights waveform regions, not single samples
    saliency = (grad_input[0] * x[0].detach()).abs()  # (12, T)
    saliency = fn.avg_pool1d(
        saliency[None], kernel_size=SMOOTHING_SAMPLES, stride=1,
        padding=SMOOTHING_SAMPLES // 2, count_include_pad=False,
    )[0]
    if saliency.max() > 0:
        saliency = saliency / saliency.max()

    return cam.cpu().numpy(), saliency.cpu().numpy()


def find_attention_segments(
    attention: np.ndarray,
    threshold: float = ATTENTION_THRESHOLD,
    fs: int = SAMPLING_RATE,
    max_segments: int = MAX_SEGMENTS,
) -> list[dict[str, float]]:
    """Return the strongest contiguous regions where attention exceeds threshold."""
    above = np.concatenate([[False], attention > threshold, [False]])
    edges = np.flatnonzero(np.diff(above.astype(int)))
    segments = [
        {
            'start_s': round(start / fs, 2),
            'end_s': round(end / fs, 2),
            'peak': float(attention[start:end].max()),
        }
        for start, end in zip(edges[::2], edges[1::2])
    ]
    segments.sort(key=lambda s: s['peak'], reverse=True)
    return sorted(segments[:max_segments], key=lambda s: s['start_s'])


def _downsample(arr: np.ndarray, factor: int) -> np.ndarray:
    """Average-pool the last axis by an integer factor."""
    usable = arr.shape[-1] - arr.shape[-1] % factor
    return arr[..., :usable].reshape(*arr.shape[:-1], -1, factor).mean(axis=-1)


class ECGExplainer:
    """High-level explainer for ECG predictions."""

    def __init__(self, model: nn.Module):
        self.model = model

    def explain_prediction(
        self,
        signal_tensor: torch.Tensor,
        diagnosis_idx: int,
        diagnosis_name: str,
        lead_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Generate an explanation for one predicted class.

        Args:
            signal_tensor: Preprocessed model input (1, 12, 5000), on the model's device
            diagnosis_idx: Index of diagnosis to explain
            diagnosis_name: Name of diagnosis (e.g., "MI")
            lead_names: Names of ECG leads

        Returns:
            Explanation dictionary with importance scores, heatmaps and a description
        """
        lead_names = lead_names or LEAD_NAMES

        cam, saliency = compute_attributions(self.model, signal_tensor, diagnosis_idx)

        lead_importance = saliency.mean(axis=1)
        if lead_importance.max() > 0:
            lead_importance = lead_importance / lead_importance.max()
        ranked = np.argsort(lead_importance)[::-1]
        important_leads = [lead_names[i] for i in ranked[:4]]

        segments = find_attention_segments(cam)
        time_range = (
            ", ".join(f"{s['start_s']:.2f}s-{s['end_s']:.2f}s" for s in segments)
            if segments else "N/A"
        )

        factor = SAMPLING_RATE // HEATMAP_RATE
        return {
            'diagnosis': diagnosis_name,
            'important_leads': important_leads,
            'lead_importance_scores': {
                lead_names[i]: round(float(lead_importance[i]), 4) for i in ranked
            },
            'important_segments': segments,
            'important_time_range': time_range,
            'heatmap_sampling_rate': HEATMAP_RATE,
            'temporal_attention': np.round(_downsample(cam, factor), 4).tolist(),
            'heatmap': np.round(_downsample(saliency, factor), 4).tolist(),
            'description': self._describe(diagnosis_name, important_leads, time_range),
        }

    @staticmethod
    def _describe(diagnosis: str, leads: list[str], time_range: str) -> str:
        """
        Plain-language summary of where the model looked.

        Deliberately describes model attention, not ECG findings: the attribution
        tells us which regions influenced the score, not what morphology is there.
        """
        name = DIAGNOSIS_NAMES.get(diagnosis, diagnosis)
        text = (
            f"The prediction of {name} was driven mostly by leads {', '.join(leads)}."
        )
        if time_range != "N/A":
            text += f" Model attention peaked at {time_range}."
        return text + " Review these regions on the tracing to confirm."


def explain_top_prediction(
    model: nn.Module,
    signal_tensor: torch.Tensor,
    diagnoses: list[dict[str, Any]],
    superclasses: list[str],
    patient_age: int | None = None,
    patient_sex: str | None = None,
    recommendations: list[dict[str, Any]] | None = None,
    use_llm: bool = False,
) -> dict[str, Any]:
    """
    Explain the top prediction.

    Args:
        model: Trained model
        signal_tensor: Preprocessed model input (1, 12, 5000), on the model's device
        diagnoses: List of diagnoses with confidence scores, sorted descending
        superclasses: List of class names
        patient_age: Patient age (for LLM context)
        patient_sex: Patient sex (for LLM context)
        recommendations: Clinical recommendations (for LLM context)
        use_llm: Whether to use LLM for explanation (slower but better)

    Returns:
        Explanation for the primary diagnosis
    """
    if not diagnoses:
        return {'explanation': 'No diagnosis to explain'}

    primary_dx = diagnoses[0]
    dx_name = primary_dx['diagnosis']

    explanation = ECGExplainer(model).explain_prediction(
        signal_tensor=signal_tensor,
        diagnosis_idx=superclasses.index(dx_name),
        diagnosis_name=dx_name,
    )
    explanation['confidence'] = primary_dx['confidence']

    if use_llm and os.getenv("DISABLE_LLM_EXPLANATIONS", "false").lower() != "true":
        try:
            from src.ml.explainability.ollama_explainer import get_ollama_explainer

            llm_description = get_ollama_explainer().generate_explanation(
                diagnosis=dx_name,
                confidence=primary_dx['confidence'],
                important_leads=explanation['important_leads'],
                time_range=explanation['important_time_range'],
                patient_age=patient_age,
                patient_sex=patient_sex,
                recommendations=recommendations or [],
            )
            explanation['rule_based_description'] = explanation['description']
            explanation['llm_description'] = llm_description
            explanation['description'] = llm_description
        except Exception as e:
            print(f"⚠️ LLM explanation failed, using rule-based: {e}")

    return explanation
