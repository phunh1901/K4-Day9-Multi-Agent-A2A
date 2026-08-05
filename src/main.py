from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.runtime import AgentRuntime
from src.config import Settings
from src.graph import run_case
from src.output_writer import write_output
from src.tools.datastore import DataStore
from src.tools.registry import ToolRegistry
from src.tracing import TraceWriter


def load_cases(input_dir: Path, case_id: str | None = None) -> list[dict[str, Any]]:
    paths = sorted(input_dir.glob("EC_*.json"))
    if case_id:
        paths = [input_dir / f"{case_id}.json"]
    if not paths:
        raise FileNotFoundError(f"no EC_*.json files found in {input_dir}")
    cases = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return cases


def run(settings: Settings, case_id: str | None = None, max_concurrency: int = 4, dry_run: bool = False) -> int:
    cases = load_cases(settings.input_dir, case_id)
    if dry_run:
        DataStore(settings.data_dir)
        print(f"dry-run: datastore loaded; {len(cases)} input case(s) validated for discovery")
        return 0
    store = DataStore(settings.data_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    trace = TraceWriter(settings.trace_file, run_id)
    runtime = AgentRuntime(ToolRegistry(store), trace, model=settings.model, max_tool_rounds=settings.max_tool_rounds)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for case in cases:
        state = run_case(runtime, case, max_revisions=settings.max_revisions, max_concurrency=max_concurrency)
        if state.get("final_output"):
            try:
                path = write_output(settings.output_dir, state["final_output"])
                trace.write("output_written", case["case_id"], "output_writer", path=str(path))
            except Exception as exc:
                failures += 1
                trace.write("case_failed", case["case_id"], "output_writer", error=str(exc))
        else:
            failures += 1
    print(json.dumps({"run_id": run_id, "cases": len(cases), "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


def cli(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run the multi-agent Olist dispute resolver")
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--trace-file", type=Path, default=Path("logging/trace.jsonl"))
    parser.add_argument("--metadata-file", type=Path, default=Path("logging/metadata.json"))
    parser.add_argument("--case-id")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings(data_dir=args.data_dir, input_dir=args.input_dir, output_dir=args.output_dir, trace_file=args.trace_file, metadata_file=args.metadata_file, max_revisions=args.max_revisions)
    try:
        return run(settings, args.case_id, args.max_concurrency, args.dry_run)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
