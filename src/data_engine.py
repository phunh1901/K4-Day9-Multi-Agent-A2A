"""
data_engine.py — Thành viên A
Nạp và truy xuất dữ liệu từ 9 file CSV của Olist.
Cung cấp tất cả các helper function mà các Agent cần để lấy dữ liệu
theo order_id, tính toán chỉ số giờ/tiền và xử lý null chuẩn.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Nạp dữ liệu toàn bộ một lần khi import module (singleton in-memory)
# ---------------------------------------------------------------------------
_df_cache: dict[str, pd.DataFrame] = {}


def _load(name: str) -> pd.DataFrame:
    if name not in _df_cache:
        path = DATA_DIR / name
        _df_cache[name] = pd.read_csv(path, dtype=str, low_memory=False)
    return _df_cache[name]


def orders() -> pd.DataFrame:
    return _load("olist_orders_dataset.csv")


def customers() -> pd.DataFrame:
    return _load("olist_customers_dataset.csv")


def order_items() -> pd.DataFrame:
    return _load("olist_order_items_dataset.csv")


def order_payments() -> pd.DataFrame:
    return _load("olist_order_payments_dataset.csv")


def order_reviews() -> pd.DataFrame:
    return _load("olist_order_reviews_dataset.csv")


def products() -> pd.DataFrame:
    return _load("olist_products_dataset.csv")


def sellers() -> pd.DataFrame:
    return _load("olist_sellers_dataset.csv")


def geolocation() -> pd.DataFrame:
    return _load("olist_geolocation_dataset.csv")


def category_translation() -> pd.DataFrame:
    return _load("product_category_name_translation.csv")


# ---------------------------------------------------------------------------
# Helpers dùng order_id
# ---------------------------------------------------------------------------

def get_order(order_id: str) -> Optional[dict]:
    """Trả về dòng order (dict) hoặc None nếu không tìm thấy."""
    df = orders()
    row = df[df["order_id"] == order_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def get_order_items(order_id: str) -> list[dict]:
    """Trả về danh sách item rows theo order_id."""
    df = order_items()
    rows = df[df["order_id"] == order_id]
    return rows.to_dict("records")


def get_order_payments(order_id: str) -> list[dict]:
    """Trả về danh sách payment rows theo order_id."""
    df = order_payments()
    rows = df[df["order_id"] == order_id]
    return rows.to_dict("records")


def get_product(product_id: str) -> Optional[dict]:
    df = products()
    row = df[df["product_id"] == product_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def get_category_name_en(category_name_pt: str) -> str:
    """Dịch category sang tiếng Anh; nếu không có trả về giá trị gốc."""
    df = category_translation()
    row = df[df["product_category_name"] == category_name_pt]
    if row.empty:
        return category_name_pt
    return row.iloc[0].get("product_category_name_english", category_name_pt)


def get_customer(customer_id: str) -> Optional[dict]:
    df = customers()
    row = df[df["customer_id"] == customer_id]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def get_customer_orders(customer_unique_id: str) -> list[str]:
    """Trả về list order_id của cùng customer_unique_id (trừ order đang xét)."""
    cust_df = customers()
    ord_df = orders()
    cust_ids = cust_df[cust_df["customer_unique_id"] == customer_unique_id]["customer_id"].tolist()
    related = ord_df[ord_df["customer_id"].isin(cust_ids)]["order_id"].tolist()
    return related


# ---------------------------------------------------------------------------
# Tính toán chỉ số — Làm tròn 2 chữ số thập phân
# ---------------------------------------------------------------------------

def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val or str(val).strip().lower() in ("", "nan", "none", "nat"):
        return None
    try:
        return datetime.fromisoformat(str(val).strip())
    except ValueError:
        return None


def _hours_between(dt_a: Optional[datetime], dt_b: Optional[datetime]) -> Optional[float]:
    """dt_a - dt_b, tính bằng giờ, làm tròn 2 chữ số thập phân."""
    if dt_a is None or dt_b is None:
        return None
    delta = dt_a - dt_b
    return round(delta.total_seconds() / 3600, 2)


def compute_delivery_variance(order: dict) -> Optional[float]:
    """delivery_variance_hours = delivered_at - estimated_delivery_at"""
    return _hours_between(
        _parse_dt(order.get("order_delivered_customer_date")),
        _parse_dt(order.get("order_estimated_delivery_date")),
    )


def compute_handoff_variance(order: dict, item: dict) -> Optional[float]:
    """handoff_variance_hours = carrier_handoff_at - shipping_limit_date (của item)"""
    return _hours_between(
        _parse_dt(order.get("order_delivered_carrier_date")),
        _parse_dt(item.get("shipping_limit_date")),
    )


def compute_payment_reconciliation(items: list[dict], payments: list[dict]) -> dict:
    """
    Tính toán đối soát thanh toán.
    Trả về dict với: item_total_brl, freight_total_brl, expected_total_brl,
    payment_total_brl, difference_brl, reconciled, payment_types.
    Nếu items rỗng, trả về null cho expected_total_brl, difference_brl, reconciled.
    """
    try:
        item_total = round(sum(float(i.get("price", 0) or 0) for i in items), 2)
        freight_total = round(sum(float(i.get("freight_value", 0) or 0) for i in items), 2)
    except (ValueError, TypeError):
        item_total = None
        freight_total = None

    payment_total = round(sum(float(p.get("payment_value", 0) or 0) for p in payments), 2) if payments else 0.0
    payment_types = list(dict.fromkeys(p.get("payment_type", "") for p in payments if p.get("payment_type")))

    if not items:
        return {
            "currency": "BRL",
            "item_total_brl": None,
            "freight_total_brl": None,
            "expected_total_brl": None,
            "payment_total_brl": payment_total,
            "difference_brl": None,
            "reconciled": None,
            "payment_types": payment_types,
        }

    expected = round(item_total + freight_total, 2)
    difference = round(payment_total - expected, 2)
    reconciled = abs(difference) <= 0.10

    return {
        "currency": "BRL",
        "item_total_brl": item_total,
        "freight_total_brl": freight_total,
        "expected_total_brl": expected,
        "payment_total_brl": payment_total,
        "difference_brl": difference,
        "reconciled": reconciled,
        "payment_types": payment_types,
    }
