"""
policy_engine.py — Đinh Quốc Việt (nhánh `viet`)
Hiện thực EC_POLICY_V2 dưới dạng hàm thuần (pure function), không đọc CSV,
không gọi mạng: cùng input luôn cho cùng output.

Chứa toàn bộ luật quyết định:
  - delivery analysis (variance giao hàng / bàn giao seller)
  - primary issue theo đúng thứ tự ưu tiên trong bảng chính sách
  - secondary issues theo đúng thứ tự nghiệp vụ
  - root cause, responsible parties, refund, actions, evidence
"""
from __future__ import annotations

from typing import Optional

from src.data_engine import OlistRepository, clean, to_float

# ---------------------------------------------------------------------------
# Hằng số chính sách EC_POLICY_V2
# ---------------------------------------------------------------------------

POLICY_VERSION = "EC_POLICY_V2"

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

ROOT_CAUSE_MAP = {
    "canceled_order_paid": "ORDER_CANCELED_AFTER_PAYMENT",
    "unavailable_order_paid": "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "late_delivery_seller": "SELLER_HANDOFF_AFTER_LIMIT",
    "late_delivery_logistics": "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "valid_split_payment": "MULTIPLE_PAYMENTS_RECONCILED",
    "unsupported_late_claim": "DELIVERY_WITHIN_ESTIMATE",
}

PRIMARY_ACTION_MAP = {
    "canceled_order_paid": "issue_full_refund",
    "unavailable_order_paid": "issue_full_refund",
    "late_delivery_seller": "refund_freight",
    "late_delivery_logistics": "refund_freight",
    "valid_split_payment": "explain_valid_split_payment",
    "unsupported_late_claim": "reject_late_refund",
}

# Ngưỡng đối soát: |difference_brl| <= 0.10 BRL
RECONCILE_TOLERANCE_BRL = 0.10

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


def limit(values: list, key: str) -> list:
    """Cắt mảng theo giới hạn schema, giữ nguyên thứ tự nguồn."""
    return values[: ARRAY_LIMITS.get(key, len(values))]


def dedupe(values: list) -> list:
    """Khử trùng lặp nhưng giữ thứ tự xuất hiện đầu tiên."""
    seen: set = set()
    out: list = []
    for v in values:
        if v is None or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


# ---------------------------------------------------------------------------
# Delivery analysis
# ---------------------------------------------------------------------------

def build_delivery_analysis(order: dict, items: list[dict], repo: OlistRepository) -> dict:
    """
    delivery_variance_hours = delivered_customer_date - estimated_delivery_date
    handoff_variance_hours  = delivered_carrier_date - shipping_limit_date sớm nhất của seller

    Mỗi seller xuất hiện đúng một dòng trong seller_handoff_analysis, thứ tự theo
    lần đầu seller đó xuất hiện trong order_items (đã sort theo order_item_id).
    Order không có item row -> seller_handoff_analysis và late_handoff_seller_ids rỗng.
    """
    earliest_limit_by_seller: dict[str, str] = {}
    seller_order: list[str] = []

    for item in items:
        seller_id = item.get("seller_id")
        shipping_limit = item.get("shipping_limit_date")
        if not seller_id:
            continue
        if seller_id not in earliest_limit_by_seller:
            seller_order.append(seller_id)
            if shipping_limit:
                earliest_limit_by_seller[seller_id] = shipping_limit
        elif shipping_limit and shipping_limit < earliest_limit_by_seller[seller_id]:
            earliest_limit_by_seller[seller_id] = shipping_limit

    seller_handoff_analysis: list[dict] = []
    late_handoff_seller_ids: list[str] = []

    for seller_id in seller_order:
        shipping_limit = earliest_limit_by_seller.get(seller_id)
        variance = repo.compute_handoff_variance(order, shipping_limit)
        late_handoff = variance is not None and variance > 0

        seller_handoff_analysis.append(
            {
                "seller_id": seller_id,
                "shipping_limit_at": shipping_limit,
                "handoff_variance_hours": variance,
                "late_handoff": late_handoff,
            }
        )
        if late_handoff:
            late_handoff_seller_ids.append(seller_id)

    return {
        "delivered_at": clean(order.get("order_delivered_customer_date")),
        "estimated_delivery_at": clean(order.get("order_estimated_delivery_date")),
        "carrier_handoff_at": clean(order.get("order_delivered_carrier_date")),
        "delivery_variance_hours": repo.compute_delivery_variance(order),
        "seller_handoff_analysis": seller_handoff_analysis,
        "late_handoff_seller_ids": late_handoff_seller_ids,
    }


