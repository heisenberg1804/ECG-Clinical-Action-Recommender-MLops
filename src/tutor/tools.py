"""
The tutor's tools (D-56): lookups into the case bank and the served model.

Every case-specific claim the tutor makes must come from one of these results;
each carries a `source` label the UI shows as a chip. Tools that would reveal
the answer refuse to run until the session is committed (D-57). The full set is
declared on every request, so the tool list never changes mid-conversation.
"""
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.casebank.store import CaseBank
from src.ml.labels import SUPERCLASSES
from src.tutor.session import COMMITTED, Session

MAX_SIMILAR = 3


class Predictor(Protocol):
    def predict(self, signal: np.ndarray, sampling_rate: int) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ToolResult:
    content: dict[str, Any]
    source: str  # Short label for the UI's source chip
    is_error: bool = False

    def as_text(self) -> str:
        return json.dumps(self.content, separators=(",", ":"))


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoInput(Strict):
    pass


class MeasureLead(Strict):
    lead: str
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)


class Diagnosis(Strict):
    diagnosis: str


class Leads(Strict):
    leads: list[str] = Field(min_length=1, max_length=11)


class Window(Strict):
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: type[Strict]
    locked: bool  # Reveals the answer, so needs a committed session
    run: Callable[..., ToolResult]
    # JSON-schema properties sent to the API. Kept to plain types and enums; ranges
    # are checked by `params` (pydantic) when the tool runs
    properties: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict[str, Any]:
        """Strict tool definition: every property required, nothing extra."""
        props = self.properties
        return {
            "name": self.name,
            "description": self.description,
            "strict": True,
            "eager_input_streaming": True,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": list(props),
                "additionalProperties": False,
            },
        }


LOCKED = ToolResult(
    content={
        "error": "locked",
        "message": "The student hasn't committed a read yet. Don't reveal or hint at the "
                   "answer or the model's output; guide their reading, then ask them to commit.",
    },
    source="Answer lock",
    is_error=True,
)


def age_band(age: str | None) -> str | None:
    try:
        years = int(age)
    except (TypeError, ValueError):
        return None
    return "age_lt40" if years < 40 else "age_40to65" if years <= 65 else "age_gt65"


