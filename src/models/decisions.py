from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Justification(BaseModel):
    conclusion: str
    supporting_report: str
    supporting_path: str
    evidence_ids: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    agent: Literal["policy_adjudicator"] = "policy_adjudicator"
    case_id: str
    decision: dict[str, Any]
    final_output: dict[str, Any]
    root_cause_analysis: dict[str, Any] = Field(default_factory=dict)
    justification: list[Justification] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    open_questions: list[str] = Field(default_factory=list)
