"""
main.py — Thành viên B
Batch Pipeline Runner:
  - Đọc 50 file JSON trong input/
  - Chạy hệ thống Multi-Agent (CoordinatorAgent và các Sub-Agents)
  - Thẩm định và ghi kết quả ra output/
  - Đóng gói file zip output.zip phục vụ nộp bài
  - Xuất metadata.json
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

from src.agent_system import MODEL_NAME, CoordinatorAgent
from src.logger import TraceLogger

ROOT_DIR = Path(__file__).parent
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
ZIP_FILE = ROOT_DIR / "output.zip"
METADATA_FILE = ROOT_DIR / "metadata.json"


def write_metadata():
    """Tạo file metadata.json theo yêu cầu."""
    data = {
        "model_name": MODEL_NAME,
        "parameter_size": "7B",
        "framework": "Custom Multi-Agent A2A Architecture (Python)",
        "runtime": "Python 3.10+ / Pandas / Pure Rule-Engine",
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
            zf.write(filepath, arcname=f"output/{filepath.name}")

    print(f"[+] Successfully created {ZIP_FILE} containing {len(json_files)} JSON files with arcname output/EC_xxx.json.")


def main():
    print("=== STARTING MULTI-AGENT E-COMMERCE DISPUTE RESOLUTION PIPELINE ===")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize TraceLogger (resets trace.jsonl)
    logger = TraceLogger(reset=True)
    coordinator = CoordinatorAgent(logger)

    input_files = sorted(INPUT_DIR.glob("EC_*.json"))
    print(f"[*] Found {len(input_files)} cases in {INPUT_DIR}")

    success_count = 0
    for input_path in input_files:
        with open(input_path, "r", encoding="utf-8") as f:
            case_input = json.load(f)

        case_id = case_input.get("case_id")
        try:
            output_data = coordinator.process_case(case_input)
            output_path = OUTPUT_DIR / f"{case_id}.json"

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            success_count += 1
            print(f"[OK] Successfully processed {case_id} -> {output_path.name}")
        except Exception as e:
            print(f"[FAIL] ERROR processing {case_id}: {e}")
            raise e

    print(f"\n[+] Completed {success_count}/{len(input_files)} cases successfully.")

    # Write metadata.json
    write_metadata()

    # Package output.zip
    package_output_zip()


if __name__ == "__main__":
    main()
