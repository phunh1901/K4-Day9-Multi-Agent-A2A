from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from provider import MODEL_NAME


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    input_dir: Path = Path("input")
    output_dir: Path = Path("output")
    trace_file: Path = Path("logging/trace.jsonl")
    metadata_file: Path = Path("logging/metadata.json")
    max_revisions: int = 2
    max_tool_rounds: int = 8
    model: str = MODEL_NAME

