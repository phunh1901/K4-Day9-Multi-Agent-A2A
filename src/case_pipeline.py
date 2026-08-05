"""Deterministic single-case pipeline.

This mirrors the agent hand-off graph one-to-one: customer -> order/product ->
payment -> delivery -> policy -> verifier. Step 2 replaces the direct calls
with agent messages, but the tools each agent may call are exactly these.
"""

from __future__ import annotations

from typing import List, Tuple

from . import domain_analyzer, policy_evaluator, output_schema


def solve_case(store, case: dict) -> Tuple[dict, List[str]]:
    """Return the submission document plus any verifier complaints."""
    case_id = case["case_id"]
    order_id = case["customer_request"]["claimed_order_id"]

    order = store.get_order(order_id)
    if order is None:
        raise KeyError(f"{case_id}: claimed_order_id {order_id} not present in orders CSV")

    items = store.get_items(order_id)
    payments = store.get_payments(order_id)

    customer = domain_analyzer.resolve_customer(store, order)
    products = domain_analyzer.describe_products(store, items)
    counts = domain_analyzer.summarize_order(items, payments, products["category_names"])
    payment_view = domain_analyzer.reconcile_payments(items, payments)
    delivery = domain_analyzer.analyze_delivery(order, items)
    late = domain_analyzer.is_late_delivery(delivery)

    verdict = policy_evaluator.apply_policy(
        order, delivery, payment_view, counts, customer["related_order_ids"], late
    )

    evidence_ids = policy_evaluator.build_evidence_ids(
        order_id,
        counts["item_ids"][: output_schema.LIMITS["item_ids"]],
        counts["payment_ids"][: output_schema.LIMITS["payment_ids"]],
        verdict["responsible_parties"],
        verdict["root_cause_code"],
    )

    doc = output_schema.build_case_output(
        case_id, order_id, delivery, payment_view, customer, products,
        counts, verdict, evidence_ids,
    )
    return doc, output_schema.verify_case_output(doc, case_id, store)