class ToolBox:
    def __init__(self, bank: CaseBank, predictor: Predictor, model_meta: dict):
        self.bank = bank
        self.predictor = predictor
        self.meta = model_meta
        self.leads: list[str] = bank.manifest["lead_names"]
        self.fs: int = bank.manifest["display_fs"]
        self.tools = {t.name: t for t in self._define()}

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self.tools.values()]

    def run(self, name: str, raw_input: Any, session: Session) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult({"error": f"Unknown tool {name}"}, source="Error", is_error=True)
        if tool.locked and session.phase != COMMITTED:
            return LOCKED
        try:
            params = tool.params.model_validate(raw_input)
        except ValidationError as e:
            # Eager input streaming hands over unvalidated input; reject it like bad JSON
            return ToolResult({"error": "invalid_input", "detail": e.errors(include_url=False)},
                              source="Error", is_error=True)
        idx = self.bank.index_of(session.case_id)
        try:
            return tool.run(idx, params)
        except ValueError as e:
            return ToolResult({"error": str(e)}, source="Error", is_error=True)

    # ------------------------------------------------------------------ tools

    def _define(self) -> list[Tool]:
        lead = {"type": "string", "enum": self.leads}
        seconds = {"type": "number", "description": "Seconds from the start of the recording"}
        return [
            Tool("get_case_facts",
                 "The patient's age and sex, and the recording's leads, duration and sampling "
                 "rate. Contains nothing about the diagnosis. Always available.",
                 NoInput, False, self._case_facts),
            Tool("measure_lead",
                 "Measure one lead between two times (seconds from the start): minimum, "
                 "maximum, peak-to-peak and mean amplitude in millivolts. Use it to ground "
                 "statements about voltages and deflections. Always available.",
                 MeasureLead, False, self._measure_lead,
                 {"lead": lead, "start_s": seconds, "end_s": seconds}),
            Tool("get_model_performance",
                 "How good the model is overall: test-set AUC, F1, sensitivity, specificity "
                 "and calibration error (ECE) per class, and its AUC for this patient's sex "
                 "and age group. Says nothing about this case. Always available.",
                 NoInput, False, self._model_performance),
            Tool("get_cardiologist_label",
                 "The ground truth for this case: the cardiologist's diagnostic classes with "
                 "their likelihoods, the SCP codes, and the original (German) report. Locked "
                 "until the student commits a read.",
                 NoInput, True, self._label),
            Tool("get_model_prediction",
                 "The model's probability for each class on this case, its decision "
                 "thresholds, the classes it predicts, and whether its main call was right. "
                 "Locked until the student commits a read.",
                 NoInput, True, self._prediction),
            Tool("get_model_attention",
                 "Where the model looked for one diagnosis on this case: its most important "
                 "leads, the time windows it attended to, and per-lead importance. "
                 f"`diagnosis` is one of {', '.join(SUPERCLASSES)}. Locked until the student "
                 "commits a read.",
                 Diagnosis, True, self._attention,
                 {"diagnosis": {"type": "string", "enum": list(SUPERCLASSES)}}),
            Tool("occlude_leads",
                 "Re-run the model with some leads flattened (as if disconnected) and report "
                 "how each class probability changes. Answers questions like 'does it still "
                 "call MI without lead III?'. Locked until the student commits a read.",
                 Leads, True, self._occlude_leads,
                 {"leads": {"type": "array", "items": lead}}),
            Tool("occlude_window",
                 "Re-run the model with a time window flattened on all leads, and report how "
                 "each class probability changes. Locked until the student commits a read.",
                 Window, True, self._occlude_window,
                 {"start_s": seconds, "end_s": seconds}),
            Tool("find_similar_cases",
                 f"Up to {MAX_SIMILAR} other practice cases with the same main diagnosis, with "
                 "whether the model got each one right, for comparison. Locked until the "
                 "student commits a read.",
                 NoInput, True, self._similar),
        ]

    def _case(self, idx: int) -> dict:
        return self.bank.cases[idx]

    def _case_facts(self, idx: int, _: NoInput) -> ToolResult:
        c = self._case(idx)
        return ToolResult({
            "age": c["age"], "sex": c["sex"], "leads": self.leads,
            "duration_s": self.bank.signals.shape[2] / self.fs, "sampling_rate_hz": self.fs,
        }, source="Case record")

    def _window(self, start_s: float, end_s: float) -> slice:
        duration = self.bank.signals.shape[2] / self.fs
        if not start_s < end_s <= duration:
            raise ValueError(f"Window must satisfy 0 <= start_s < end_s <= {duration}")
        return slice(int(start_s * self.fs), max(int(end_s * self.fs), int(start_s * self.fs) + 1))

    def _lead_index(self, lead: str) -> int:
        if lead not in self.leads:
            raise ValueError(f"Unknown lead {lead!r}; expected one of {self.leads}")
        return self.leads.index(lead)

    def _measure_lead(self, idx: int, p: MeasureLead) -> ToolResult:
        seg = self.bank.signals[idx, self._lead_index(p.lead), self._window(p.start_s, p.end_s)]
        seg = seg.astype(np.float32)
        return ToolResult({
            "lead": p.lead, "start_s": p.start_s, "end_s": p.end_s,
            "min_mv": round(float(seg.min()), 3), "max_mv": round(float(seg.max()), 3),
            "peak_to_peak_mv": round(float(seg.max() - seg.min()), 3),
            "mean_mv": round(float(seg.mean()), 3),
        }, source=f"Signal: {p.lead}")

    def _model_performance(self, idx: int, _: NoInput) -> ToolResult:
        c, m = self._case(idx), self.meta
        groups = {f"sex_{'male' if c['sex'] == 'M' else 'female'}", age_band(c["age"])}
        return ToolResult({
            "model_version": m["model_version"],
            "evaluated_on": "PTB-XL test fold 10 (patients never seen in training)",
            "test_macro_auc": round(m["test_macro_auc"], 3),
            "per_class": {
                k: {"auc": round(m["test_per_class_auc"][k], 3),
                    "ece": round(m["test_ece"][k], 3),
                    "threshold": m["thresholds"][k],
                    **{s: round(v, 3) for s, v in m["test_at_threshold"][k].items()}}
                for k in SUPERCLASSES
            },
            "auc_for_this_patients_groups": {
                g: round(v, 3) for g, v in m["test_subgroup_auc"].items() if g in groups
            },
        }, source="Model card")

    def _label(self, idx: int, _: NoInput) -> ToolResult:
        c = self._case(idx)
        return ToolResult({
            "labels": c["labels"], "primary_label": c["primary_label"],
            "label_likelihoods": c["label_likelihoods"], "scp_codes": c["scp_codes"],
            "report_de": c["report"],
        }, source="Cardiologist label")

    def _prediction(self, idx: int, _: NoInput) -> ToolResult:
        m = self._case(idx)["model"]
        return ToolResult({
            "probabilities": m["probabilities"], "thresholds": self.meta["thresholds"],
            "predicted": m["predicted"], "primary_correct": m["primary_correct"],
        }, source="Model output")

    def _attention(self, idx: int, p: Diagnosis) -> ToolResult:
        if p.diagnosis not in SUPERCLASSES:
            raise ValueError(f"Unknown diagnosis {p.diagnosis!r}; expected one of {SUPERCLASSES}")
        exp = self._case(idx)["model"]["explanations"][p.diagnosis]
        k = SUPERCLASSES.index(p.diagnosis)
        importance = self.bank.lead_importance[idx, k].astype(np.float32)
        return ToolResult({
            "diagnosis": p.diagnosis,
            "important_leads": exp["important_leads"],
            "important_segments": [{k: round(v, 2) for k, v in seg.items()}
                                   for seg in exp["important_segments"]],
            "lead_importance": {ld: round(float(v), 3) for ld, v in zip(self.leads, importance)},
        }, source=f"Model attention: {p.diagnosis}")

    def _rescore(self, idx: int, mask: Callable[[np.ndarray], None], what: str) -> ToolResult:
        signal = self.bank.signals[idx].astype(np.float32)
        before = self.predictor.predict(signal, sampling_rate=self.fs)["probabilities"]
        mask(signal)
        after = self.predictor.predict(signal, sampling_rate=self.fs)["probabilities"]
        thresholds = self.meta["thresholds"]
        return ToolResult({
            "occluded": what,
            "per_class": {
                k: {"before": round(before[k], 3), "after": round(after[k], 3),
                    "change": round(after[k] - before[k], 3),
                    "called_before": before[k] >= thresholds[k],
                    "called_after": after[k] >= thresholds[k]}
                for k in SUPERCLASSES
            },
        }, source=f"Occlusion: {what}")

    def _occlude_leads(self, idx: int, p: Leads) -> ToolResult:
        rows = [self._lead_index(ld) for ld in p.leads]

        def flatten(s: np.ndarray) -> None:
            s[rows] = 0.0
        return self._rescore(idx, flatten, "leads " + ", ".join(p.leads))

    def _occlude_window(self, idx: int, p: Window) -> ToolResult:
        cols = self._window(p.start_s, p.end_s)

        def flatten(s: np.ndarray) -> None:
            s[:, cols] = 0.0
        return self._rescore(idx, flatten, f"{p.start_s:g}-{p.end_s:g} s")

    def _similar(self, idx: int, _: NoInput) -> ToolResult:
        c = self._case(idx)
        probs = np.array([c["model"]["probabilities"][k] for k in SUPERCLASSES])
        others = [
            (float(np.abs(probs - [o["model"]["probabilities"][k] for k in SUPERCLASSES]).sum()), o)
            for j, o in enumerate(self.bank.cases)
            if j != idx and o["primary_label"] == c["primary_label"]
        ]
        others.sort(key=lambda t: t[0])
        return ToolResult({
            "main_diagnosis": c["primary_label"],
            "cases": [{"case_id": o["case_id"], "labels": o["labels"], "age": o["age"],
                       "sex": o["sex"], "model_correct": o["model"]["primary_correct"]}
                      for _, o in others[:MAX_SIMILAR]],
        }, source="Case bank")
