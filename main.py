"""
main.py — Đinh Quốc Việt (nhánh `viet`)
Runner của pipeline Multi-Agent:
  1. Nạp và index 9 CSV Olist một lần cho cả 50 case.
  2. Chạy Coordinator + 6 sub-agent cho từng case trong `input/`.
  3. Ghi output đã qua Verifier ra `output/EC_xxx.json`.
  4. Ghi `trace.jsonl` (chỉ lượt chạy mới nhất) và `metadata.json`.
  5. Đóng gói `output.zip` gồm đúng 50 JSON, không kèm file lạ.

Chạy:  python main.py
"""
from __future__ import annotations

import json
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

from src.agent_system import (
    MODEL_NAME,
    MODEL_PARAMETER_SIZE,
    MODEL_TEMPERATURE,
    CoordinatorAgent,
)
from src.data_engine import get_repository
from src.logger import TraceLogger

ROOT_DIR = Path(__file__).parent
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
ZIP_FILE = ROOT_DIR / "output.zip"
METADATA_FILE = ROOT_DIR / "metadata.json"

EXPECTED_CASES = 50

# Console Windows mặc định cp1252 -> ép UTF-8 để log tiếng Việt không vỡ
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def write_metadata(run_stats: dict) -> None:
    metadata = {
        "cohort": "Cohort 4",
        "model_name": MODEL_NAME,
        "parameter_size": MODEL_PARAMETER_SIZE,
        "framework": "Custom Multi-Agent A2A (Coordinator + 6 sub-agent, Python thuần)",
        "runtime": "Python 3.10+ / pandas 2.2 / openai-compatible client (advisory)",
        "temperature": MODEL_TEMPERATURE,
        "policy_version": "EC_POLICY_V2",
        "agents": [
            "CoordinatorAgent",
            "CustomerAgent",
            "OrderProductAgent",
            "PaymentAgent",
            "DeliveryAgent",
            "PolicyAgent",
            "VerifierAgent",
        ],
        "decision_mode": (
            "Toàn bộ giá trị trong output do rule-engine deterministic sinh ra từ CSV; "
            f"model {MODEL_NAME} (<=10B) chỉ đóng vai reviewer diễn giải và được ghi vào trace, "
            "không sửa số liệu hay ID."
        ),
        "run": run_stats,
    }
    METADATA_FILE.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Đã ghi {METADATA_FILE.name}")


def package_output_zip() -> int:
    json_files = sorted(OUTPUT_DIR.glob("EC_*.json"))
    if ZIP_FILE.exists():
        ZIP_FILE.unlink()
    with zipfile.ZipFile(ZIP_FILE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in json_files:
            zf.write(path, arcname=f"output/{path.name}")
    size_kb = ZIP_FILE.stat().st_size / 1024
    print(f"[+] Đã đóng gói {ZIP_FILE.name}: {len(json_files)} JSON, {size_kb:.1f} KB")
    return len(json_files)


def main() -> int:
    print("=== PIPELINE MULTI-AGENT — E-COMMERCE DISPUTE RESOLUTION (EC_POLICY_V2) ===")
    started = time.perf_counter()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT_DIR.glob("*.json"):
        stale.unlink()  # bảo đảm output/ chỉ chứa kết quả của lượt chạy này

    repo = get_repository()
    print(f"[*] Đã index {len(repo.orders_by_id)} order, {len(repo.items_by_order)} order có item")

    logger = TraceLogger(reset=True)
    coordinator = CoordinatorAgent(logger, repo)
    print(f"[*] LLM advisor ({MODEL_NAME}): "
          f"{'sẵn sàng' if coordinator.advisor.available else 'không cấu hình -> chạy deterministic'}")

    input_files = sorted(INPUT_DIR.glob("EC_*.json"))
    print(f"[*] Tìm thấy {len(input_files)} case trong {INPUT_DIR.name}/")

    primary_counter: Counter = Counter()
    status_counter: Counter = Counter()
    refund_total = 0.0
    failures: list[str] = []

    for path in input_files:
        case_input = json.loads(path.read_text(encoding="utf-8"))
        case_id = case_input.get("case_id", path.stem)
        try:
            output = coordinator.process_case(case_input)
        except Exception as exc:
            failures.append(f"{case_id}: {exc}")
            print(f"[FAIL] {case_id}: {exc}")
            continue

        (OUTPUT_DIR / f"{case_id}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        primary_counter[output["case_assessment"]["primary_issue"]] += 1
        status_counter[output["case_assessment"]["case_status"]] += 1
        refund_total += output["financial_resolution"]["recommended_refund_brl"]
        print(f"[OK] {case_id}: {output['case_assessment']['primary_issue']:<24} "
              f"refund={output['financial_resolution']['recommended_refund_brl']:>9.2f} BRL")

    elapsed = time.perf_counter() - started
    written = len(list(OUTPUT_DIR.glob("EC_*.json")))

    print("\n--- TỔNG KẾT ---")
    print(f"Case xử lý thành công : {written}/{len(input_files)}")
    for issue, count in primary_counter.most_common():
        print(f"  {issue:<26} {count}")
    print(f"case_status           : {dict(status_counter)}")
    print(f"Tổng refund đề xuất   : {round(refund_total, 2)} BRL")
    print(f"Trace A2A             : {logger.summary()}")
    print(f"LLM advisory          : {coordinator.advisor.stats()}")
    print(f"Thời gian chạy        : {elapsed:.1f}s")
    if failures:
        print(f"[!] {len(failures)} case lỗi: {failures}")

    run_stats = {
        "cases_processed": written,
        "cases_expected": EXPECTED_CASES,
        "primary_issue_distribution": dict(primary_counter),
        "case_status_distribution": dict(status_counter),
        "total_recommended_refund_brl": round(refund_total, 2),
        "verifier_repair_rounds": coordinator.stats["repairs"],
        "llm_advisory": coordinator.advisor.stats(),
        "trace": logger.summary(),
        "duration_seconds": round(elapsed, 2),
    }
    write_metadata(run_stats)
    zipped = package_output_zip()

    if written != EXPECTED_CASES or zipped != EXPECTED_CASES:
        print(f"[!] CẢNH BÁO: cần đúng {EXPECTED_CASES} file, đang có {written} output / {zipped} trong zip")
        return 1
    print("[✓] Hoàn tất: 50/50 case đã qua Verifier và được đóng gói.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
