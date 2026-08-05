"""
data_engine.py — Đinh Quốc Việt (nhánh `viet`)
Lớp truy xuất dữ liệu Olist cho toàn bộ hệ Multi-Agent.

Nguyên tắc:
  - Nạp 9 CSV đúng một lần, dựng sẵn index dạng dict để mọi agent tra cứu O(1)
    thay vì quét lại DataFrame cho từng case (50 case x 6 agent = rất nhiều lượt quét).
  - Mọi giá trị trả về là dữ liệu thô có thể kiểm chứng trong CSV; module này
    không suy diễn nghiệp vụ, không tạo ra sự kiện mới.
  - Chuẩn hóa null một lần tại đây (chuỗi rỗng / "nan" / NaN -> None) để các
    agent phía sau không phải xử lý lại.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"

# Thứ tự item/payment trong mọi mảng output được chốt theo khóa số tự nhiên này
_ITEM_SORT_KEY = "order_item_id"
_PAYMENT_SORT_KEY = "payment_sequential"

_NULL_TOKENS = {"", "nan", "none", "nat", "null"}


# ---------------------------------------------------------------------------
# Chuẩn hóa giá trị thô
# ---------------------------------------------------------------------------

def clean(val: Any) -> Optional[str]:
    """Trả về chuỗi đã strip, hoặc None nếu giá trị rỗng/NaN."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    text = str(val).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    return text


def to_float(val: Any) -> Optional[float]:
    text = clean(val)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(val: Any, default: int = 0) -> int:
    text = clean(val)
    if text is None:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def parse_dt(val: Any) -> Optional[datetime]:
    """Parse timestamp CSV `YYYY-MM-DD HH:MM:SS`. So sánh nguyên trạng, không đổi timezone."""
    text = clean(val)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def hours_between(later: Optional[datetime], earlier: Optional[datetime]) -> Optional[float]:
    """later - earlier, đơn vị giờ, làm tròn 2 chữ số. None nếu thiếu một trong hai mốc."""
    if later is None or earlier is None:
        return None
    return round((later - earlier).total_seconds() / 3600, 2)


# ---------------------------------------------------------------------------
# Repository: nạp CSV + dựng index
# ---------------------------------------------------------------------------

