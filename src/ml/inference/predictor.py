# ============================================================
# FILE: src/ml/inference/predictor.py (WITH MLFLOW SUPPORT)
# ============================================================
"""
Model inference logic for clinical action recommendation.

Handles:
- Model loading (from file or MLflow Registry)
- Preprocessing
- Inference
- Action mapping
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

from src.ml.models.resnet1d import resnet18_1d
from src.ml.preprocessing.signal import TARGET_FS, prepare_ecg

DEFAULT_THRESHOLD = float(os.getenv("PREDICTION_THRESHOLD", "0.3"))
DEFAULT_TOP_K = int(os.getenv("MAX_RECOMMENDATIONS", "5"))


class ClinicalActionPredictor:
    """Predicts clinical actions from ECG signals."""

    def __init__(
        self,
        model_path: Path | str | None = None,
        model_name: str | None = None,
        model_stage: str = "Production",
        action_mapping_path: Path | str | None = None,
        device: str | None = None,
        mlflow_tracking_uri: str | None = None,
    ):
        """
        Initialize predictor.

        Args:
            model_path: Path to trained PyTorch model (.pth file).
                       If None, loads from MLflow Model Registry.
            model_name: MLflow model registry name (used if model_path is None)
            model_stage: MLflow model stage (Production, Staging, etc.)
            action_mapping_path: Path to action mapping JSON
            device: Device to run inference on. Auto-detect if None.
            mlflow_tracking_uri: MLflow tracking URI. Uses env var if None.
        """
        self.model_path = Path(model_path) if model_path else None
        self.model_name = model_name
        self.model_stage = model_stage
        self.mlflow_tracking_uri = mlflow_tracking_uri or os.getenv(
            "MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"
        )
        self.action_mapping_path = Path(action_mapping_path) if action_mapping_path else None

        # Auto-detect device
        if device is None:
            if torch.backends.mps.is_available():
                self.device = torch.device("mps")
            elif torch.cuda.is_available():
                self.device = torch.device("cuda")
            else:
                self.device = torch.device("cpu")
        else:
            self.device = torch.device(device)

        # Load model
        self.superclasses = ['NORM', 'MI', 'STTC', 'CD', 'HYP']
        self.model_version = os.getenv("MODEL_VERSION", "")
        self.weights_digest = ""
        self.model = self._load_model()

        # Load action mapping
        self.action_mapping = self._load_action_mapping()

        # Per-class thresholds tuned on the validation fold, if the model ships with them
        self.thresholds = self._load_thresholds()

    def _load_model(self) -> nn.Module:
        """Load trained model from file or MLflow Registry."""
        model = resnet18_1d(num_classes=len(self.superclasses), include_patient_context=False)

        # Load from MLflow Model Registry if model_name provided
        if self.model_path is None and self.model_name:
            print(f"📦 Loading model from MLflow Registry: {self.model_name}/{self.model_stage}")
            try:
                import mlflow
                import mlflow.pytorch

                mlflow.set_tracking_uri(self.mlflow_tracking_uri)

                # Load model from registry
                model_uri = f"models:/{self.model_name}/{self.model_stage}"
                loaded_model = mlflow.pytorch.load_model(model_uri, map_location=self.device)

                # MLflow returns the full model, we just need to move to device
                loaded_model = loaded_model.to(self.device)
                loaded_model.eval()

                print("✅ Model loaded from MLflow Registry")
                self.model_version = self.model_version or f"{self.model_name}/{self.model_stage}"
                return loaded_model

            except Exception as e:
                print(f"⚠️  Failed to load from MLflow: {e}")
                print("   Falling back to file-based loading...")
                # Fall through to file-based loading

        # Load from file path
        if self.model_path and self.model_path.exists():
            print(f"📦 Loading model from file: {self.model_path}")
            state_dict = torch.load(self.model_path, map_location=self.device, weights_only=True)
            model.load_state_dict(state_dict)
            model = model.to(self.device)
            model.eval()
            # Tie every logged prediction to the exact weights that produced it
            self.weights_digest = hashlib.sha256(self.model_path.read_bytes()).hexdigest()[:12]
            if not self.model_version or self.model_version == "latest":
                self.model_version = f"resnet18-{self.weights_digest}"
            print(f"✅ Model loaded from file ({self.model_version})")
            return model

        raise FileNotFoundError(
            f"No model found. Tried: "
            f"MLflow Registry ({self.model_name}), "
            f"File path ({self.model_path})"
        )

    def _load_thresholds(self) -> dict[str, float]:
        """Read thresholds from model_meta.json next to the weights; fall back to a global one."""
        meta_path = self.model_path.with_name("model_meta.json") if self.model_path else None
        if meta_path and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            if meta.get("model_version") == f"resnet18-{self.weights_digest}":
                print(f"✅ Using tuned thresholds from {meta_path.name}")
                return {c: float(meta["thresholds"][c]) for c in self.superclasses}
            print(f"⚠️  {meta_path.name} does not match the loaded weights; ignoring it")
        return dict.fromkeys(self.superclasses, DEFAULT_THRESHOLD)

    def _load_action_mapping(self) -> dict[str, list[dict[str, str]]]:
        """Load diagnostic → action mapping."""
        if self.action_mapping_path is None:
            self.action_mapping_path = Path(__file__).parent / "action_mapping.json"

        with open(self.action_mapping_path) as f:
            return json.load(f)

    def preprocess_signal(
        self, signal: np.ndarray, sampling_rate: int = TARGET_FS
    ) -> torch.Tensor:
        """
        Preprocess ECG signal exactly as during training (see prepare_ecg).

        Returns:
            Preprocessed tensor, shape (1, 12, 5000)

        Raises:
            ValueError: If the signal is malformed or shorter than 10 seconds
        """
        return torch.from_numpy(prepare_ecg(signal, sampling_rate)).unsqueeze(0)

    def predict(
        self,
        signal: np.ndarray,
        sampling_rate: int = TARGET_FS,
        threshold: float | None = None,
        top_k: int = DEFAULT_TOP_K,
        explain: bool = False,
        use_llm: bool = False,
        patient_age: int | None = None,
        patient_sex: str | None = None,
    ) -> dict[str, Any]:
        """
        Predict clinical actions from ECG signal.

        Args:
            signal: ECG signal, shape (12, num_samples) or (num_samples, 12)
            sampling_rate: Sampling rate of `signal` in Hz
            threshold: Override for all classes; defaults to the per-class tuned thresholds
            top_k: Return top K recommendations
            explain: If True, generate explanation for top prediction
            use_llm: If True, ask the local LLM to phrase the explanation
            patient_age: Patient age (LLM context only)
            patient_sex: Patient sex (LLM context only)

        Returns:
            Dictionary with:
                - probabilities: Sigmoid output for every class
                - diagnoses: Classes above threshold, sorted by confidence
                - recommendations: List of recommended clinical actions
                - explanation: (optional) Explanation for top diagnosis
        """
        thresholds = (
            self.thresholds if threshold is None else dict.fromkeys(self.superclasses, threshold)
        )

        # Preprocess
        signal_tensor = self.preprocess_signal(signal, sampling_rate).to(self.device)

        # Inference
        with torch.no_grad():
            logits = self.model(signal_tensor)
            probs = torch.sigmoid(logits).cpu().numpy()[0]

        # Get predicted diagnoses
        diagnoses = []
        for i, (sc, prob) in enumerate(zip(self.superclasses, probs)):
            if prob > thresholds[sc]:
                diagnoses.append({
                    'diagnosis': sc,
                    'confidence': float(prob),
                })

        # Sort by confidence
        diagnoses = sorted(diagnoses, key=lambda x: x['confidence'], reverse=True)

        # Map to actions
        recommendations = []
        seen_actions = set()  # Avoid duplicate actions

        for dx in diagnoses:
            dx_name = dx['diagnosis']
            if dx_name in self.action_mapping:
                for action_dict in self.action_mapping[dx_name]:
                    action_text = action_dict['action']
                    if action_text not in seen_actions:
                        recommendations.append({
                            'action': action_text,
                            'confidence': dx['confidence'],  # Inherit from diagnosis
                            'urgency': action_dict['urgency'],
                            'reasoning': action_dict['reasoning'],
                        })
                        seen_actions.add(action_text)

        # Nothing above threshold: the model is not confident in any class,
        # including NORM, so defer to a human rather than implying "normal"
        if not recommendations:
            recommendations = [{
                'action': 'Manual ECG review recommended',
                'confidence': float(1.0 - probs.max()),
                'urgency': 'routine',
                'reasoning': 'No diagnostic class exceeded its confidence threshold',
            }]

        # Sort by urgency (immediate > urgent > routine), then by confidence
        urgency_order = {'immediate': 0, 'urgent': 1, 'routine': 2}
        recommendations = sorted(
            recommendations,
            key=lambda x: (urgency_order.get(x['urgency'], 3), -x['confidence'])
        )

        # Limit to top_k
        recommendations = recommendations[:top_k]

        result = {
            'probabilities': {sc: float(p) for sc, p in zip(self.superclasses, probs)},
            'diagnoses': diagnoses,
            'recommendations': recommendations,
        }

        # Generate explanation if requested
        if explain and diagnoses:
            from src.ml.explainability.explainer import explain_top_prediction

            explanation = explain_top_prediction(
                model=self.model,
                signal_tensor=signal_tensor,
                diagnoses=diagnoses,
                superclasses=self.superclasses,
                patient_age=patient_age,
                patient_sex=patient_sex,
                recommendations=recommendations,
                use_llm=use_llm,
            )

            result['explanation'] = explanation

        return result


# Singleton instance (lazy loading)
_predictor_instance = None


def get_predictor(
    model_path: Path | str | None = None,
    model_name: str | None = None,
    action_mapping_path: Path | str | None = None,
) -> ClinicalActionPredictor:
    """
    Get singleton predictor instance.

    Lazy loads model on first call. Subsequent calls return cached instance.

    Args:
        model_path: Path to model file (for local/file-based loading)
        model_name: MLflow model name (for registry-based loading)
        action_mapping_path: Path to action mapping

    Priority:
        1. If model_name provided → load from MLflow Registry
        2. If model_path provided → load from file
        3. Default → try file at models/best_model.pth
    """
    global _predictor_instance

    if _predictor_instance is None:
        # Check for MLflow model name in environment
        mlflow_model_name = model_name or os.getenv("MLFLOW_MODEL_NAME")

        # Default paths for file-based loading
        if model_path is None and mlflow_model_name is None:
            model_path = Path(__file__).parents[3] / "models" / "best_model.pth"

        if action_mapping_path is None:
            action_mapping_path = Path(__file__).parent / "action_mapping.json"

        _predictor_instance = ClinicalActionPredictor(
            model_path=model_path,
            model_name=mlflow_model_name,
            action_mapping_path=action_mapping_path,
        )

    return _predictor_instance
