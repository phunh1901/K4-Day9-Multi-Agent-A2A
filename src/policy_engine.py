"""
policy_engine.py — Thành viên A
Áp dụng EC_POLICY_V2 để xác định:
  - Primary issue
  - Secondary issues (đúng thứ tự ưu tiên)
  - Responsible parties
  - Recommended refund
  - Root cause codes
  - Evidence IDs
  - Resolution actions
Chỉ dựa trên dữ liệu có thể kiểm chứng từ CSV. Không tạo ra sự kiện giả.
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Constants — Policy EC_POLICY_V2
# ---------------------------------------------------------------------------

PRIMARY_ISSUES_ORDER = [
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]

SECONDARY_ISSUES_ORDER = [
    "multi_item_order",
    "multi_seller_order",
    "split_payment",
    "repeat_customer",
    "multiple_categories",
]

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _limit(lst: list, key: str) -> list:
    """Giới hạn kích thước mảng theo ARRAY_LIMITS."""
    return lst[: ARRAY_LIMITS.get(key, len(lst))]


# ---------------------------------------------------------------------------
# Primary issue determination
# ---------------------------------------------------------------------------

def determine_primary_issue(
    order: dict,
    items: list[dict],
    payments: list[dict],
    payment_reconciliation: dict,
    delivery_analysis: dict,
) -> str:
    """
    Xác định primary issue theo đúng thứ tự ưu tiên EC_POLICY_V2.
    """
    order_status = (order.get("order_status") or "").strip().lower()
    payment_total = payment_reconciliation.get("payment_total_brl") or 0.0

    # 1. canceled_order_paid
    if order_status == "canceled" and payment_total > 0:
        return "canceled_order_paid"

    # 2. unavailable_order_paid
    if order_status == "unavailable" and payment_total > 0:
        return "unavailable_order_paid"

    delivered_at = order.get("order_delivered_customer_date")
    estimated_at = order.get("order_estimated_delivery_date")
    delivery_variance = delivery_analysis.get("delivery_variance_hours")
    late_handoff_sellers = delivery_analysis.get("late_handoff_seller_ids", [])

    is_late = (
        delivered_at is not None
        and estimated_at is not None
        and delivery_variance is not None
        and delivery_variance > 0
    )

    # 3. late_delivery_seller
    if is_late and len(late_handoff_sellers) > 0:
        return "late_delivery_seller"

    # 4. late_delivery_logistics
    if is_late and len(late_handoff_sellers) == 0:
        return "late_delivery_logistics"

    # 5. valid_split_payment
    reconciled = payment_reconciliation.get("reconciled")
    if len(payments) >= 2 and reconciled is True:
        return "valid_split_payment"

    # 6. unsupported_late_claim (default)
    return "unsupported_late_claim"


# ---------------------------------------------------------------------------
# Secondary issues
# ---------------------------------------------------------------------------

def determine_secondary_issues(
    items: list[dict],
    payments: list[dict],
    customer_order_ids: list[str],
    claimed_order_id: str,
    category_names: list[str],
) -> list[str]:
    """Xác định secondary issues theo đúng thứ tự ưu tiên."""
    issues = []
    unique_sellers = list(dict.fromkeys(i.get("seller_id", "") for i in items if i.get("seller_id")))
    related_orders = [o for o in customer_order_ids if o != claimed_order_id]

    if len(items) >= 2:
        issues.append("multi_item_order")
    if len(unique_sellers) >= 2:
        issues.append("multi_seller_order")
    if len(payments) >= 2:
        issues.append("split_payment")
    if len(related_orders) > 0:
        issues.append("repeat_customer")
    if len(set(c for c in category_names if c)) >= 2:
        issues.append("multiple_categories")

    return issues


# ---------------------------------------------------------------------------
# Delivery analysis
# ---------------------------------------------------------------------------

def build_delivery_analysis(order: dict, items: list[dict], data_engine) -> dict:
    """
    Xây dựng delivery_analysis block đầy đủ.
    data_engine là module src.data_engine để gọi compute_*.
    Lưu ý: handoff_variance_hours = carrier_handoff_at - shipping_limit_date sớm nhất của seller.
    """
    delivered_at = order.get("order_delivered_customer_date")
    estimated_at = order.get("order_estimated_delivery_date")
    carrier_handoff_at = order.get("order_delivered_carrier_date")

    # Delivery variance
    delivery_variance = data_engine.compute_delivery_variance(order)

    # Group items by seller_id to find the EARLIEST shipping_limit_date for each seller
    seller_earliest_limit: dict[str, str] = {}
    for item in items:
        sid = item.get("seller_id")
        limit = item.get("shipping_limit_date")
        if sid and limit:
            if sid not in seller_earliest_limit or str(limit) < str(seller_earliest_limit[sid]):
                seller_earliest_limit[sid] = limit

    seller_handoff_list = []
    late_handoff_seller_ids = []

    for sid, earliest_limit in seller_earliest_limit.items():
        dummy_item = {"shipping_limit_date": earliest_limit}
        h_variance = data_engine.compute_handoff_variance(order, dummy_item)
        is_late = h_variance is not None and h_variance > 0

        seller_handoff_list.append({
            "seller_id": sid,
            "shipping_limit_at": earliest_limit,
            "handoff_variance_hours": h_variance,
            "late_handoff": is_late,
        })
        if is_late and sid not in late_handoff_seller_ids:
            late_handoff_seller_ids.append(sid)

    # Normalize timestamps: trả về None nếu NaT/empty
    def _ts(val):
        if not val or str(val).strip().lower() in ("nan", "none", "nat", ""):
            return None
        return str(val).strip()

    return {
        "delivered_at": _ts(delivered_at),
        "estimated_delivery_at": _ts(estimated_at),
        "carrier_handoff_at": _ts(carrier_handoff_at),
        "delivery_variance_hours": delivery_variance,
        "seller_handoff_analysis": seller_handoff_list,
        "late_handoff_seller_ids": late_handoff_seller_ids,
    }


# ---------------------------------------------------------------------------
# Evidence IDs
# ---------------------------------------------------------------------------

def build_evidence_ids(
    order_id: str,
    items: list[dict],
    payments: list[dict],
    responsible_seller_ids: list[str],
    root_cause_code: str,
) -> list[str]:
    """
    Sinh evidence_ids đúng định dạng từ dữ liệu CSV thực.
    Tối đa 20 evidence IDs.
    """
    evs: list[str] = []

    evs.append(f"order:{order_id}")

    for item in items:
        seq = item.get("order_item_id", "")
        evs.append(f"item:{order_id}:{seq}")

    for pay in payments:
        seq = pay.get("payment_sequential", "")
        evs.append(f"payment:{order_id}:{seq}")

    for sid in responsible_seller_ids:
        evs.append(f"seller:{sid}")

    evs.append(f"policy:{root_cause_code}")

    return _limit(evs, "evidence_ids")


# ---------------------------------------------------------------------------
# Root cause code mapping
# ---------------------------------------------------------------------------

ROOT_CAUSE_MAP = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}


def get_root_cause_code(primary_issue: str) -> str:
    return ROOT_CAUSE_MAP.get(primary_issue, "DELIVERY_WITHIN_ESTIMATE")


# ---------------------------------------------------------------------------
# Financial resolution
# ---------------------------------------------------------------------------

def compute_financial_resolution(
    primary_issue: str,
    payment_reconciliation: dict,
) -> dict:
    """
    Tính khoản hoàn đề xuất theo policy.
    - canceled/unavailable -> hoàn full payment
    - late_delivery_*      -> hoàn freight
    - Còn lại              -> 0
    """
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        refund = round(payment_reconciliation.get("payment_total_brl") or 0.0, 2)
    elif primary_issue in ("late_delivery_seller", "late_delivery_logistics"):
        refund = round(payment_reconciliation.get("freight_total_brl") or 0.0, 2)
    else:
        refund = 0.0

    return {"currency": "BRL", "recommended_refund_brl": refund}


# ---------------------------------------------------------------------------
# Resolution actions
# ---------------------------------------------------------------------------

def build_resolution_actions(
    primary_issue: str,
    secondary_issues: list[str],
    delivery_analysis: dict,
    payments: list[dict],
) -> list[str]:
    """
    Xây dựng danh sách resolution_actions.
    Action chính -> bổ sung theo thứ tự (review_seller_handoff / review_carrier_delay,
    verify_refund_completion, coordinate_multi_seller_case, verify_payment_allocation).
    Không thêm verify_payment_allocation khi primary là valid_split_payment.
    """
    # Map primary action
    primary_action_map = {
        "canceled_order_paid": "issue_full_refund",
        "unavailable_order_paid": "issue_full_refund",
        "late_delivery_seller": "refund_freight",
        "late_delivery_logistics": "refund_freight",
        "valid_split_payment": "explain_valid_split_payment",
        "unsupported_late_claim": "reject_late_refund",
    }
    actions = [primary_action_map[primary_issue]]

    # Supplemental actions theo thứ tự
    late_sellers = delivery_analysis.get("late_handoff_seller_ids", [])
    if primary_issue == "late_delivery_seller" and late_sellers:
        actions.append("review_seller_handoff")
    elif primary_issue == "late_delivery_logistics":
        actions.append("review_carrier_delay")

    if primary_issue in ("canceled_order_paid", "unavailable_order_paid",
                         "late_delivery_seller", "late_delivery_logistics"):
        actions.append("verify_refund_completion")

    if "multi_seller_order" in secondary_issues:
        actions.append("coordinate_multi_seller_case")

    if primary_issue != "valid_split_payment" and len(payments) >= 2:
        actions.append("verify_payment_allocation")

    return _limit(actions, "resolution_actions")


# ---------------------------------------------------------------------------
# Responsible parties
# ---------------------------------------------------------------------------

def build_responsible_parties(
    primary_issue: str,
    late_handoff_seller_ids: list[str],
) -> list[dict]:
    """Xác định danh sách responsible_parties."""
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]

    if primary_issue == "late_delivery_seller":
        parties = [{"party_type": "seller", "party_id": sid} for sid in late_handoff_seller_ids]
        return _limit(parties, "responsible_parties")

    if primary_issue == "late_delivery_logistics":
        return [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]

    return []
