"""
main.py — Thành viên B
Batch Pipeline Runner using the updated src architecture.
  - Đọc 50 file JSON trong input/
  - Chạy hệ thống Multi-Agent (Coordinator và các Sub-Agents)
  - Thẩm định và ghi kết quả ra output/
  - Đóng gói file zip output.zip phục vụ nộp bài
  - Xuất metadata.json
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from pathlib import Path

from src import llm_service, case_pipeline
from src.tools_engine import ToolRegistry
from src.csv_store import OlistStore
from src.coordinator_engine import Coordinator, TraceWriter

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOGGING_DIR = ROOT_DIR / "logging"
ZIP_FILE = ROOT_DIR / "output.zip"
METADATA_FILE = ROOT_DIR / "metadata.json"
TRACE_FILE = ROOT_DIR / "trace.jsonl"
LOGGING_TRACE_FILE = LOGGING_DIR / "trace.jsonl"


def write_metadata():
    """Tạo file metadata.json theo yêu cầu."""
    data = {
        "model_name": "qwen/qwen-2.5-7b-instruct",
        "parameter_size": "7B",
        "framework": "Custom Multi-Agent A2A Architecture (Python)",
        "runtime": "Python 3.10+ / Pure Rule-Engine / Multi-Agent Handoff",
        "description": "Multi-agent e-commerce dispute resolution system running <=10B model architecture with strict A2A handoff logging.",
    }
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[+] Saved {METADATA_FILE}")


def package_output_zip():
    """Tạo file output.zip chứa đúng 50 file JSON từ output/."""
    json_files = sorted(OUTPUT_DIR.glob("EC_*.json"))
    if len(json_files) != 50:
        print(f"[!] WARNING: Number of output JSON files is {len(json_files)}, expected 50!")

    with zipfile.ZipFile(ZIP_FILE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filepath in json_files:
            zf.write(filepath, arcname=filepath.name)

    print(f"[+] Successfully created {ZIP_FILE} containing {len(json_files)} JSON files (flat arcname EC_xxx.json).")


def main():
    print("=== STARTING MULTI-AGENT E-COMMERCE DISPUTE RESOLUTION PIPELINE ===")

    # Load environment variables from .env if present
    llm_service.load_env(str(ROOT_DIR / ".env"))

    # Map OPENAI_API_KEY to OPENROUTER_API_KEY if needed by src/model_config.py
    if not os.environ.get("OPENROUTER_API_KEY"):
        os.environ["OPENROUTER_API_KEY"] = os.environ.get("OPENAI_API_KEY") or "mock_key"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGGING_DIR.mkdir(parents=True, exist_ok=True)

    print("[*] Loading Olist CSV datasets into memory...")
    store = OlistStore(str(DATA_DIR))
    registry = ToolRegistry(store)

    run_id = "run_20260805"
    trace = TraceWriter(str(TRACE_FILE), run_id=run_id)
    coordinator = Coordinator(store, registry, trace)

    input_files = sorted(INPUT_DIR.glob("EC_*.json"))
    print(f"[*] Found {len(input_files)} cases in {INPUT_DIR}")

    success_count = 0
    for input_path in input_files:
        with open(input_path, "r", encoding="utf-8") as f:
            case_input = json.load(f)

        case_id = case_input.get("case_id")
        try:
            try:
                output_data, record = coordinator.run_case(case_input)
            except Exception as api_err:
                # Log fallback event to trace and use deterministic solver
                trace.emit(case_id, "fallback_policy_solver", reason=str(api_err))
                output_data, _errors = case_pipeline.solve_case(store, case_input)

            output_path = OUTPUT_DIR / f"{case_id}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            success_count += 1
            print(f"[OK] Successfully processed {case_id} -> {output_path.name}")
        except Exception as e:
            print(f"[FAIL] ERROR processing {case_id}: {e}")
            raise e

    print(f"\n[+] Completed {success_count}/{len(input_files)} cases successfully.")

    # Copy trace.jsonl to logging/trace.jsonl for complete compatibility
    shutil.copyfile(TRACE_FILE, LOGGING_TRACE_FILE)

    # Write metadata.json
    write_metadata()

    # Package output.zip
    package_output_zip()


if __name__ == "__main__":
    main()
