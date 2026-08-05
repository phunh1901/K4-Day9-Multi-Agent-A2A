"""
validate_submission.py — Đinh Quốc Việt (nhánh `viet`)
Audit độc lập trước khi nộp: đọc lại các artifact đã ghi ra đĩa (không tin cache
trong RAM của lần chạy) và kiểm tra 5 điều kiện nộp bài.

  1. output/ có đúng 50 file EC_001..EC_050.json, JSON parse được.
  2. Mỗi output vượt qua toàn bộ luật của VerifierAgent khi đối chiếu lại CSV.
  3. output.zip chứa đúng 50 entry JSON, không kèm file lạ / .env / source code.
  4. trace.jsonl là của một lượt chạy duy nhất và phủ đủ 50 case với đủ 6 agent.
  5. metadata.json khai báo model <= 10B và đủ trường bắt buộc.

Chạy:  python validate_submission.py
Exit code 0 = sẵn sàng nộp.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

from src.data_engine import get_repository
from src.verifier import verify_output

ROOT_DIR = Path(__file__).parent
OUTPUT_DIR = ROOT_DIR / "output"
ZIP_FILE = ROOT_DIR / "output.zip"
TRACE_FILE = ROOT_DIR / "trace.jsonl"
METADATA_FILE = ROOT_DIR / "metadata.json"

EXPECTED_CASE_IDS = [f"EC_{i:03d}" for i in range(1, 51)]
EXPECTED_AGENTS = {
    "CustomerAgent",
    "OrderProductAgent",
    "PaymentAgent",
    "DeliveryAgent",
    "PolicyAgent",
    "VerifierAgent",
}
MAX_PARAMETER_BILLIONS = 10.0

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def check_outputs(problems: list[str]) -> list[dict]:
    repo = get_repository()
    outputs: list[dict] = []
    files = sorted(OUTPUT_DIR.glob("*.json"))
    names = [f.name for f in files]

    if names != [f"{cid}.json" for cid in EXPECTED_CASE_IDS]:
        missing = set(f"{c}.json" for c in EXPECTED_CASE_IDS) - set(names)
        extra = set(names) - set(f"{c}.json" for c in EXPECTED_CASE_IDS)
        problems.append(f"output/ sai danh sách file (thiếu {sorted(missing)}, thừa {sorted(extra)})")

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: JSON không parse được ({exc})")
            continue
        outputs.append(data)
        if data.get("case_id") != path.stem:
            problems.append(f"{path.name}: case_id {data.get('case_id')!r} không khớp tên file")
        for error in verify_output(data, repo):
            problems.append(f"{path.name}: {error}")

    print(f"[1-2] Đã kiểm chứng {len(outputs)} output với dữ liệu CSV gốc")
    return outputs


def check_zip(problems: list[str]) -> None:
    if not ZIP_FILE.exists():
        problems.append("thiếu output.zip")
        return
    with zipfile.ZipFile(ZIP_FILE) as zf:
        names = zf.namelist()
    case_ids = sorted(Path(n).stem for n in names if n.endswith(".json"))
    non_json = [n for n in names if not n.endswith(".json")]

    if case_ids != EXPECTED_CASE_IDS:
        problems.append(f"output.zip không chứa đúng 50 JSON EC_001..EC_050 (có {len(case_ids)})")
    if non_json:
        problems.append(f"output.zip chứa file lạ: {non_json}")
    size_mb = ZIP_FILE.stat().st_size / 1024 / 1024
    if size_mb > 5:
        problems.append(f"output.zip {size_mb:.2f} MB vượt giới hạn 5 MB")
    print(f"[3] output.zip: {len(case_ids)} JSON, {size_mb:.2f} MB, không có file lạ")


def check_trace(problems: list[str]) -> None:
    if not TRACE_FILE.exists():
        problems.append("thiếu trace.jsonl")
        return
    run_ids: set[str] = set()
    cases: set[str] = set()
    senders: Counter = Counter()
    total = 0

    for line_no, line in enumerate(TRACE_FILE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"trace.jsonl dòng {line_no} không phải JSON hợp lệ")
            continue
        total += 1
        run_ids.add(record.get("run_id"))
        cases.add(record.get("case_id"))
        senders[record.get("sender_agent")] += 1

    if len(run_ids) != 1:
        problems.append(f"trace.jsonl chứa {len(run_ids)} lượt chạy, đề bài yêu cầu chỉ lượt mới nhất")
    missing_cases = set(EXPECTED_CASE_IDS) - cases
    if missing_cases:
        problems.append(f"trace.jsonl thiếu case: {sorted(missing_cases)}")
    missing_agents = EXPECTED_AGENTS - set(senders)
    if missing_agents:
        problems.append(f"trace.jsonl thiếu handoff từ agent: {sorted(missing_agents)}")
    print(f"[4] trace.jsonl: {total} message, 1 run_id, {len(cases)} case, "
          f"{len(set(senders) & EXPECTED_AGENTS)}/6 sub-agent có bàn giao")


def check_metadata(problems: list[str]) -> None:
    if not METADATA_FILE.exists():
        problems.append("thiếu metadata.json")
        return
    meta = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    for key in ("model_name", "parameter_size", "framework", "runtime"):
        if not meta.get(key):
            problems.append(f"metadata.json thiếu trường {key}")

    size = str(meta.get("parameter_size", ""))
    match = re.match(r"^([\d.]+)\s*B$", size, re.IGNORECASE)
    if not match:
        problems.append(f"parameter_size không đọc được: {size!r}")
    elif float(match.group(1)) > MAX_PARAMETER_BILLIONS:
        problems.append(f"model {meta.get('model_name')} có {size} > 10B, vi phạm ràng buộc đề bài")
    print(f"[5] metadata.json: {meta.get('model_name')} ({size}) — trong giới hạn 10B")


def main() -> int:
    problems: list[str] = []
    outputs = check_outputs(problems)
    check_zip(problems)
    check_trace(problems)
    check_metadata(problems)

    if outputs:
        primary = Counter(o["case_assessment"]["primary_issue"] for o in outputs)
        status = Counter(o["case_assessment"]["case_status"] for o in outputs)
        refund = round(sum(o["financial_resolution"]["recommended_refund_brl"] for o in outputs), 2)
        print("\n--- PHÂN BỐ KẾT QUẢ ---")
        for issue, count in primary.most_common():
            print(f"  {issue:<26} {count}")
        print(f"  case_status: {dict(status)} | tổng refund: {refund} BRL")

    print()
    if problems:
        print(f"[X] KHÔNG ĐẠT — {len(problems)} vấn đề:")
        for problem in problems[:40]:
            print(f"    - {problem}")
        return 1
    print("[✓] ĐẠT — bộ nộp bài hợp lệ, sẵn sàng upload output.zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
