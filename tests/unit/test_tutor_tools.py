"""Tutor session tokens and tools (D-56, D-57), against a synthetic case bank."""
import json

import numpy as np
import pytest

from src.casebank.store import CaseBank
from src.ml.labels import SUPERCLASSES
from src.tutor import session as s
from src.tutor.tools import LOCKED, ToolBox
from tests.unit.test_cases_api import synthetic_bank

META = {
    "model_version": "resnet18-test", "test_macro_auc": 0.91,
    "thresholds": dict.fromkeys(SUPERCLASSES, 0.3),
    "test_per_class_auc": dict.fromkeys(SUPERCLASSES, 0.9),
    "test_ece": dict.fromkeys(SUPERCLASSES, 0.03),
    "test_at_threshold": {c: {"f1": 0.7, "sensitivity": 0.8, "specificity": 0.9}
                          for c in SUPERCLASSES},
    "test_subgroup_auc": {"sex_male": 0.92, "sex_female": 0.90, "age_lt40": 0.91,
                          "age_40to65": 0.90, "age_gt65": 0.89},
}
LOCKED_TOOLS = {"get_cardiologist_label", "get_model_prediction", "get_model_attention",
                "occlude_leads", "occlude_window", "find_similar_cases"}
VALID_INPUT = {
    "get_case_facts": {}, "get_model_performance": {}, "get_cardiologist_label": {},
    "get_model_prediction": {}, "find_similar_cases": {},
    "measure_lead": {"lead": "II", "start_s": 0, "end_s": 1},
    "get_model_attention": {"diagnosis": "MI"},
    "occlude_leads": {"leads": ["III"]}, "occlude_window": {"start_s": 1, "end_s": 2},
}


class FakePredictor:
    """MI probability tracks lead III's energy, so occluding it visibly changes the call."""

    def __init__(self):
        self.signals = []

    def predict(self, signal, sampling_rate):
        self.signals.append(signal.copy())
        mi = min(1.0, float(np.abs(signal[2]).mean()))
        return {"probabilities": dict.fromkeys(SUPERCLASSES, 0.1) | {"MI": mi}}


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("TUTOR_SESSION_SECRET", "test-secret")


def make_toolbox(path) -> ToolBox:
    synthetic_bank(path, "resnet18-test")
    return ToolBox(CaseBank.load(path), FakePredictor(), META)


@pytest.fixture
def toolbox(tmp_path):
    return make_toolbox(tmp_path)


reading = s.Session(case_id="case-001")
committed = reading.commit(["MI"])


class TestSessionToken:
    def test_round_trip(self):
        assert s.verify(s.sign(committed)) == committed

    def test_tampered_payload_is_rejected(self):
        payload, mac = s.sign(reading).split(".")
        forged = s._b64(json.dumps({**json.loads(s._unb64(payload)), "phase": "committed"})
                        .encode())
        with pytest.raises(s.InvalidSessionError):
            s.verify(f"{forged}.{mac}")

    def test_other_servers_tokens_are_rejected(self, monkeypatch):
        token = s.sign(reading)
        monkeypatch.setenv("TUTOR_SESSION_SECRET", "another-secret")
        with pytest.raises(s.InvalidSessionError):
            s.verify(token)

    @pytest.mark.parametrize("token", ["", "abc", "a.b.c", "!!!.???"])
    def test_garbage_is_rejected(self, token):
        with pytest.raises(s.InvalidSessionError):
            s.verify(token)

    def test_expired_token_is_rejected(self):
        with pytest.raises(s.InvalidSessionError):
            s.verify(s.sign(reading), now=reading.issued_at + s.TOKEN_TTL_S + 1)

    def test_commit_is_one_way(self):
        with pytest.raises(ValueError):
            committed.commit(["NORM"])

    def test_missing_secret_fails_loudly(self, monkeypatch):
        monkeypatch.delenv("TUTOR_SESSION_SECRET")
        with pytest.raises(RuntimeError):
            s.sign(reading)


