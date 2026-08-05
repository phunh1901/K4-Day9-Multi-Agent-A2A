"""
tests/test_policy_engine.py — Đinh Quốc Việt (nhánh `viet`)
Bộ test luật EC_POLICY_V2 trên dữ liệu dựng sẵn (không cần CSV, không cần mạng).
Mục tiêu: chốt các nhánh quyết định dễ sai — thứ tự ưu tiên primary issue, xử lý
null khi order không có item, và mốc shipping_limit_date sớm nhất theo từng seller.

Chạy:  python tests/test_policy_engine.py     (không cần pytest)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_engine import OlistRepository  # noqa: E402
from src.policy_engine import (  # noqa: E402
    build_delivery_analysis,
    build_evidence_ids,
    build_resolution_actions,
    build_responsible_parties,
    compute_financial_resolution,
    determine_primary_issue,
    determine_secondary_issues,
)

REPO = OlistRepository()  # chỉ dùng các hàm tính toán, không nạp CSV

ORDER_ID = "o1"
SELLER_A = "sellerA"
SELLER_B = "sellerB"


def make_order(**kwargs) -> dict:
    order = {
        "order_id": ORDER_ID,
        "order_status": "delivered",
        "order_delivered_customer_date": "2018-03-31 15:23:33",
        "order_estimated_delivery_date": "2018-03-28 00:00:00",
        "order_delivered_carrier_date": "2018-03-15 21:33:51",
    }
    order.update(kwargs)
    return order


def make_item(seller_id=SELLER_A, item_id="1", limit="2018-03-15 20:31:15", price="100.00",
              freight="10.00", product_id="p1") -> dict:
    return {
        "order_id": ORDER_ID,
        "order_item_id": item_id,
        "product_id": product_id,
        "seller_id": seller_id,
        "shipping_limit_date": limit,
        "price": price,
        "freight_value": freight,
    }


def make_payment(seq="1", value="110.00", ptype="credit_card") -> dict:
    return {"order_id": ORDER_ID, "payment_sequential": seq,
            "payment_type": ptype, "payment_value": value}


CHECKS: list[tuple[str, bool]] = []


def expect(name: str, condition: bool) -> None:
    CHECKS.append((name, bool(condition)))


# --- 1. Thứ tự ưu tiên primary issue --------------------------------------
def test_priority_order() -> None:
    items = [make_item()]
    payments = [make_payment()]
    delivery = build_delivery_analysis(make_order(), items, REPO)
    recon = REPO.compute_payment_reconciliation(items, payments)

    # canceled + đã thu tiền phải thắng cả nhánh giao trễ
    canceled = make_order(order_status="canceled")
    issue, _ = determine_primary_issue(canceled, payments, recon, delivery)
    expect("canceled_order_paid ưu tiên cao nhất", issue == "canceled_order_paid")

    # canceled nhưng chưa thu tiền -> rơi xuống nhánh giao hàng
    empty_recon = REPO.compute_payment_reconciliation(items, [])
    issue, _ = determine_primary_issue(canceled, [], empty_recon, delivery)
    expect("canceled + payment 0 không phải canceled_order_paid", issue == "late_delivery_seller")

    issue, _ = determine_primary_issue(
        make_order(order_status="unavailable"), payments, recon, delivery
    )
    expect("unavailable_order_paid", issue == "unavailable_order_paid")


# --- 2. Trách nhiệm giao trễ: seller vs logistics --------------------------
def test_late_delivery_split() -> None:
    payments = [make_payment()]

    late_seller_items = [make_item(limit="2018-03-15 20:31:15")]  # carrier nhận sau limit
    delivery = build_delivery_analysis(make_order(), late_seller_items, REPO)
    recon = REPO.compute_payment_reconciliation(late_seller_items, payments)
    issue, _ = determine_primary_issue(make_order(), payments, recon, delivery)
    expect("giao trễ + seller bàn giao muộn -> seller", issue == "late_delivery_seller")
    expect("handoff_variance dương và làm tròn 2 số",
           delivery["seller_handoff_analysis"][0]["handoff_variance_hours"] == 1.04)
    expect("responsible = seller vi phạm",
           build_responsible_parties(issue, delivery["late_handoff_seller_ids"])
           == [{"party_type": "seller", "party_id": SELLER_A}])

    on_time_items = [make_item(limit="2018-03-20 00:00:00")]  # carrier nhận trước limit
    delivery = build_delivery_analysis(make_order(), on_time_items, REPO)
    issue, _ = determine_primary_issue(make_order(), payments, recon, delivery)
    expect("giao trễ + seller đúng hạn -> logistics", issue == "late_delivery_logistics")
    expect("responsible = logistics_provider",
           build_responsible_parties(issue, [])[0]["party_id"] == "LOGISTICS_PROVIDER")


# --- 3. shipping_limit_date sớm nhất theo từng seller ---------------------
def test_earliest_shipping_limit_per_seller() -> None:
    items = [
        make_item(seller_id=SELLER_A, item_id="1", limit="2018-03-20 00:00:00"),
        make_item(seller_id=SELLER_A, item_id="2", limit="2018-03-10 00:00:00"),
        make_item(seller_id=SELLER_B, item_id="3", limit="2018-03-25 00:00:00"),
    ]
    delivery = build_delivery_analysis(make_order(), items, REPO)
    analysis = {h["seller_id"]: h for h in delivery["seller_handoff_analysis"]}

    expect("mỗi seller đúng một dòng", len(delivery["seller_handoff_analysis"]) == 2)
    expect("lấy limit sớm nhất của seller A",
           analysis[SELLER_A]["shipping_limit_at"] == "2018-03-10 00:00:00")
    expect("seller A bị đánh dấu bàn giao muộn", analysis[SELLER_A]["late_handoff"] is True)
    expect("seller B đúng hạn", analysis[SELLER_B]["late_handoff"] is False)
    expect("late_handoff_seller_ids chỉ gồm seller vi phạm",
           delivery["late_handoff_seller_ids"] == [SELLER_A])


# --- 4. Đối soát thanh toán và null handling ------------------------------
def test_reconciliation() -> None:
    items = [make_item(price="194.00", freight="18.27")]
    recon = REPO.compute_payment_reconciliation(items, [make_payment(value="212.27")])
    expect("expected_total = item + freight", recon["expected_total_brl"] == 212.27)
    expect("difference 0 -> reconciled", recon["reconciled"] is True)

    off = REPO.compute_payment_reconciliation(items, [make_payment(value="212.40")])
    expect("lệch 0.13 BRL vượt ngưỡng 0.10", off["reconciled"] is False)
    edge = REPO.compute_payment_reconciliation(items, [make_payment(value="212.37")])
    expect("lệch đúng 0.10 BRL vẫn khớp", edge["reconciled"] is True)

    empty = REPO.compute_payment_reconciliation([], [make_payment(value="18.37")])
    expect("order không item -> expected null", empty["expected_total_brl"] is None)
    expect("order không item -> difference null", empty["difference_brl"] is None)
    expect("order không item -> reconciled null", empty["reconciled"] is None)
    expect("payment_total vẫn được tính", empty["payment_total_brl"] == 18.37)

    delivery = build_delivery_analysis(make_order(), [], REPO)
    expect("order không item -> seller_handoff rỗng", delivery["seller_handoff_analysis"] == [])


# --- 5. valid_split_payment và unsupported_late_claim ---------------------
def test_no_action_branches() -> None:
    on_time = make_order(order_delivered_customer_date="2018-03-20 10:00:00")
    items = [make_item(price="100.00", freight="10.00")]
    delivery = build_delivery_analysis(on_time, items, REPO)

    two_pay = [make_payment(seq="1", value="60.00"), make_payment(seq="2", value="50.00", ptype="voucher")]
    recon = REPO.compute_payment_reconciliation(items, two_pay)
    issue, _ = determine_primary_issue(on_time, two_pay, recon, delivery)
    expect("2 payment khớp + giao đúng hạn -> valid_split_payment", issue == "valid_split_payment")
    actions = build_resolution_actions(issue, ["split_payment"], two_pay)
    expect("valid_split_payment không kèm verify_payment_allocation",
           actions == ["explain_valid_split_payment"])

    one_pay = [make_payment(value="110.00")]
    recon = REPO.compute_payment_reconciliation(items, one_pay)
    issue, _ = determine_primary_issue(on_time, one_pay, recon, delivery)
    expect("giao đúng hạn + payment khớp -> unsupported_late_claim",
           issue == "unsupported_late_claim")
    expect("refund = 0", compute_financial_resolution(issue, recon)["recommended_refund_brl"] == 0.0)


# --- 6. Secondary issues, actions, evidence -------------------------------
def test_secondary_actions_evidence() -> None:
    items = [make_item(seller_id=SELLER_A, item_id="1", product_id="p1"),
             make_item(seller_id=SELLER_B, item_id="2", product_id="p2")]
    payments = [make_payment(seq="1"), make_payment(seq="2", ptype="voucher")]
    secondary = determine_secondary_issues(items, payments, ["o9"], ["cat1", "cat2"])
    expect("secondary đúng thứ tự và đủ 5 loại",
           secondary == ["multi_item_order", "multi_seller_order", "split_payment",
                         "repeat_customer", "multiple_categories"])

    actions = build_resolution_actions("late_delivery_seller", secondary, payments)
    expect("actions đúng thứ tự bổ sung",
           actions == ["refund_freight", "review_seller_handoff",
                       "coordinate_multi_seller_case", "verify_payment_allocation"])

    evidence = build_evidence_ids(ORDER_ID, items, payments, [SELLER_A], "SELLER_HANDOFF_AFTER_LIMIT")
    expect("evidence đúng định dạng và thứ tự",
           evidence == [f"order:{ORDER_ID}", f"item:{ORDER_ID}:1", f"item:{ORDER_ID}:2",
                        f"payment:{ORDER_ID}:1", f"payment:{ORDER_ID}:2",
                        f"seller:{SELLER_A}", "policy:SELLER_HANDOFF_AFTER_LIMIT"])

    many_items = [make_item(item_id=str(i)) for i in range(1, 26)]
    capped = build_evidence_ids(ORDER_ID, many_items, payments, [SELLER_A], "SELLER_HANDOFF_AFTER_LIMIT")
    expect("evidence cắt về 20", len(capped) == 20)
    expect("vẫn giữ seller và policy khi cắt",
           capped[-1] == "policy:SELLER_HANDOFF_AFTER_LIMIT" and f"seller:{SELLER_A}" in capped)


def main() -> int:
    for test in (test_priority_order, test_late_delivery_split,
                 test_earliest_shipping_limit_per_seller, test_reconciliation,
                 test_no_action_branches, test_secondary_actions_evidence):
        test()

    failed = [name for name, ok in CHECKS if not ok]
    for name, ok in CHECKS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} assertion đạt")
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
