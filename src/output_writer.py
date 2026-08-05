from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models import FinalCaseOutput


def write_output(output_dir: Path, candidate: dict[str, Any]) -> Path:
    validated = FinalCaseOutput.model_validate(candidate)
    errors = validated.validate_business_shape()
    if errors:
        raise ValueError("; ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{validated.case_id}.json"
    path.write_text(json.dumps(validated.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
