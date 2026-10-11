# ============================================================
# FILE: tests/unit/test_kill_switch.py
# ============================================================
"""Decision logic of the budget kill switch Cloud Function (infra/terraform/foundation)."""
import base64
import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[2] / "infra/terraform/foundation/kill_switch/budget.py"
_spec = importlib.util.spec_from_file_location("kill_switch_budget", _PATH)
budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(budget)


def message(**payload) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_parses_pubsub_payload():
    data = message(costAmount=3.2, budgetAmount=15.0, budgetDisplayName="cap")
    assert budget.parse_budget_message(data)["costAmount"] == 3.2


@pytest.mark.parametrize(
    "cost, expected", [(0.0, False), (14.99, False), (15.0, True), (40.0, True)]
)
def test_disables_only_at_or_above_budget(cost, expected):
    assert budget.should_disable_billing({"costAmount": cost, "budgetAmount": 15.0}) is expected


def test_forecast_alone_never_triggers():
    """Forecast notifications carry a low actual costAmount; only actual spend counts."""
    payload = {"costAmount": 2.0, "budgetAmount": 15.0, "alertThresholdExceeded": 1.0,
               "forecastThresholdExceeded": 1.0}
    assert budget.should_disable_billing(payload) is False


def test_missing_cost_is_treated_as_zero():
    assert budget.should_disable_billing({"budgetAmount": 15.0}) is False
