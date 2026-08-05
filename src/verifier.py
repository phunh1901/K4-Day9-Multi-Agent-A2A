"""
verifier.py — Đinh Quốc Việt (nhánh `viet`)
Cổng kiểm soát cuối trước khi ghi file: output chỉ được ghi ra `output/` khi
không còn lỗi nào.

Kiểm tra 5 nhóm:
  1. Schema: đủ key bắt buộc, đúng kiểu, đúng tập giá trị hợp lệ.
  2. Giới hạn mảng và thứ tự nghiệp vụ (secondary issues, resolution actions).
  3. Grounding: mọi ID trong output phải tồn tại thật trong CSV (chống false positive).
  4. Null handling: order không có item row thì expected/difference/reconciled = null.
  5. Nhất quán nghiệp vụ: refund vs case_status, root cause vs primary issue,
     số tiền làm tròn 2 chữ số, timestamp đúng định dạng CSV.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from src.data_engine import OlistRepository
from src.policy_engine import (
    ARRAY_LIMITS,
    PRIMARY_ACTION_MAP,
    ROOT_CAUSE_MAP,
    SECONDARY_ISSUES_ORDER,
)

VALID_PRIMARY_ISSUES = set(ROOT_CAUSE_MAP)
VALID_SECONDARY_ISSUES = set(SECONDARY_ISSUES_ORDER)
VALID_CASE_STATUS = {"action_required", "no_action"}
VALID_ROOT_CAUSES = set(ROOT_CAUSE_MAP.values())
VALID_PARTY_TYPES = {"platform", "seller", "logistics_provider"}
VALID_ACTIONS = set(PRIMARY_ACTION_MAP.values()) | {
    "review_seller_handoff",
    "review_carrier_delay",
    "verify_refund_completion",
    "coordinate_multi_seller_case",
    "verify_payment_allocation",
}

TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

REQUIRED_TOP_LEVEL = [
    "case_id",
    "case_assessment",
    "affected_entities",
    "customer_context",
    "product_context",
    "delivery_analysis",
    "payment_reconciliation",
    "root_cause_analysis",
    "evidence_ids",
    "financial_resolution",
    "resolution_actions",
]


def _is_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _rounded_ok(val: Any) -> bool:
    return not _is_number(val) or abs(round(float(val), 2) - float(val)) < 1e-9


def verify_output(result: dict, repo: Optional[OlistRepository] = None) -> list[str]:
    """Trả về danh sách lỗi; list rỗng nghĩa là output hợp lệ."""
    errors: list[str] = []

    def check(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    # --- 1. Schema --------------------------------------------------------
    for key in REQUIRED_TOP_LEVEL:
        check(key in result, f"thiếu key bắt buộc: {key}")
    if errors:
        return errors

    assessment = result["case_assessment"]
    primary = assessment.get("primary_issue")
    check(primary in VALID_PRIMARY_ISSUES, f"primary_issue không hợp lệ: {primary!r}")

    secondary = assessment.get("secondary_issues", [])
    check(isinstance(secondary, list), "secondary_issues phải là list")
    for issue in secondary:
        check(issue in VALID_SECONDARY_ISSUES, f"secondary_issue không hợp lệ: {issue!r}")
    ranks = [SECONDARY_ISSUES_ORDER.index(i) for i in secondary if i in VALID_SECONDARY_ISSUES]
    check(ranks == sorted(ranks), f"secondary_issues sai thứ tự nghiệp vụ: {secondary}")
    check(len(secondary) == len(set(secondary)), "secondary_issues bị lặp")

    check(assessment.get("case_status") in VALID_CASE_STATUS,
          f"case_status không hợp lệ: {assessment.get('case_status')!r}")
    confidence = assessment.get("confidence")
    check(_is_number(confidence) and 0.0 <= float(confidence) <= 1.0,
          f"confidence phải nằm trong [0,1], nhận {confidence!r}")

    # --- 2. Giới hạn mảng -------------------------------------------------
    entities = result["affected_entities"]
    for field in ("order_ids", "item_ids", "seller_ids", "payment_ids"):
        arr = entities.get(field, [])
        check(isinstance(arr, list), f"affected_entities.{field} phải là list")
        check(len(arr) <= ARRAY_LIMITS[field],
              f"affected_entities.{field} vượt giới hạn {ARRAY_LIMITS[field]} (có {len(arr)})")

    customer_ctx = result["customer_context"]
    product_ctx = result["product_context"]
    check(len(customer_ctx.get("related_order_ids", [])) <= ARRAY_LIMITS["related_order_ids"],
          "related_order_ids vượt giới hạn 5")
    check(len(product_ctx.get("product_ids", [])) <= ARRAY_LIMITS["product_ids"],
          "product_ids vượt giới hạn 5")
    check(len(product_ctx.get("category_names", [])) <= ARRAY_LIMITS["category_names"],
          "category_names vượt giới hạn 5")

    evidence_ids = result["evidence_ids"]
    check(len(evidence_ids) <= ARRAY_LIMITS["evidence_ids"],
          f"evidence_ids vượt giới hạn 20 (có {len(evidence_ids)})")
    check(len(evidence_ids) == len(set(evidence_ids)), "evidence_ids bị lặp")

    actions = result["resolution_actions"]
    check(len(actions) <= ARRAY_LIMITS["resolution_actions"],
          f"resolution_actions vượt giới hạn 5 (có {len(actions)})")
    for action in actions:
        check(action in VALID_ACTIONS, f"action không hợp lệ: {action!r}")
    if actions and primary in PRIMARY_ACTION_MAP:
        check(actions[0] == PRIMARY_ACTION_MAP[primary],
              f"action đầu tiên phải là {PRIMARY_ACTION_MAP[primary]!r}, nhận {actions[0]!r}")
        check("verify_payment_allocation" not in actions or primary != "valid_split_payment",
              "không được thêm verify_payment_allocation khi primary là valid_split_payment")

    causes = result["root_cause_analysis"].get("ranked_causes", [])
    parties = result["root_cause_analysis"].get("responsible_parties", [])
    check(len(causes) <= ARRAY_LIMITS["ranked_causes"], "ranked_causes vượt giới hạn 3")
    check(len(parties) <= ARRAY_LIMITS["responsible_parties"], "responsible_parties vượt giới hạn 3")
    for cause in causes:
        check(cause.get("cause_code") in VALID_ROOT_CAUSES,
              f"cause_code không hợp lệ: {cause.get('cause_code')!r}")
    for party in parties:
        check(party.get("party_type") in VALID_PARTY_TYPES,
              f"party_type không hợp lệ: {party.get('party_type')!r}")
    if primary in ROOT_CAUSE_MAP and causes:
        check(causes[0]["cause_code"] == ROOT_CAUSE_MAP[primary],
              f"root cause không khớp primary_issue {primary!r}")

    # --- 3. Grounding: ID phải tồn tại trong CSV --------------------------
    delivery = result["delivery_analysis"]
    reconciliation = result["payment_reconciliation"]

    if repo is not None:
        order_ids = entities.get("order_ids", [])
        check(len(order_ids) == 1, f"phải có đúng 1 claimed order, nhận {len(order_ids)}")
        for order_id in order_ids:
            check(repo.get_order(order_id) is not None, f"order không tồn tại trong CSV: {order_id}")

        order_id = order_ids[0] if order_ids else ""
        real_items = repo.get_order_items(order_id)
        real_payments = repo.get_order_payments(order_id)
        real_item_ids = {f"{order_id}:{i.get('order_item_id')}" for i in real_items}
        real_payment_ids = {f"{order_id}:{p.get('payment_sequential')}" for p in real_payments}
        real_seller_ids = {i.get("seller_id") for i in real_items}
        real_product_ids = {i.get("product_id") for i in real_items}

        for item_id in entities.get("item_ids", []):
            check(item_id in real_item_ids, f"item_id không có trong CSV: {item_id}")
        for payment_id in entities.get("payment_ids", []):
            check(payment_id in real_payment_ids, f"payment_id không có trong CSV: {payment_id}")
        for seller_id in entities.get("seller_ids", []):
            check(seller_id in real_seller_ids and repo.seller_exists(seller_id),
                  f"seller_id không thuộc order/CSV: {seller_id}")
        for product_id in product_ctx.get("product_ids", []):
            check(product_id in real_product_ids, f"product_id không thuộc order: {product_id}")

        related = customer_ctx.get("related_order_ids", [])
        check(order_id not in related, "related_order_ids không được chứa chính claimed order")
        for related_id in related:
            check(repo.get_order(related_id) is not None,
                  f"related order không tồn tại trong CSV: {related_id}")

        # evidence phải dựng được từ dữ liệu thật
        for evidence in evidence_ids:
            if evidence.startswith("order:"):
                check(repo.get_order(evidence.split(":", 1)[1]) is not None,
                      f"evidence order sai: {evidence}")
            elif evidence.startswith("item:"):
                check(evidence[len("item:"):] in real_item_ids, f"evidence item sai: {evidence}")
            elif evidence.startswith("payment:"):
                check(evidence[len("payment:"):] in real_payment_ids,
                      f"evidence payment sai: {evidence}")
            elif evidence.startswith("seller:"):
                check(repo.seller_exists(evidence.split(":", 1)[1]), f"evidence seller sai: {evidence}")
            elif evidence.startswith("policy:"):
                check(evidence.split(":", 1)[1] in VALID_ROOT_CAUSES, f"evidence policy sai: {evidence}")
            else:
                errors.append(f"evidence sai định dạng: {evidence}")

        # --- 4. Null handling khi order không có item row -----------------
        if not real_items:
            for field in ("expected_total_brl", "difference_brl", "reconciled"):
                check(reconciliation.get(field) is None,
                      f"order không có item row thì {field} phải null")
            for field in ("item_total_brl", "freight_total_brl"):
                check(reconciliation.get(field) == 0.0,
                      f"order không có item row thì {field} phải là 0.0 (tổng tập rỗng), không phải null")
            check(entities.get("item_ids") == [], "order không có item row thì item_ids phải rỗng")
            check(entities.get("seller_ids") == [], "order không có item row thì seller_ids phải rỗng")
            check(product_ctx.get("product_ids") == [], "order không có item row thì product_ids phải rỗng")
            check(product_ctx.get("category_names") == [],
                  "order không có item row thì category_names phải rỗng")
            check(delivery.get("seller_handoff_analysis") == [],
                  "order không có item row thì seller_handoff_analysis phải rỗng")

    # --- 5. Nhất quán nghiệp vụ ------------------------------------------
    for field in ("delivered_at", "estimated_delivery_at", "carrier_handoff_at"):
        value = delivery.get(field)
        check(value is None or bool(TS_PATTERN.match(str(value))),
              f"delivery_analysis.{field} sai định dạng timestamp: {value!r}")
    for handoff in delivery.get("seller_handoff_analysis", []):
        limit_at = handoff.get("shipping_limit_at")
        check(limit_at is None or bool(TS_PATTERN.match(str(limit_at))),
              f"shipping_limit_at sai định dạng: {limit_at!r}")
        check(_rounded_ok(handoff.get("handoff_variance_hours")),
              "handoff_variance_hours phải làm tròn 2 chữ số")
        check(isinstance(handoff.get("late_handoff"), bool), "late_handoff phải là bool")
    check(_rounded_ok(delivery.get("delivery_variance_hours")),
          "delivery_variance_hours phải làm tròn 2 chữ số")

    late_ids = delivery.get("late_handoff_seller_ids", [])
    late_from_analysis = [h["seller_id"] for h in delivery.get("seller_handoff_analysis", [])
                          if h.get("late_handoff")]
    check(late_ids == late_from_analysis,
          "late_handoff_seller_ids không khớp seller_handoff_analysis")

    check(reconciliation.get("currency") == "BRL", "payment_reconciliation.currency phải là BRL")
    for field in ("item_total_brl", "freight_total_brl", "expected_total_brl",
                  "payment_total_brl", "difference_brl"):
        check(_rounded_ok(reconciliation.get(field)), f"{field} phải làm tròn 2 chữ số")

    refund = result["financial_resolution"].get("recommended_refund_brl")
    check(result["financial_resolution"].get("currency") == "BRL",
          "financial_resolution.currency phải là BRL")
    check(_is_number(refund) and refund >= 0, f"recommended_refund_brl không hợp lệ: {refund!r}")
    check(_rounded_ok(refund), "recommended_refund_brl phải làm tròn 2 chữ số")

    if _is_number(refund):
        expected_status = "action_required" if refund > 0 else "no_action"
        check(assessment.get("case_status") == expected_status,
              f"case_status phải là {expected_status!r} khi refund={refund}")

    return errors
