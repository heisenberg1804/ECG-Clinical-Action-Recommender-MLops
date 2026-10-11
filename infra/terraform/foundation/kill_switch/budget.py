"""Pure decision logic for the budget kill switch (unit-tested, no GCP imports)."""
import base64
import json


def parse_budget_message(data_b64: str) -> dict:
    """Decode the JSON payload Cloud Billing publishes to the budget Pub/Sub topic."""
    return json.loads(base64.b64decode(data_b64))


def should_disable_billing(payload: dict) -> bool:
    """
    True once actual spend has reached the budget.

    Cloud Billing sends forecast-based notifications too; only actual
    cost (costAmount) may trigger a shutdown.
    """
    return float(payload.get("costAmount", 0.0)) >= float(payload["budgetAmount"])
