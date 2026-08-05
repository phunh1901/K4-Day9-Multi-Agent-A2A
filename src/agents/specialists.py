from __future__ import annotations

import json
from typing import Any

from src.agents.prompts import REPORT_CONTRACTS, SPECIALIST_PROMPTS
from src.agents.runtime import AgentRuntime
from src.models import CustomerReport, DeliveryReport, OrderProductReport, PaymentReport


SPECIALIST_TOOLS = {
    "customer_investigator": ["get_order_customer", "get_customer", "get_orders_by_unique_customer"],
    "order_product_investigator": ["get_order", "get_order_items", "get_product", "get_seller"],
    "payment_auditor": ["get_order_payments", "get_order_items", "sum_money", "add_money", "subtract_money", "compare_money_with_tolerance"],
    "delivery_investigator": ["get_order_delivery_timestamps", "get_order_items", "hours_between"],
}


def _normalize_evidence(values: list[Any], case_id: str) -> list[str]:
    """Convert tool-record evidence accidentally echoed by the model to valid IDs."""
    normalized: list[str] = []
    for value in values:
        if isinstance(value, str):
            normalized.append(value)
            continue
        if not isinstance(value, dict):
            continue
        order_id = value.get("order_id")
        if value.get("payment_sequential") is not None and order_id:
            normalized.append(f"payment:{order_id}:{value['payment_sequential']}")
        elif value.get("order_item_id") is not None and order_id:
            normalized.append(f"item:{order_id}:{value['order_item_id']}")
        elif value.get("seller_id"):
            normalized.append(f"seller:{value['seller_id']}")
        elif order_id:
            normalized.append(f"order:{order_id}")
    return list(dict.fromkeys(normalized))


def run_specialist(runtime: AgentRuntime, agent: str, case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    order_id = case["customer_request"]["claimed_order_id"]
    contract = REPORT_CONTRACTS[agent]
    user = f"Case: {json.dumps(case, ensure_ascii=False)}\nClaimed order_id: {order_id}\nReturn exactly this report shape: {contract}"
    runtime.handoff(case_id, "coordinator", agent, "task", f"Investigate assigned domain for {order_id}", {"order_id": order_id})
    classes = {"customer_investigator": CustomerReport, "order_product_investigator": OrderProductReport, "payment_auditor": PaymentReport, "delivery_investigator": DeliveryReport}
    def validate_report(payload: dict[str, Any]) -> Any:
        if isinstance(payload.get("evidence"), list):
            payload["evidence"] = _normalize_evidence(payload["evidence"], case_id)
        invalid = [evidence_id for evidence_id in payload.get("evidence", []) if not runtime.tools.store.evidence_exists(evidence_id)]
        if invalid:
            raise ValueError(f"invalid evidence IDs: {invalid}")
        return classes[agent].model_validate(payload)
    report = runtime.run_json(case_id=case_id, agent=agent, system=SPECIALIST_PROMPTS[agent], user=user, allowed_tools=SPECIALIST_TOOLS[agent], validator=validate_report, max_rounds=12 if agent == "order_product_investigator" else (10 if agent == "delivery_investigator" else (8 if agent in {"customer_investigator", "payment_auditor"} else None)))
    if isinstance(report.get("evidence"), list):
        report["evidence"] = _normalize_evidence(report["evidence"], case_id)
    validated = classes[agent].model_validate(report)
    runtime.trace.write("agent_report_created", case_id, agent, report_status=validated.status, evidence_count=len(validated.evidence))
    return validated.model_dump()


async def run_specialist_async(runtime: AgentRuntime, agent: str, case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    order_id = case["customer_request"]["claimed_order_id"]
    contract = REPORT_CONTRACTS[agent]
    user = f"Case: {json.dumps(case, ensure_ascii=False)}\nClaimed order_id: {order_id}\nReturn exactly this report shape: {contract}"
    runtime.handoff(case_id, "coordinator", agent, "task", f"Investigate assigned domain for {order_id}", {"order_id": order_id})
    classes = {"customer_investigator": CustomerReport, "order_product_investigator": OrderProductReport, "payment_auditor": PaymentReport, "delivery_investigator": DeliveryReport}

    def validate_report(payload: dict[str, Any]) -> Any:
        if isinstance(payload.get("evidence"), list):
            payload["evidence"] = _normalize_evidence(payload["evidence"], case_id)
        invalid = [evidence_id for evidence_id in payload.get("evidence", []) if not runtime.tools.store.evidence_exists(evidence_id)]
        if invalid:
            raise ValueError(f"invalid evidence IDs: {invalid}")
        return classes[agent].model_validate(payload)

    report = await runtime.run_json_async(case_id=case_id, agent=agent, system=SPECIALIST_PROMPTS[agent], user=user, allowed_tools=SPECIALIST_TOOLS[agent], validator=validate_report, max_rounds=12 if agent == "order_product_investigator" else (10 if agent == "delivery_investigator" else (8 if agent in {"customer_investigator", "payment_auditor"} else None)))
    report["evidence"] = _normalize_evidence(report.get("evidence", []), case_id)
    validated = classes[agent].model_validate(report)
    runtime.trace.write("agent_report_created", case_id, agent, report_status=validated.status, evidence_count=len(validated.evidence), mode="async")
    return validated.model_dump()
