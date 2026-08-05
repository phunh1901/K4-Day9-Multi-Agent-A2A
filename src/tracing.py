from __future__ import annotations

import json
import time
from threading import Lock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceWriter:
    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.sequence = 0
        self._lock = Lock()
        self.path.write_text("", encoding="utf-8")

    def write(self, event_type: str, case_id: str | None = None, agent: str | None = None, **fields: Any) -> dict[str, Any]:
        with self._lock:
            self.sequence += 1
            event = {
                "run_id": self.run_id, "case_id": case_id, "sequence": self.sequence,
                "event_type": event_type, "agent": agent, "timestamp": datetime.now(timezone.utc).isoformat(),
                **fields,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event

    def timed(self) -> float:
        return time.perf_counter()
