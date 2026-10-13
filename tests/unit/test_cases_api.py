# ============================================================
# FILE: tests/unit/test_cases_api.py
# ============================================================
"""Learner case endpoints and the model card, against a synthetic case bank."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.casebank.store import write_bank
from src.ml.inference.predictor import get_predictor
from src.ml.training.data import SUPERCLASSES

ANSWER_KEYS = {"labels", "primary_label", "label_likelihoods", "report", "model", "ptbxl_ecg_id"}


def synthetic_bank(path, model_version: str, n: int = 3) -> None:
    rng = np.random.default_rng(0)
    explanations = {c: {"important_leads": ["II", "III", "aVF", "V1"],
                        "important_segments": [{"start_s": 1.0, "end_s": 1.5, "peak": 1.0}],
                        "description": f"attention for {c}"} for c in SUPERCLASSES}
    cases = [{
        "case_id": f"case-{i + 1:03d}", "age": "61", "sex": "M", "ptbxl_ecg_id": 210 + i,
        "labels": ["MI"], "primary_label": "MI", "label_likelihoods": {"MI": 80.0},
        "scp_codes": {"IMI": 80.0}, "report": "inferiorer infarkt", "quality_flags": {},
        "model": {"probabilities": dict.fromkeys(SUPERCLASSES, 0.1) | {"MI": 0.48},
                  "predicted": ["MI"], "primary_correct": True, "explanations": explanations},
    } for i in range(n)]
    write_bank(path, {"model_version": model_version, "display_fs": 250, "heatmap_fs": 50,
                      "lead_names": ["I", "II", "III", "aVR", "aVL", "aVF",
                                     "V1", "V2", "V3", "V4", "V5", "V6"],
                      "source": "synthetic", "built_at": "2026-10-13T00:00:00+00:00",
                      "selection": {"per_class": 1}},
               cases, signals=rng.normal(size=(n, 12, 2500)),
               lead_importance=rng.uniform(size=(n, 5, 12)),
               temporal=rng.uniform(size=(n, 5, 500)), heatmap=rng.uniform(size=(n, 5, 12, 500)))


def client_with_bank(tmp_path, monkeypatch, model_version):
    synthetic_bank(tmp_path, model_version)
    monkeypatch.setenv("CASE_BANK_DIR", str(tmp_path))
    from src.api.main import app
    return TestClient(app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    with client_with_bank(tmp_path, monkeypatch, get_predictor().model_version) as c:
        yield c


def test_list_shows_no_answer_material(client):
    body = client.get("/cases").json()
    assert body["n_cases"] == 3 and len(body["cases"]) == 3
    assert all(set(c) == {"case_id", "age", "sex"} for c in body["cases"])


def test_case_signal_has_no_answer(client):
    body = client.get("/cases/case-001").json()
    assert not ANSWER_KEYS & set(body)
    assert np.array(body["signal_mv"]).shape == (12, 2500) and body["sampling_rate"] == 250


def test_reveal_scores_student_and_model(client):
    body = client.post("/cases/case-002/reveal", json={"answer": ["NORM"]}).json()
    assert body["labels"] == ["MI"] and body["report"] == "inferiorer infarkt"
    assert body["agreement"]["MI"] == {"student": False, "model": True}
    assert body["agreement"]["NORM"] == {"student": False, "model": True}
    assert body["agreement"]["CD"] == {"student": True, "model": True}


def test_reveal_rejects_unknown_class(client):
    assert client.post("/cases/case-001/reveal", json={"answer": ["AFIB"]}).status_code == 422


def test_unknown_case_is_404(client):
    assert client.get("/cases/case-999").status_code == 404


def test_explanation_per_class(client):
    body = client.get("/cases/case-001/explanation/MI").json()
    assert len(body["lead_importance"]) == 12 and body["sampling_rate"] == 50
    assert np.array(body["heatmap"]).shape == (12, 500)
    assert client.get("/cases/case-001/explanation/AFIB").status_code == 404


def test_large_payloads_are_gzipped(client):
    r = client.get("/cases/case-001", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_model_card_derives_limitations(client):
    card = client.get("/model/card").json()
    assert card["model_version"] == get_predictor().model_version
    assert card["case_bank"]["n_cases"] == 3
    assert any(line.startswith("Weakest class: HYP") for line in card["limitations"])
    assert any(line.startswith("Less accurate for patients over 65")
               for line in card["limitations"])


def test_mismatched_bank_disables_only_case_routes(tmp_path, monkeypatch):
    with client_with_bank(tmp_path, monkeypatch, "resnet18-not-the-served-one") as c:
        r = c.get("/cases")
        assert r.status_code == 503 and "make case-bank" in r.json()["detail"]
        assert c.get("/ready").status_code == 200