class OlistRepository:
    """Kho dữ liệu Olist đã index sẵn theo các khóa join của đề bài."""

    FILES = {
        "orders": "olist_orders_dataset.csv",
        "customers": "olist_customers_dataset.csv",
        "order_items": "olist_order_items_dataset.csv",
        "order_payments": "olist_order_payments_dataset.csv",
        "order_reviews": "olist_order_reviews_dataset.csv",
        "products": "olist_products_dataset.csv",
        "sellers": "olist_sellers_dataset.csv",
        "geolocation": "olist_geolocation_dataset.csv",
        "category_translation": "product_category_name_translation.csv",
    }

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self._frames: dict[str, pd.DataFrame] = {}
        self._built = False

    # -- nạp CSV -----------------------------------------------------------
    def frame(self, name: str) -> pd.DataFrame:
        if name not in self._frames:
            self._frames[name] = pd.read_csv(
                self.data_dir / self.FILES[name], dtype=str, low_memory=False
            )
        return self._frames[name]

    # -- dựng index --------------------------------------------------------
    def build(self) -> "OlistRepository":
        if self._built:
            return self

        orders_df = self.frame("orders")
        self.orders_by_id: dict[str, dict] = {
            rec["order_id"]: {k: clean(v) for k, v in rec.items()}
            for rec in orders_df.to_dict("records")
        }

        customers_df = self.frame("customers")
        self.customers_by_id: dict[str, dict] = {}
        customer_ids_by_unique: dict[str, set[str]] = {}
        for rec in customers_df.to_dict("records"):
            row = {k: clean(v) for k, v in rec.items()}
            self.customers_by_id[row["customer_id"]] = row
            customer_ids_by_unique.setdefault(row["customer_unique_id"], set()).add(row["customer_id"])
        self._customer_ids_by_unique = customer_ids_by_unique

        # order_id theo customer_unique_id, giữ nguyên thứ tự dòng trong orders CSV
        self.orders_by_customer_unique: dict[str, list[str]] = {}
        unique_by_customer_id = {
            cid: row["customer_unique_id"] for cid, row in self.customers_by_id.items()
        }
        for order_id, row in self.orders_by_id.items():
            unique_id = unique_by_customer_id.get(row.get("customer_id"))
            if unique_id:
                self.orders_by_customer_unique.setdefault(unique_id, []).append(order_id)

        self.items_by_order: dict[str, list[dict]] = {}
        for rec in self.frame("order_items").to_dict("records"):
            row = {k: clean(v) for k, v in rec.items()}
            self.items_by_order.setdefault(row["order_id"], []).append(row)
        for rows in self.items_by_order.values():
            rows.sort(key=lambda r: to_int(r.get(_ITEM_SORT_KEY)))

        self.payments_by_order: dict[str, list[dict]] = {}
        for rec in self.frame("order_payments").to_dict("records"):
            row = {k: clean(v) for k, v in rec.items()}
            self.payments_by_order.setdefault(row["order_id"], []).append(row)
        for rows in self.payments_by_order.values():
            rows.sort(key=lambda r: to_int(r.get(_PAYMENT_SORT_KEY)))

        self.products_by_id: dict[str, dict] = {
            rec["product_id"]: {k: clean(v) for k, v in rec.items()}
            for rec in self.frame("products").to_dict("records")
        }

        self.seller_ids: set[str] = {
            clean(rec["seller_id"]) for rec in self.frame("sellers").to_dict("records")
        }

        self.category_en: dict[str, str] = {
            clean(rec["product_category_name"]): clean(rec["product_category_name_english"])
            for rec in self.frame("category_translation").to_dict("records")
        }

        self._built = True
        return self

    # -- truy vấn ----------------------------------------------------------
    def get_order(self, order_id: Optional[str]) -> Optional[dict]:
        if not order_id:
            return None
        return self.orders_by_id.get(order_id)

    def get_order_items(self, order_id: Optional[str]) -> list[dict]:
        return list(self.items_by_order.get(order_id or "", []))

    def get_order_payments(self, order_id: Optional[str]) -> list[dict]:
        return list(self.payments_by_order.get(order_id or "", []))

    def get_customer(self, customer_id: Optional[str]) -> Optional[dict]:
        if not customer_id:
            return None
        return self.customers_by_id.get(customer_id)

    def get_customer_order_ids(self, customer_unique_id: Optional[str]) -> list[str]:
        if not customer_unique_id:
            return []
        return list(self.orders_by_customer_unique.get(customer_unique_id, []))

    def get_product(self, product_id: Optional[str]) -> Optional[dict]:
        if not product_id:
            return None
        return self.products_by_id.get(product_id)

    def get_category_name(self, product_id: Optional[str]) -> Optional[str]:
        """
        Trả về `product_category_name` nguyên trạng trong products CSV.

        Quyết định: KHÔNG dịch sang tiếng Anh. Đề bài chỉ liệt kê các khóa join tới
        products/sellers/payments và yêu cầu "array giữ thứ tự ổn định theo dữ liệu
        nguồn"; không có bước dịch category nào được mô tả trong EC_POLICY_V2, nên
        giá trị kiểm chứng được trực tiếp từ CSV là tên gốc (tiếng Bồ Đào Nha).
        """
        product = self.get_product(product_id)
        if not product:
            return None
        return product.get("product_category_name")

    def seller_exists(self, seller_id: Optional[str]) -> bool:
        return bool(seller_id) and seller_id in self.seller_ids

    # -- tính toán chỉ số ---------------------------------------------------
    def compute_delivery_variance(self, order: dict) -> Optional[float]:
        """delivery_variance_hours = order_delivered_customer_date - order_estimated_delivery_date"""
        return hours_between(
            parse_dt(order.get("order_delivered_customer_date")),
            parse_dt(order.get("order_estimated_delivery_date")),
        )

    def compute_handoff_variance(self, order: dict, shipping_limit_at: Optional[str]) -> Optional[float]:
        """handoff_variance_hours = order_delivered_carrier_date - shipping_limit_date"""
        return hours_between(
            parse_dt(order.get("order_delivered_carrier_date")),
            parse_dt(shipping_limit_at),
        )

    def compute_payment_reconciliation(self, items: list[dict], payments: list[dict]) -> dict:
        """
        expected_total_brl = sum(price) + sum(freight_value)
        difference_brl     = sum(payment_value) - expected_total_brl
        reconciled         = abs(difference_brl) <= 0.10

        Order không có item row: expected/difference/reconciled = null (theo đề bài).
        """
        payment_total = round(sum(to_float(p.get("payment_value")) or 0.0 for p in payments), 2)
        payment_types: list[str] = []
        for p in payments:
            ptype = p.get("payment_type")
            if ptype and ptype not in payment_types:
                payment_types.append(ptype)

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

        item_total = round(sum(to_float(i.get("price")) or 0.0 for i in items), 2)
        freight_total = round(sum(to_float(i.get("freight_value")) or 0.0 for i in items), 2)
        expected_total = round(item_total + freight_total, 2)
        difference = round(payment_total - expected_total, 2)

        return {
            "currency": "BRL",
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "expected_total_brl": expected_total,
            "payment_total_brl": payment_total,
            "difference_brl": difference,
            "reconciled": abs(difference) <= 0.10,
            "payment_types": payment_types,
        }


# ---------------------------------------------------------------------------
# Singleton dùng chung cho mọi agent
# ---------------------------------------------------------------------------

REPO = OlistRepository()


def get_repository() -> OlistRepository:
    return REPO.build()
