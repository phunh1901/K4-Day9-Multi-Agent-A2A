from __future__ import annotations

from typing import Any, TypedDict


class InvestigationState(TypedDict, total=False):
    case: dict[str, Any]
    assignments: list[dict[str, Any]]
    customer_report: dict[str, Any]
    order_product_report: dict[str, Any]
    payment_report: dict[str, Any]
    delivery_report: dict[str, Any]
    investigation_dossier: dict[str, Any]
    policy_decision: dict[str, Any]
    verifier_result: dict[str, Any]
    final_output: dict[str, Any]
    revision_count: int
    errors: list[dict[str, Any]]
