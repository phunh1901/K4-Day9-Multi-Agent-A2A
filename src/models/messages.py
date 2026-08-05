from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


MessageType = Literal[
    "task", "finding", "clarification_request", "clarification_response",
    "decision", "verification_result", "revision_request",
]


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg-{uuid4().hex}")
    case_id: str
    sender: str
    recipient: str
    message_type: MessageType
    objective: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    parent_message_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
