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


def run_specialist(runtime: AgentRuntime, agent: str, case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    order_id = case["customer_request"]["claimed_order_id"]
    contract = REPORT_CONTRACTS[agent]
    user = f"Case: {json.dumps(case, ensure_ascii=False)}\nClaimed order_id: {order_id}\nReturn exactly this report shape: {contract}"
    runtime.handoff(case_id, "coordinator", agent, "task", f"Investigate assigned domain for {order_id}", {"order_id": order_id})
    report = runtime.run_json(case_id=case_id, agent=agent, system=SPECIALIST_PROMPTS[agent], user=user, allowed_tools=SPECIALIST_TOOLS[agent])
    classes = {"customer_investigator": CustomerReport, "order_product_investigator": OrderProductReport, "payment_auditor": PaymentReport, "delivery_investigator": DeliveryReport}
    validated = classes[agent].model_validate(report)
    runtime.trace.write("agent_report_created", case_id, agent, report_status=validated.status, evidence_count=len(validated.evidence))
    return validated.model_dump()
