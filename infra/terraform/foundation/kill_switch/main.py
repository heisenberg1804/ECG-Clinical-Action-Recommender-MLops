"""
Budget kill switch: unlinks the project's billing account when actual spend
reaches the budget. GCP budgets on their own only send alerts.

WARNING: with billing disabled, Google stops (and may eventually delete) the
project's billable resources. That is acceptable for this ephemeral demo
infrastructure and is the point of a hard cap.
"""
import os

import functions_framework
from budget import parse_budget_message, should_disable_billing

PROJECT_NAME = f"projects/{os.environ['TARGET_PROJECT_ID']}"


@functions_framework.cloud_event
def stop_billing(cloud_event) -> None:
    payload = parse_budget_message(cloud_event.data["message"]["data"])
    cost, budget = payload.get("costAmount"), payload["budgetAmount"]

    if not should_disable_billing(payload):
        print(f"Spend {cost} below budget {budget}; no action")
        return

    from google.cloud import billing_v1

    client = billing_v1.CloudBillingClient()
    info = client.get_project_billing_info(name=PROJECT_NAME)
    if not info.billing_enabled:
        print("Billing already disabled")
        return

    client.update_project_billing_info(
        name=PROJECT_NAME,
        project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name=""),
    )
    print(f"Spend {cost} reached budget {budget}: billing disabled for {PROJECT_NAME}")