class TestToolGating:
    def test_answer_tools_are_locked_while_reading(self, toolbox):
        for name in LOCKED_TOOLS:
            assert toolbox.run(name, VALID_INPUT[name], reading) is LOCKED

    def test_every_tool_runs_once_committed(self, toolbox):
        for name, inp in VALID_INPUT.items():
            result = toolbox.run(name, inp, committed)
            assert not result.is_error, (name, result.content)
            json.loads(result.as_text())  # what the model receives is valid JSON

    def test_reading_tools_reveal_nothing(self, toolbox):
        text = "".join(toolbox.run(n, VALID_INPUT[n], reading).as_text()
                       for n in VALID_INPUT if n not in LOCKED_TOOLS)
        for leak in ("inferiorer", "IMI", "primary_correct", "probabilities", "0.48"):
            assert leak not in text


class TestToolInputs:
    def test_schemas_are_strict(self, toolbox):
        for schema in toolbox.schemas():
            body = schema["input_schema"]
            assert schema["strict"] and body["additionalProperties"] is False
            assert set(body["required"]) == set(body["properties"])
            assert "minimum" not in json.dumps(body)  # ranges are checked server-side

    def test_schemas_cover_every_tool(self, toolbox):
        assert {t["name"] for t in toolbox.schemas()} == set(VALID_INPUT)

    @pytest.mark.parametrize("name,bad", [
        ("measure_lead", {"lead": "II", "start_s": 0}),                       # missing field
        ("measure_lead", {"lead": "II", "start_s": 0, "end_s": 1, "x": 1}),  # extra field
        ("measure_lead", {"lead": "V9", "start_s": 0, "end_s": 1}),          # unknown lead
        ("measure_lead", {"lead": "II", "start_s": 3, "end_s": 2}),          # reversed window
        ("measure_lead", {"lead": "II", "start_s": 0, "end_s": 99}),         # past the end
        ("get_model_attention", {"diagnosis": "AFIB"}),
        ("occlude_leads", {"leads": []}),
        ("occlude_leads", "not-an-object"),
    ])
    def test_bad_input_is_an_error_not_a_crash(self, toolbox, name, bad):
        assert toolbox.run(name, bad, committed).is_error

    def test_unknown_tool(self, toolbox):
        assert toolbox.run("rm_rf", {}, committed).is_error


class TestToolResults:
    def test_measure_lead_matches_the_signal(self, toolbox):
        r = toolbox.run("measure_lead", {"lead": "V1", "start_s": 1, "end_s": 2}, reading).content
        seg = toolbox.bank.signals[0, 6, 250:500].astype(np.float32)
        assert r["max_mv"] == pytest.approx(seg.max(), abs=1e-3)
        assert r["peak_to_peak_mv"] == pytest.approx(seg.max() - seg.min(), abs=2e-3)

    def test_occluding_a_lead_flattens_only_that_lead(self, toolbox):
        r = toolbox.run("occlude_leads", {"leads": ["III"]}, committed).content
        before, after = toolbox.predictor.signals[-2:]
        assert not after[2].any() and np.array_equal(before[[0, 1]], after[[0, 1]])
        assert r["per_class"]["MI"]["after"] == 0.0 and r["per_class"]["MI"]["change"] < 0

    def test_occluding_a_window_flattens_every_lead_there(self, toolbox):
        toolbox.run("occlude_window", {"start_s": 1, "end_s": 2}, committed)
        after = toolbox.predictor.signals[-1]
        assert not after[:, 250:500].any() and after[:, :250].any()

    def test_similar_cases_exclude_the_current_case(self, toolbox):
        cases = toolbox.run("find_similar_cases", {}, committed).content["cases"]
        assert cases and "case-001" not in {c["case_id"] for c in cases}

    def test_performance_reports_only_this_patients_groups(self, toolbox):
        groups = toolbox.run("get_model_performance", {}, reading).content
        assert set(groups["auc_for_this_patients_groups"]) == {"sex_male", "age_40to65"}