def is_late_delivery(delivery_analysis: dict) -> bool:
    """Giao sau estimated date: cần có cả hai mốc và variance dương."""
    variance = delivery_analysis.get("delivery_variance_hours")
    return (
        delivery_analysis.get("delivered_at") is not None
        and delivery_analysis.get("estimated_delivery_at") is not None
        and variance is not None
        and variance > 0
    )


# ---------------------------------------------------------------------------
# Primary / secondary issue
# ---------------------------------------------------------------------------

def determine_primary_issue(
    order: dict,
    payments: list[dict],
    payment_reconciliation: dict,
    delivery_analysis: dict,
) -> tuple[str, str]:
    """
    Duyệt bảng EC_POLICY_V2 theo đúng thứ tự ưu tiên; trả về (primary_issue, lý do).
    Lý do được ghi vào trace để kiểm chứng lại quyết định sau này.
    """
    order_status = (order.get("order_status") or "").lower()
    payment_total = payment_reconciliation.get("payment_total_brl") or 0.0
    late_sellers = delivery_analysis.get("late_handoff_seller_ids", [])
    late = is_late_delivery(delivery_analysis)

    if order_status == "canceled" and payment_total > 0:
        return "canceled_order_paid", f"order_status=canceled và payment_total={payment_total} > 0"

    if order_status == "unavailable" and payment_total > 0:
        return "unavailable_order_paid", f"order_status=unavailable và payment_total={payment_total} > 0"

    if late and late_sellers:
        return (
            "late_delivery_seller",
            f"giao trễ {delivery_analysis['delivery_variance_hours']}h và {len(late_sellers)} seller bàn giao sau shipping_limit_date",
        )

    if late:
        return (
            "late_delivery_logistics",
            f"giao trễ {delivery_analysis['delivery_variance_hours']}h nhưng không seller nào bàn giao muộn",
        )

    if len(payments) >= 2 and payment_reconciliation.get("reconciled") is True:
        return (
            "valid_split_payment",
            f"{len(payments)} payment row và difference_brl={payment_reconciliation.get('difference_brl')} trong ngưỡng {RECONCILE_TOLERANCE_BRL}",
        )

    return "unsupported_late_claim", "đơn không giao trễ hơn estimated date và payment khớp"


def determine_secondary_issues(
    items: list[dict],
    payments: list[dict],
    related_order_ids: list[str],
    category_names: list[str],
) -> list[str]:
    """Secondary issues theo đúng thứ tự: item -> seller -> payment -> customer -> category."""
    unique_sellers = dedupe([i.get("seller_id") for i in items])
    unique_categories = dedupe(category_names)

    issues: list[str] = []
    if len(items) >= 2:
        issues.append("multi_item_order")
    if len(unique_sellers) >= 2:
        issues.append("multi_seller_order")
    if len(payments) >= 2:
        issues.append("split_payment")
    if related_order_ids:
        issues.append("repeat_customer")
    if len(unique_categories) >= 2:
        issues.append("multiple_categories")
    return issues


# ---------------------------------------------------------------------------
# Root cause / responsibility / refund / actions / evidence
# ---------------------------------------------------------------------------

def get_root_cause_code(primary_issue: str) -> str:
    return ROOT_CAUSE_MAP[primary_issue]


def build_ranked_causes(primary_issue: str) -> list[dict]:
    return limit([{"cause_code": get_root_cause_code(primary_issue), "rank": 1}], "ranked_causes")


