from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class DataStore:
    """Load Olist once and expose indexed, stable-order source records."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.orders = _read_csv(self.data_dir / "olist_orders_dataset.csv")
        self.customers = _read_csv(self.data_dir / "olist_customers_dataset.csv")
        self.items = _read_csv(self.data_dir / "olist_order_items_dataset.csv")
        self.payments = _read_csv(self.data_dir / "olist_order_payments_dataset.csv")
        self.products = _read_csv(self.data_dir / "olist_products_dataset.csv")
        self.sellers = _read_csv(self.data_dir / "olist_sellers_dataset.csv")
        self.reviews = _read_csv(self.data_dir / "olist_order_reviews_dataset.csv")
        self.categories = _read_csv(self.data_dir / "product_category_name_translation.csv")

        self.orders_by_id = {row["order_id"]: row for row in self.orders}
        self.customers_by_id = {row["customer_id"]: row for row in self.customers}
        self.customers_by_unique: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.customers:
            self.customers_by_unique[row["customer_unique_id"]].append(row)
        self.items_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.items:
            self.items_by_order[row["order_id"]].append(row)
        self.payments_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in self.payments:
            self.payments_by_order[row["order_id"]].append(row)
        self.products_by_id = {row["product_id"]: row for row in self.products}
        self.sellers_by_id = {row["seller_id"]: row for row in self.sellers}
        self.category_translation = {
            row.get("product_category_name", ""): row.get("product_category_name_english", "")
            for row in self.categories
        }

    @staticmethod
    def _public(record: dict[str, str] | None) -> dict[str, str] | None:
        return dict(record) if record else None

    def order(self, order_id: str) -> dict[str, Any] | None:
        return self._public(self.orders_by_id.get(order_id))

    def customer(self, customer_id: str) -> dict[str, Any] | None:
        return self._public(self.customers_by_id.get(customer_id))

    def customer_orders(self, unique_id: str) -> list[dict[str, Any]]:
        customer_ids = {row["customer_id"] for row in self.customers_by_unique.get(unique_id, [])}
        return [dict(row) for row in self.orders if row["customer_id"] in customer_ids]

    def items_for(self, order_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.items_by_order.get(order_id, [])]

    def payments_for(self, order_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.payments_by_order.get(order_id, [])]

    def product(self, product_id: str) -> dict[str, Any] | None:
        return self._public(self.products_by_id.get(product_id))

    def seller(self, seller_id: str) -> dict[str, Any] | None:
        return self._public(self.sellers_by_id.get(seller_id))

    def translated_category(self, category: str | None) -> str | None:
        if not category:
            return None
        return self.category_translation.get(category) or category

    def evidence_exists(self, evidence_id: str) -> bool:
        parts = evidence_id.split(":")
        if parts[0] == "order" and len(parts) == 2:
            return parts[1] in self.orders_by_id
        if parts[0] == "item" and len(parts) == 3:
            return any(r["order_id"] == parts[1] and r["order_item_id"] == parts[2] for r in self.items)
        if parts[0] == "payment" and len(parts) == 3:
            return any(r["order_id"] == parts[1] and r["payment_sequential"] == parts[2] for r in self.payments)
        if parts[0] == "seller" and len(parts) == 2:
            return parts[1] in self.sellers_by_id
        if parts[0] == "policy" and len(parts) == 2:
            return parts[1] in {
                "SELLER_HANDOFF_AFTER_LIMIT", "CARRIER_DELIVERED_AFTER_ESTIMATE",
                "ORDER_CANCELED_AFTER_PAYMENT", "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                "MULTIPLE_PAYMENTS_RECONCILED", "DELIVERY_WITHIN_ESTIMATE",
            }
        return False
