from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportBase(BaseModel):
    agent: str
    case_id: str
    status: Literal["completed", "needs_clarification", "failed"]
    findings: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    open_questions: list[str] = Field(default_factory=list)


class CustomerReport(ReportBase):
    agent: Literal["customer_investigator"] = "customer_investigator"


class OrderProductReport(ReportBase):
    agent: Literal["order_product_investigator"] = "order_product_investigator"


class PaymentReport(ReportBase):
    agent: Literal["payment_auditor"] = "payment_auditor"


class DeliveryReport(ReportBase):
    agent: Literal["delivery_investigator"] = "delivery_investigator"
