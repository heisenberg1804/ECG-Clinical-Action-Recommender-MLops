# ============================================================
# FILE: tests/unit/test_api.py
# ============================================================
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

CLASSES = {"NORM", "MI", "STTC", "CD", "HYP"}


@pytest.fixture(scope="module")
def client():
    # Context manager runs the lifespan, which loads the model like production
    with TestClient(app) as c:
        yield c


def ecg(n_samples: int = 5000, seed: int = 0) -> list[list[float]]:
    return np.random.default_rng(seed).normal(size=(12, n_samples)).round(4).tolist()


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_ready_reports_loaded_model(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["model"] == "loaded"
        assert body["model_version"]


class TestPredictEndpoint:
    """Tests for prediction endpoint."""

    def test_predict_valid_input(self, client):
        response = client.post(
            "/predict",
            json={"ecg_signal": ecg(), "patient_age": 65, "patient_sex": "M"},
        )
        assert response.status_code == 200
        data = response.json()
        assert set(data["probabilities"]) == CLASSES
        assert all(0.0 <= p <= 1.0 for p in data["probabilities"].values())
        assert len(data["recommendations"]) > 0
        assert data["ecg_id"]
        assert data["model_version"].startswith("resnet18-")

    def test_predict_without_demographics(self, client):
        response = client.post("/predict", json={"ecg_signal": ecg()})
        assert response.status_code == 200

    def test_predict_flat_signal_does_not_crash(self, client):
        """Regression: a featureless signal used to hit a KeyError in the fallback path."""
        response = client.post("/predict", json={"ecg_signal": [[0.1] * 5000] * 12})
        assert response.status_code == 200
        assert len(response.json()["recommendations"]) > 0

    def test_predict_invalid_leads(self, client):
        response = client.post("/predict", json={"ecg_signal": ecg()[:10]})
        assert response.status_code == 422

    def test_predict_ragged_leads(self, client):
        signal = ecg()
        signal[3] = signal[3][:4000]
        response = client.post("/predict", json={"ecg_signal": signal})
        assert response.status_code == 400

    def test_predict_too_short(self, client):
        response = client.post("/predict", json={"ecg_signal": ecg(2500)})
        assert response.status_code == 400
        assert "10 s" in response.json()["detail"]

    def test_predict_other_sampling_rate(self, client):
        """10 s at 250 Hz is valid input and gets resampled to 500 Hz."""
        response = client.post(
            "/predict", json={"ecg_signal": ecg(2500), "sampling_rate": 250}
        )
        assert response.status_code == 200

    def test_predict_with_explanation(self, client):
        response = client.post("/predict", json={"ecg_signal": ecg(), "explain": True})
        assert response.status_code == 200
        explanation = response.json()["explanation"]
        if explanation is not None and "heatmap" in explanation:
            assert len(explanation["lead_importance_scores"]) == 12
            assert np.array(explanation["heatmap"]).shape == (12, 500)
            assert len(explanation["temporal_attention"]) == 500
