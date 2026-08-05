from __future__ import annotations

from typing import Any, Callable

from .calculation_tools import (
    add_money, compare_money_with_tolerance, hours_between, subtract_money, sum_money,
)
from .datastore import DataStore


Tool = Callable[..., Any]


def _ok(tool: str, query: dict[str, Any], records: Any, **extra: Any) -> dict[str, Any]:
    result = {"status": "success", "tool": tool, "query": query, "records": records}
    if isinstance(records, list):
        result["record_count"] = len(records)
    result.update(extra)
    return result


def _fail(tool: str, query: dict[str, Any], error: str) -> dict[str, Any]:
    return {"status": "error", "tool": tool, "query": query, "error": error}


class ToolRegistry:
    """A name-to-callable registry used to enforce per-agent tool permissions."""

    def __init__(self, store: DataStore):
        self.store = store
        self.functions: dict[str, Tool] = {
            "get_order_customer": self.get_order_customer,
            "get_customer": self.get_customer,
            "get_orders_by_unique_customer": self.get_orders_by_unique_customer,
            "get_order": self.get_order,
            "get_order_items": self.get_order_items,
            "get_product": self.get_product,
            "get_seller": self.get_seller,
            "get_order_payments": self.get_order_payments,
            "get_order_delivery_timestamps": self.get_order_delivery_timestamps,
            "sum_money": lambda values: sum_money(values),
            "add_money": lambda a, b: add_money(a, b),
            "subtract_money": lambda a, b: subtract_money(a, b),
            "compare_money_with_tolerance": lambda a, b, tolerance="0.10": compare_money_with_tolerance(a, b, tolerance),
            "hours_between": lambda timestamp_a, timestamp_b: hours_between(timestamp_a, timestamp_b),
            "lookup_evidence_id": self.lookup_evidence_id,
            "validate_array_limits": self.validate_array_limits,
        }

    def _arg(self, value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value

    def get_order_customer(self, order_id: str) -> dict[str, Any]:
        order_id = self._arg(order_id, "order_id")
        order = self.store.order(order_id)
        if not order:
            return _fail("get_order_customer", {"order_id": order_id}, "order not found")
        return _ok("get_order_customer", {"order_id": order_id}, {"customer_id": order["customer_id"]})

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        customer_id = self._arg(customer_id, "customer_id")
        row = self.store.customer(customer_id)
        return _ok("get_customer", {"customer_id": customer_id}, row) if row else _fail("get_customer", {"customer_id": customer_id}, "customer not found")

    def get_orders_by_unique_customer(self, customer_unique_id: str) -> dict[str, Any]:
        customer_unique_id = self._arg(customer_unique_id, "customer_unique_id")
        return _ok("get_orders_by_unique_customer", {"customer_unique_id": customer_unique_id}, self.store.customer_orders(customer_unique_id))

    def get_order(self, order_id: str) -> dict[str, Any]:
        order_id = self._arg(order_id, "order_id")
        row = self.store.order(order_id)
        return _ok("get_order", {"order_id": order_id}, row) if row else _fail("get_order", {"order_id": order_id}, "order not found")

    def get_order_items(self, order_id: str) -> dict[str, Any]:
        order_id = self._arg(order_id, "order_id")
        return _ok("get_order_items", {"order_id": order_id}, self.store.items_for(order_id))

    def get_product(self, product_id: str) -> dict[str, Any]:
        product_id = self._arg(product_id, "product_id")
        row = self.store.product(product_id)
        if not row:
            return _fail("get_product", {"product_id": product_id}, "product not found")
        row["product_category_name_english"] = self.store.translated_category(row.get("product_category_name"))
        return _ok("get_product", {"product_id": product_id}, row)

    def get_seller(self, seller_id: str) -> dict[str, Any]:
        seller_id = self._arg(seller_id, "seller_id")
        row = self.store.seller(seller_id)
        return _ok("get_seller", {"seller_id": seller_id}, row) if row else _fail("get_seller", {"seller_id": seller_id}, "seller not found")

    def get_order_payments(self, order_id: str) -> dict[str, Any]:
        order_id = self._arg(order_id, "order_id")
        return _ok("get_order_payments", {"order_id": order_id}, self.store.payments_for(order_id))

    def get_order_delivery_timestamps(self, order_id: str) -> dict[str, Any]:
        order_id = self._arg(order_id, "order_id")
        row = self.store.order(order_id)
        if not row:
            return _fail("get_order_delivery_timestamps", {"order_id": order_id}, "order not found")
        fields = {
            "delivered_at": row.get("order_delivered_customer_date") or None,
            "estimated_delivery_at": row.get("order_estimated_delivery_date") or None,
            "carrier_handoff_at": row.get("order_delivered_carrier_date") or None,
        }
        return _ok("get_order_delivery_timestamps", {"order_id": order_id}, fields)

    def lookup_evidence_id(self, evidence_id: str) -> dict[str, Any]:
        if not isinstance(evidence_id, str):
            return _fail("lookup_evidence_id", {}, "evidence_id must be a string")
        return _ok("lookup_evidence_id", {"evidence_id": evidence_id}, {"exists": self.store.evidence_exists(evidence_id)})

    def validate_array_limits(self, candidate: dict[str, Any]) -> dict[str, Any]:
        limits = {"order_ids": 5, "item_ids": 5, "seller_ids": 3, "payment_ids": 5, "related_order_ids": 5, "product_ids": 5, "category_names": 5, "evidence_ids": 20, "resolution_actions": 5}
        failures = []
        for key, limit in limits.items():
            values = candidate.get(key) or candidate.get("affected_entities", {}).get(key) or candidate.get("customer_context", {}).get(key) or candidate.get("product_context", {}).get(key) or []
            if len(values) > limit:
                failures.append({"field": key, "limit": limit, "actual": len(values)})
        return {"status": "success", "tool": "validate_array_limits", "failures": failures, "valid": not failures}

    def schemas_for(self, names: list[str]) -> list[dict[str, Any]]:
        schemas: dict[str, dict[str, Any]] = {
            "get_order_customer": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
            "get_customer": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]},
            "get_orders_by_unique_customer": {"type": "object", "properties": {"customer_unique_id": {"type": "string"}}, "required": ["customer_unique_id"]},
            "get_order": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
            "get_order_items": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
            "get_product": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"]},
            "get_seller": {"type": "object", "properties": {"seller_id": {"type": "string"}}, "required": ["seller_id"]},
            "get_order_payments": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
            "get_order_delivery_timestamps": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
            "sum_money": {"type": "object", "properties": {"values": {"type": "array", "items": {"type": "number"}}}, "required": ["values"]},
            "add_money": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]},
            "subtract_money": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]},
            "compare_money_with_tolerance": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}, "tolerance": {"type": "number"}}, "required": ["a", "b"]},
            "hours_between": {"type": "object", "properties": {"timestamp_a": {"type": ["string", "null"]}, "timestamp_b": {"type": ["string", "null"]}}, "required": ["timestamp_a", "timestamp_b"]},
            "lookup_evidence_id": {"type": "object", "properties": {"evidence_id": {"type": "string"}}, "required": ["evidence_id"]},
            "validate_array_limits": {"type": "object", "properties": {"candidate": {"type": "object"}}, "required": ["candidate"]},
        }
        return [{"type": "function", "function": {"name": name, "description": f"Authorized tool {name}", "parameters": schemas[name]}} for name in names]
