# ============================================================
# FILE: tests/unit/test_inference.py
# ============================================================
"""Predictor and explainer behaviour, including regressions from the Oct 2026 audit."""
from pathlib import Path

import numpy as np
import pytest

from src.ml.explainability.explainer import find_attention_segments
from src.ml.inference.predictor import DEFAULT_THRESHOLD, ClinicalActionPredictor

MODEL_PATH = Path(__file__).parents[2] / "models" / "best_model.pth"


@pytest.fixture(scope="module")
def predictor():
    return ClinicalActionPredictor(model_path=MODEL_PATH, device="cpu")


@pytest.fixture
def signal():
    return np.random.default_rng(42).normal(size=(12, 5000)).astype(np.float32)


class TestPreprocessing:
    def test_output_shape_and_normalization(self, predictor, signal):
        x = predictor.preprocess_signal(signal * 3 + 1).numpy()[0]
        assert x.shape == (12, 5000)
        np.testing.assert_allclose(x.mean(axis=1), 0, atol=1e-4)
        np.testing.assert_allclose(x.std(axis=1), 1, atol=1e-3)

    def test_accepts_samples_by_leads_layout(self, predictor, signal):
        assert predictor.preprocess_signal(signal.T).shape == (1, 12, 5000)

    def test_resamples_by_sampling_rate(self, predictor):
        ten_s_at_250 = np.random.default_rng(0).normal(size=(12, 2500))
        assert predictor.preprocess_signal(ten_s_at_250, sampling_rate=250).shape == (1, 12, 5000)

    def test_longer_signals_are_cropped_to_10s(self, predictor):
        twenty_s = np.random.default_rng(0).normal(size=(12, 10000))
        assert predictor.preprocess_signal(twenty_s).shape == (1, 12, 5000)

    def test_rejects_short_signals(self, predictor):
        with pytest.raises(ValueError, match="at least 10 s"):
            predictor.preprocess_signal(np.zeros((12, 2500)))

    def test_rejects_non_finite(self, predictor, signal):
        signal[0, 10] = np.nan
        with pytest.raises(ValueError, match="NaN"):
            predictor.preprocess_signal(signal)


class TestPredict:
    def test_returns_all_class_probabilities(self, predictor, signal):
        result = predictor.predict(signal)
        assert set(result["probabilities"]) == set(predictor.superclasses)

    def test_no_confident_class_falls_back_to_review(self, predictor, signal):
        """Regression: this path raised KeyError('confidence')."""
        result = predictor.predict(signal, threshold=1.0)
        assert result["diagnoses"] == []
        [rec] = result["recommendations"]
        assert rec["action"] == "Manual ECG review recommended"
        assert 0.0 <= rec["confidence"] <= 1.0

    def test_model_version_identifies_weights(self, predictor):
        assert predictor.model_version.startswith("resnet18-")


class TestExplanation:
    def explain(self, predictor, signal):
        result = predictor.predict(signal, threshold=0.0, explain=True)
        return result["explanation"]

    def test_lead_importance_differs_across_leads(self, predictor, signal):
        """Regression: one temporal map was tiled to all leads, so every lead scored 1.0."""
        scores = self.explain(predictor, signal)["lead_importance_scores"]
        assert len(scores) == 12
        assert len(set(scores.values())) > 1
        assert max(scores.values()) == pytest.approx(1.0)

    def test_explains_the_preprocessed_input(self, predictor, signal):
        """
        Regression: Grad-CAM ran on the raw signal. Prediction is invariant to
        per-lead scale/offset (z-score), so the explanation must be too.
        """
        a = self.explain(predictor, signal)
        b = self.explain(predictor, signal * 7.0 + 3.0)
        assert a["important_leads"] == b["important_leads"]
        np.testing.assert_allclose(a["temporal_attention"], b["temporal_attention"], atol=1e-3)

    def test_leaves_no_hooks_on_model(self, predictor, signal):
        """Regression: each call registered new hooks on the shared model."""
        for _ in range(3):
            self.explain(predictor, signal)
        assert all(not m._forward_hooks and not m._backward_hooks
                   for m in predictor.model.modules())

    def test_does_not_accumulate_parameter_gradients(self, predictor, signal):
        self.explain(predictor, signal)
        assert all(p.grad is None for p in predictor.model.parameters())


def test_find_attention_segments():
    attention = np.zeros(5000)
    attention[500:750] = 0.9  # 1.00-1.50 s
    attention[3000:3100] = 0.6  # 6.00-6.20 s
    segments = find_attention_segments(attention)
    assert [(s["start_s"], s["end_s"]) for s in segments] == [(1.0, 1.5), (6.0, 6.2)]


class TestModelMeta:
    def test_tuned_thresholds_are_used_when_meta_matches(self, predictor):
        import json
        meta = json.loads(MODEL_PATH.with_name("model_meta.json").read_text())
        assert predictor.model_version == meta["model_version"]
        assert predictor.thresholds == meta["thresholds"]

    def test_mismatched_meta_is_ignored(self, tmp_path):
        import json
        import shutil

        shutil.copy(MODEL_PATH, tmp_path / "best_model.pth")
        (tmp_path / "model_meta.json").write_text(json.dumps({
            "model_version": "resnet18-000000000000",
            "thresholds": dict.fromkeys(["NORM", "MI", "STTC", "CD", "HYP"], 0.99),
        }))
        p = ClinicalActionPredictor(model_path=tmp_path / "best_model.pth", device="cpu")
        assert set(p.thresholds.values()) == {DEFAULT_THRESHOLD}
