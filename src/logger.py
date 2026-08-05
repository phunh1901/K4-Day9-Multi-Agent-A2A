"""
logger.py — Thành viên B
Ghi vết truyền tin (A2A handoff traces) của các Agent vào file trace.jsonl
(Ghi đồng thời ở cả root trace.jsonl và logging/trace.jsonl để đảm bảo tương thích).
Mỗi dòng là một JSON object thể hiện một bước giao tiếp/handoff giữa 2 agent.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_TRACE_FILE = Path(__file__).parent.parent / "trace.jsonl"
LOGGING_TRACE_FILE = Path(__file__).parent.parent / "logging" / "trace.jsonl"


class TraceLogger:
    """Class ghi log trace A2A cho đợt chạy."""

    def __init__(self, reset: bool = True):
        self.trace_paths = [ROOT_TRACE_FILE, LOGGING_TRACE_FILE]

        for p in self.trace_paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            if reset and p.exists():
                p.unlink()

    def log_handoff(
        self,
        case_id: str,
        sender_agent: str,
        receiver_agent: str,
        action: str,
        message: str,
        payload_summary: dict[str, Any] | None = None,
        evidence_ids: list[str] | None = None,
    ) -> dict:
        """
        Ghi lại 1 sự kiện handoff giữa 2 Agent.
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "case_id": case_id,
            "sender_agent": sender_agent,
            "receiver_agent": receiver_agent,
            "action": action,
            "message": message,
            "payload_summary": payload_summary or {},
            "evidence_ids": evidence_ids or [],
        }

        line = json.dumps(record, ensure_ascii=False) + "\n"
        for p in self.trace_paths:
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)

        return record
