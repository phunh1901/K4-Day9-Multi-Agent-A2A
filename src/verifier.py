"""
verifier.py — Thành viên A
Kiểm tra JSON output trước khi ghi file.
Phát hiện vi phạm schema, giới hạn mảng, null handling, confidence range.
Trả về list lỗi (rỗng = hợp lệ).
"""
from __future__ import annotations

from typing import Any

ARRAY_LIMITS = {
    "order_ids": 5,
    "item_ids": 5,
    "seller_ids": 3,
    "payment_ids": 5,
    "related_order_ids": 5,
    "product_ids": 5,
    "category_names": 5,
    "ranked_causes": 3,
    "responsible_parties": 3,
    "evidence_ids": 20,
    "resolution_actions": 5,
}

VALID_PRIMARY_ISSUES = {
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
}

VALID_SECONDARY_ISSUES = {
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
}

VALID_CASE_STATUS = {"action_required", "no_action"}

VALID_EVIDENCE_PREFIXES = ("order:", "item:", "payment:", "seller:", "policy:")


def verify_output(result: dict) -> list[str]:
    """
    Kiểm tra một output dict.
    Trả về danh sách lỗi (list rỗng = pass).
    """
    errors: list[str] = []

    def _check(condition: bool, msg: str):
        if not condition:
            errors.append(msg)

    # --- Top-level keys ---
    required_keys = [
        "case_id", "case_assessment", "affected_entities",
        "customer_context", "product_context", "delivery_analysis",
        "payment_reconciliation", "root_cause_analysis", "evidence_ids",
        "financial_resolution", "resolution_actions",
    ]
    for k in required_keys:
        _check(k in result, f"Missing top-level key: {k}")

    # --- case_assessment ---
    ca = result.get("case_assessment", {})
    primary = ca.get("primary_issue", "")
    _check(primary in VALID_PRIMARY_ISSUES, f"Invalid primary_issue: {primary!r}")
    for si in ca.get("secondary_issues", []):
        _check(si in VALID_SECONDARY_ISSUES, f"Invalid secondary_issue: {si!r}")
    _check(ca.get("case_status") in VALID_CASE_STATUS,
           f"Invalid case_status: {ca.get('case_status')!r}")
    conf = ca.get("confidence")
    _check(
        isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0,
        f"confidence must be in [0, 1], got {conf!r}",
    )

    # --- affected_entities array limits ---
    ae = result.get("affected_entities", {})
    for field, limit_key in [
        ("order_ids", "order_ids"),
        ("item_ids", "item_ids"),
        ("seller_ids", "seller_ids"),
        ("payment_ids", "payment_ids"),
    ]:
        arr = ae.get(field, [])
        _check(len(arr) <= ARRAY_LIMITS[limit_key],
               f"affected_entities.{field} exceeds limit {ARRAY_LIMITS[limit_key]} (got {len(arr)})")

    # --- customer_context ---
    cc = result.get("customer_context", {})
    related = cc.get("related_order_ids", [])
    _check(len(related) <= ARRAY_LIMITS["related_order_ids"],
           f"related_order_ids exceeds limit {ARRAY_LIMITS['related_order_ids']} (got {len(related)})")

    # --- product_context array limits ---
    pc = result.get("product_context", {})
    _check(len(pc.get("product_ids", [])) <= ARRAY_LIMITS["product_ids"],
           f"product_ids exceeds limit")
    _check(len(pc.get("category_names", [])) <= ARRAY_LIMITS["category_names"],
           f"category_names exceeds limit")

    # --- evidence_ids format & limit ---
    evs = result.get("evidence_ids", [])
    _check(len(evs) <= ARRAY_LIMITS["evidence_ids"],
           f"evidence_ids exceeds limit {ARRAY_LIMITS['evidence_ids']} (got {len(evs)})")
    for ev in evs:
        _check(
            isinstance(ev, str) and any(ev.startswith(p) for p in VALID_EVIDENCE_PREFIXES),
            f"Invalid evidence_id format: {ev!r}",
        )

    # --- resolution_actions limit ---
    ra = result.get("resolution_actions", [])
    _check(len(ra) <= ARRAY_LIMITS["resolution_actions"],
           f"resolution_actions exceeds limit {ARRAY_LIMITS['resolution_actions']} (got {len(ra)})")

    # --- root_cause_analysis limits ---
    rca = result.get("root_cause_analysis", {})
    _check(len(rca.get("ranked_causes", [])) <= ARRAY_LIMITS["ranked_causes"],
           "ranked_causes exceeds limit 3")
    _check(len(rca.get("responsible_parties", [])) <= ARRAY_LIMITS["responsible_parties"],
           "responsible_parties exceeds limit 3")

    # --- financial_resolution ---
    fr = result.get("financial_resolution", {})
    refund = fr.get("recommended_refund_brl")
    _check(isinstance(refund, (int, float)), f"recommended_refund_brl must be numeric, got {refund!r}")

    # --- case_status consistency with refund ---
    cs = ca.get("case_status")
    if isinstance(refund, (int, float)):
        if refund > 0:
            _check(cs == "action_required",
                   f"case_status should be 'action_required' when refund > 0 (got {cs!r})")
        else:
            _check(cs == "no_action",
                   f"case_status should be 'no_action' when refund == 0 (got {cs!r})")

    return errors