def build_responsible_parties(primary_issue: str, late_handoff_seller_ids: list[str]) -> list[dict]:
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        return [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}]
    if primary_issue == "late_delivery_seller":
        parties = [{"party_type": "seller", "party_id": sid} for sid in late_handoff_seller_ids]
        return limit(parties, "responsible_parties")
    if primary_issue == "late_delivery_logistics":
        return [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}]
    return []


def compute_financial_resolution(primary_issue: str, payment_reconciliation: dict) -> dict:
    """
    canceled/unavailable -> hoàn toàn bộ payment đã thu.
    late_delivery_*      -> hoàn toàn bộ freight.
    còn lại              -> 0.
    """
    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        refund = payment_reconciliation.get("payment_total_brl") or 0.0
    elif primary_issue in ("late_delivery_seller", "late_delivery_logistics"):
        refund = payment_reconciliation.get("freight_total_brl") or 0.0
    else:
        refund = 0.0
    return {"currency": "BRL", "recommended_refund_brl": round(float(refund), 2)}


def build_resolution_actions(
    primary_issue: str,
    secondary_issues: list[str],
    payments: list[dict],
) -> list[str]:
    """
    Action chính trước, sau đó bổ sung đúng thứ tự:
    review_seller_handoff|review_carrier_delay -> verify_refund_completion
    -> coordinate_multi_seller_case -> verify_payment_allocation.
    """
    actions = [PRIMARY_ACTION_MAP[primary_issue]]

    if primary_issue == "late_delivery_seller":
        actions.append("review_seller_handoff")
    elif primary_issue == "late_delivery_logistics":
        actions.append("review_carrier_delay")

    if primary_issue in ("canceled_order_paid", "unavailable_order_paid"):
        actions.append("verify_refund_completion")

    if "multi_seller_order" in secondary_issues:
        actions.append("coordinate_multi_seller_case")

    # valid_split_payment: action chính đã giải thích split payment nên không thêm nữa
    if primary_issue != "valid_split_payment" and len(payments) >= 2:
        actions.append("verify_payment_allocation")

    return limit(actions, "resolution_actions")


def build_evidence_ids(
    order_id: str,
    items: list[dict],
    payments: list[dict],
    responsible_seller_ids: list[str],
    root_cause_code: str,
) -> list[str]:
    """
    Evidence gồm: order -> từng item -> từng payment -> seller chịu trách nhiệm -> policy.
    Chỉ dựng từ ID có thật trong CSV. Nếu vượt 20, cắt bớt item/payment ở giữa để
    luôn giữ được order, seller chịu trách nhiệm và policy (các bằng chứng kết luận).
    """
    head = [f"order:{order_id}"]
    tail = [f"seller:{sid}" for sid in responsible_seller_ids] + [f"policy:{root_cause_code}"]
    body = [f"item:{order_id}:{i.get('order_item_id')}" for i in items]
    body += [f"payment:{order_id}:{p.get('payment_sequential')}" for p in payments]

    budget = ARRAY_LIMITS["evidence_ids"] - len(head) - len(tail)
    return dedupe(head + body[: max(budget, 0)] + tail)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def compute_confidence(
    primary_issue: str,
    payment_reconciliation: dict,
    delivery_analysis: dict,
    items: list[dict],
    payments: list[dict],
) -> float:
    """
    Confidence phản ánh mức đầy đủ của bằng chứng, không phải số ngẫu nhiên:
      - 0.95 khi mọi mốc thời gian và số tiền cần cho kết luận đều có mặt.
      - Trừ điểm khi thiếu dữ liệu đối chứng (không có item/payment row, thiếu mốc
        bàn giao carrier, hoặc payment lệch ngoài ngưỡng đối soát).
    Luôn nằm trong [0, 1].
    """
    score = 0.95

    if not items:
        score -= 0.10
    if not payments:
        score -= 0.05
    if payment_reconciliation.get("reconciled") is False:
        score -= 0.05

    if primary_issue in ("late_delivery_seller", "late_delivery_logistics"):
        if delivery_analysis.get("carrier_handoff_at") is None:
            score -= 0.05
        if not delivery_analysis.get("seller_handoff_analysis"):
            score -= 0.05

    return round(min(max(score, 0.0), 1.0), 2)
