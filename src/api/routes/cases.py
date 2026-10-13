# ============================================================
# FILE: src/api/routes/cases.py
# ============================================================
"""
Case bank endpoints for the learner UI (D-53, D-54).

A student loads a case (signal and demographics only), commits a read, then
reveals the cardiologist label and the model's output. Explanations are served
per class on demand. Answer locking is enforced from v1b, with the tutor's
signed session token (D-57); v1a relies on the honour system.
"""
import os
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.casebank.store import CaseBank, dequantize
from src.ml.training.data import SUPERCLASSES

router = APIRouter()

DEFAULT_BANK_DIR = Path(__file__).parents[3] / "models" / "case_bank"
_bank: CaseBank | None = None
_bank_error = "Case bank not loaded"


def load_bank(model_version: str) -> None:
    """Called at startup. A missing or mismatched bank disables these routes, not the API."""
    global _bank, _bank_error
    bank_dir = Path(os.getenv("CASE_BANK_DIR", DEFAULT_BANK_DIR))
    try:
        _bank = CaseBank.load(bank_dir, expected_model_version=model_version)
        print(f"✅ Case bank loaded: {_bank.manifest['n_cases']} cases ({bank_dir})")
    except FileNotFoundError:
        _bank, _bank_error = None, f"No case bank at {bank_dir}. Build one: make case-bank"
    except ValueError as e:
        _bank, _bank_error = None, str(e)
    if _bank is None:
        print(f"⚠️  {_bank_error}")


def bank() -> CaseBank:
    if _bank is None:
        raise HTTPException(status_code=503, detail=_bank_error)
    return _bank


def case(case_id: str) -> tuple[int, dict]:
    b = bank()
    try:
        i = b.index_of(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown case {case_id}")
    return i, b.cases[i]


class CaseSummary(BaseModel):
    case_id: str
    age: str | None
    sex: str


class CaseList(BaseModel):
    model_version: str
    n_cases: int
    cases: list[CaseSummary]


class CaseSignal(CaseSummary):
    sampling_rate: int
    leads: list[str]
    signal_mv: list[list[float]] = Field(description="12 x n samples, millivolts")


class RevealRequest(BaseModel):
    answer: list[str] = Field(default_factory=list, description="Classes the student chose")


class Reveal(BaseModel):
    case_id: str
    ptbxl_ecg_id: int
    labels: list[str]
    primary_label: str
    label_likelihoods: dict[str, float]
    report: str | None
    quality_flags: dict[str, str]
    model: dict
    student_answer: list[str]
    agreement: dict[str, dict[str, bool]] = Field(
        description="Per class: does the student / model agree with the cardiologist?"
    )


class Explanation(BaseModel):
    case_id: str
    diagnosis: str
    sampling_rate: int
    lead_importance: dict[str, float]
    temporal_attention: list[float]
    heatmap: list[list[float]]
    important_segments: list[dict]
    description: str


@router.get("/cases", response_model=CaseList)
async def list_cases() -> CaseList:
    b = bank()
    return CaseList(
        model_version=b.manifest["model_version"],
        n_cases=b.manifest["n_cases"],
        cases=[CaseSummary(case_id=c["case_id"], age=c["age"], sex=c["sex"]) for c in b.cases],
    )


@router.get("/cases/{case_id}", response_model=CaseSignal)
async def get_case(case_id: str) -> CaseSignal:
    """The ECG and demographics only: nothing that gives the answer away."""
    i, c = case(case_id)
    b = bank()
    return CaseSignal(
        case_id=c["case_id"], age=c["age"], sex=c["sex"],
        sampling_rate=b.manifest["display_fs"], leads=b.manifest["lead_names"],
        signal_mv=np.round(b.signals[i].astype(np.float32), 3).tolist(),
    )


@router.post("/cases/{case_id}/reveal", response_model=Reveal)
async def reveal(case_id: str, body: RevealRequest) -> Reveal:
    unknown = set(body.answer) - set(SUPERCLASSES)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown classes: {sorted(unknown)}")
    _, c = case(case_id)
    truth, model_pred = set(c["labels"]), set(c["model"]["predicted"])
    agreement = {
        cls: {"student": (cls in body.answer) == (cls in truth),
              "model": (cls in model_pred) == (cls in truth)}
        for cls in SUPERCLASSES
    }
    return Reveal(
        case_id=c["case_id"], ptbxl_ecg_id=c["ptbxl_ecg_id"], labels=c["labels"],
        primary_label=c["primary_label"], label_likelihoods=c["label_likelihoods"],
        report=c["report"], quality_flags=c["quality_flags"], model=c["model"],
        student_answer=sorted(body.answer, key=SUPERCLASSES.index), agreement=agreement,
    )


@router.get("/cases/{case_id}/explanation/{diagnosis}", response_model=Explanation)
async def explanation(case_id: str, diagnosis: str) -> Explanation:
    """Where the model looked for one class. Lead and time attributions, 0-1."""
    if diagnosis not in SUPERCLASSES:
        raise HTTPException(status_code=404, detail=f"Unknown class {diagnosis}")
    i, c = case(case_id)
    b, k = bank(), SUPERCLASSES.index(diagnosis)
    text = c["model"]["explanations"][diagnosis]
    return Explanation(
        case_id=c["case_id"], diagnosis=diagnosis, sampling_rate=b.manifest["heatmap_fs"],
        lead_importance={lead: round(float(v), 4)
                         for lead, v in zip(b.manifest["lead_names"], b.lead_importance[i, k])},
        temporal_attention=np.round(dequantize(b.temporal[i, k]), 3).tolist(),
        heatmap=np.round(dequantize(b.heatmap[i, k]), 3).tolist(),
        important_segments=text["important_segments"],
        description=text["description"],
    )
