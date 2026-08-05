"""
logger.py — Đinh Quốc Việt (nhánh `viet`)
Ghi vết giao thức A2A (Agent-to-Agent) ra `trace.jsonl`.

Mỗi dòng JSONL là một *message* trong hội thoại giữa hai agent, không phải log tự do:

    {run_id, seq, msg_id, parent_msg_id, timestamp, case_id,
     sender_agent, receiver_agent, msg_type, action, message,
     payload_summary, evidence_ids, latency_ms}

- `msg_type`: REQUEST (giao việc) | RESPONSE (bàn giao kết quả) | ERROR | EVENT.
- `parent_msg_id` nối RESPONSE về đúng REQUEST đã sinh ra nó, nhờ vậy trace có thể
  dựng lại thành cây handoff cho từng case.
- File luôn được ghi mới ở đầu mỗi lần chạy (không append chồng lượt cũ).
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT_DIR = Path(__file__).parent.parent
ROOT_TRACE_FILE = ROOT_DIR / "trace.jsonl"
LOGGING_TRACE_FILE = ROOT_DIR / "logging" / "trace.jsonl"

MSG_REQUEST = "REQUEST"
MSG_RESPONSE = "RESPONSE"
MSG_ERROR = "ERROR"
MSG_EVENT = "EVENT"


class TraceLogger:
    """Ghi các message A2A của một lượt chạy vào trace.jsonl (root và logging/)."""

    def __init__(self, reset: bool = True, run_id: Optional[str] = None):
        self.run_id = run_id or f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.trace_paths = [ROOT_TRACE_FILE, LOGGING_TRACE_FILE]
        self.seq = 0
        self.counts: dict[str, int] = {}

        for path in self.trace_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            if reset:
                path.write_text("", encoding="utf-8")

    # -- API chính ---------------------------------------------------------
    def log_message(
        self,
        case_id: str,
        sender_agent: str,
        receiver_agent: str,
        msg_type: str,
        action: str,
        message: str,
        payload_summary: Optional[dict[str, Any]] = None,
        evidence_ids: Optional[list[str]] = None,
        parent_msg_id: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> str:
        """Ghi một message A2A, trả về msg_id để agent nhận có thể tham chiếu ngược."""
        self.seq += 1
        msg_id = f"{self.run_id}-{self.seq:05d}-{uuid.uuid4().hex[:6]}"
        record = {
            "run_id": self.run_id,
            "seq": self.seq,
            "msg_id": msg_id,
            "parent_msg_id": parent_msg_id,
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "case_id": case_id,
            "sender_agent": sender_agent,
            "receiver_agent": receiver_agent,
            "msg_type": msg_type,
            "action": action,
            "message": message,
            "payload_summary": payload_summary or {},
            "evidence_ids": evidence_ids or [],
            "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        }
        self.counts[msg_type] = self.counts.get(msg_type, 0) + 1

        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        for path in self.trace_paths:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        return msg_id

    # -- tiện ích ----------------------------------------------------------
    def request(self, case_id, sender, receiver, action, message, payload=None, parent=None) -> str:
        return self.log_message(
            case_id, sender, receiver, MSG_REQUEST, action, message, payload, parent_msg_id=parent
        )

    def response(self, case_id, sender, receiver, action, message, payload=None,
                 evidence_ids=None, parent=None, latency_ms=None) -> str:
        return self.log_message(
            case_id, sender, receiver, MSG_RESPONSE, action, message, payload,
            evidence_ids=evidence_ids, parent_msg_id=parent, latency_ms=latency_ms,
        )

    def event(self, case_id, sender, receiver, action, message, payload=None, parent=None) -> str:
        return self.log_message(
            case_id, sender, receiver, MSG_EVENT, action, message, payload, parent_msg_id=parent
        )

    def error(self, case_id, sender, receiver, action, message, payload=None, parent=None) -> str:
        return self.log_message(
            case_id, sender, receiver, MSG_ERROR, action, message, payload, parent_msg_id=parent
        )

    # Giữ tương thích với tên gọi cũ trong repo nhóm
    def log_handoff(self, case_id, sender_agent, receiver_agent, action, message,
                    payload_summary=None, evidence_ids=None) -> str:
        return self.log_message(
            case_id, sender_agent, receiver_agent, MSG_RESPONSE, action, message,
            payload_summary, evidence_ids,
        )

    def summary(self) -> dict:
        return {"run_id": self.run_id, "total_messages": self.seq, "by_type": dict(self.counts)}


class Stopwatch:
    """Đo latency của một lượt handoff (ms)."""

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
        return False
