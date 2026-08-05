from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VerificationDefect(BaseModel):
    code: str
    description: str
    responsible_agent: str
    required_action: str


class VerificationResult(BaseModel):
    agent: Literal["verifier"] = "verifier"
    case_id: str
    status: Literal["VERIFIED", "REVISION_REQUIRED"]
    defects: list[VerificationDefect] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
