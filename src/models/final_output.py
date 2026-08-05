from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class FinalCaseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    case_assessment: dict[str, Any]
    affected_entities: dict[str, Any]
    customer_context: dict[str, Any]
    product_context: dict[str, Any]
    delivery_analysis: dict[str, Any]
    payment_reconciliation: dict[str, Any]
    root_cause_analysis: dict[str, Any]
    evidence_ids: list[str] = Field(max_length=20)
    financial_resolution: dict[str, Any]
    resolution_actions: list[str] = Field(max_length=5)

    def validate_business_shape(self) -> list[str]:
        errors: list[str] = []
        assessment = self.case_assessment
        if assessment.get("case_status") not in {"action_required", "no_action"}:
            errors.append("invalid case_status")
        confidence = assessment.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append("confidence must be in [0, 1]")
        limits = {
            "order_ids": (self.affected_entities.get("order_ids", []), 5),
            "item_ids": (self.affected_entities.get("item_ids", []), 5),
            "seller_ids": (self.affected_entities.get("seller_ids", []), 3),
            "payment_ids": (self.affected_entities.get("payment_ids", []), 5),
            "related_order_ids": (self.customer_context.get("related_order_ids", []), 5),
            "product_ids": (self.product_context.get("product_ids", []), 5),
            "category_names": (self.product_context.get("category_names", []), 5),
        }
        for name, (values, limit) in limits.items():
            if len(values) > limit:
                errors.append(f"{name} exceeds limit {limit}")
        if set(self.affected_entities.get("order_ids", [])) & set(self.customer_context.get("related_order_ids", [])):
            errors.append("historical order leaked into affected_entities")
        return errors
