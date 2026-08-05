# Kiến trúc Multi-Agent A2A — E-commerce Dispute Resolution (EC_POLICY_V2)

> Bản kiến trúc của nhánh `viet` (Đinh Quốc Việt — MHV 01891). Mỗi thành viên trong nhóm
> triển khai bản của riêng mình trên nhánh riêng; tài liệu này mô tả đúng code đang chạy
> trong `main.py` + `src/` của nhánh này.

## 1. Sơ đồ agent và luồng handoff

```text
                         input/EC_xxx.json
                                 |
                                 v  EVENT: CASE_RECEIVED
                     +-----------------------------+
                     |     CoordinatorAgent        |
                     |  (điều phối, không tự tính) |
                     +--+-----+-----+-----+-----+--+
        REQUEST 1 |      |     |     |     |      | REQUEST 5
                  v      |     |     |     |      v
      +-------------------+    |     |     |   +--------------------+
      |   CustomerAgent   |    |     |     |   |    PolicyAgent     |
      | customers, orders |    |     |     |   |  EC_POLICY_V2      |
      +-------------------+    |     |     |   +--------------------+
                  |  RESPONSE  |     |     |            ^
                  |            v     |     |            | bằng chứng đã hợp nhất
                  |  +--------------------+|            |
                  |  | OrderProductAgent  ||            |
                  |  | items, products    ||            |
                  |  +--------------------+|            |
                  |            |           |            |
                  |            v  items    v            |
                  |  +-----------------+ +-----------------+
                  |  |  PaymentAgent   | |  DeliveryAgent  |
                  |  | order_payments  | | orders, items   |
                  |  +-----------------+ +-----------------+
                  |            |           |            |
                  +------------+-----+-----+------------+
                                     |
                                     v  assemble()
                          +----------------------+
                          |   Output JSON draft  |
                          +----------+-----------+
                                     |  REQUEST: VERIFY_OUTPUT
                                     v
                          +----------------------+
                          |    VerifierAgent     |
                          |  schema + grounding  |
                          +----+------------+----+
                     REPAIR_REQUIRED |      | valid
                     (quay lại       |      v
                      Coordinator    |   output/EC_xxx.json  ->  output.zip
                      normalize())<--+
```

Toàn bộ mũi tên trên sơ đồ đều là message có thật trong `trace.jsonl`
(700 message cho 50 case ở lượt chạy hiện tại: 100 EVENT + 300 REQUEST + 300 RESPONSE).

## 2. Vai trò và quyền truy cập dữ liệu (least-privilege)

Mỗi agent chỉ được cấp đúng các bảng cần cho domain của nó; quyền này khai báo tường minh
trong thuộc tính `data_access` của từng class và được ghi kèm vào mỗi REQUEST trong trace.

| Agent | Vai trò | Bảng được phép đọc | Bàn giao cho Coordinator |
| --- | --- | --- | --- |
| **CoordinatorAgent** | Nhận case, phát REQUEST, ráp output, chạy vòng sửa lỗi. Không tự tính nghiệp vụ. | `input/EC_xxx.json`, `orders` (chỉ để tra tồn tại order) | Output JSON hoàn chỉnh |
| **CustomerAgent** | Suy ra `customer_unique_id`, tìm các order khác của cùng khách. | `customers`, `orders` | `customer_unique_id`, `related_order_ids` |
| **OrderProductAgent** | Liệt kê item, seller, product, category theo thứ tự `order_item_id`. | `order_items`, `products`, `sellers` | `item_ids`, `seller_ids`, `product_ids`, `category_names` |
| **PaymentAgent** | Cộng payment row, đối soát với item + freight (ngưỡng 0.10 BRL). | `order_payments` (+ item nhận qua handoff) | `payment_ids`, khối `payment_reconciliation` |
| **DeliveryAgent** | Tính `delivery_variance_hours` và `handoff_variance_hours` theo từng seller. | `orders`, `order_items` | Khối `delivery_analysis`, `late_handoff_seller_ids` |
| **PolicyAgent** | Áp `EC_POLICY_V2`: primary/secondary issue, root cause, trách nhiệm, refund, actions, evidence. | *Không đọc CSV* — chỉ làm việc trên bằng chứng được handoff | `case_assessment`, `root_cause_analysis`, `evidence_ids`, `financial_resolution`, `resolution_actions` |
| **VerifierAgent** | Kiểm schema, giới hạn mảng, thứ tự nghiệp vụ, null handling, và **grounding**: mọi ID phải tồn tại thật trong CSV. | `orders`, `order_items`, `order_payments`, `sellers` | `valid` + danh sách lỗi |

PolicyAgent cố tình không có quyền đọc CSV: nó chỉ được kết luận dựa trên bằng chứng do các
agent khác bàn giao, nên không thể "tự tìm thêm" dữ liệu ngoài luồng handoff.

## 3. Giao thức A2A

Mỗi bước là một message JSONL trong `trace.jsonl`:

```json
{
  "run_id": "run-20260805-190649",
  "seq": 12,
  "msg_id": "run-20260805-190649-00012-a1b2c3",
  "parent_msg_id": "run-20260805-190649-00011-9f8e7d",
  "timestamp": "2026-08-05T19:06:49.812",
  "case_id": "EC_001",
  "sender_agent": "DeliveryAgent",
  "receiver_agent": "CoordinatorAgent",
  "msg_type": "RESPONSE",
  "action": "ANALYZE_DELIVERY_DONE",
  "message": "delivery_variance=-166.52h, late_delivery=False, late_sellers=không có",
  "payload_summary": { "delivery_variance_hours": -166.52, "late_handoff_seller_ids": [] },
  "evidence_ids": [],
  "latency_ms": 0.42
}
```

- `msg_type`: `REQUEST` (giao việc) → `RESPONSE` (bàn giao kết quả), thêm `EVENT` (mốc vòng đời
  case) và `ERROR` (agent thất bại).
- `parent_msg_id` trỏ về REQUEST sinh ra RESPONSE, nên trace dựng lại được cây handoff của
  từng case thay vì chỉ là log phẳng.
- File được ghi mới ở đầu mỗi lượt chạy (`TraceLogger(reset=True)`) đúng yêu cầu "chỉ lượt
  chạy mới nhất".

## 4. Vòng kiểm chứng và sửa lỗi

VerifierAgent là cổng chặn thật, không phải bước trang trí:

1. Coordinator gửi `VERIFY_OUTPUT`.
2. Verifier chấm 5 nhóm luật (schema, giới hạn mảng + thứ tự nghiệp vụ, grounding ID theo CSV,
   null handling khi order không có item row, nhất quán refund ↔ `case_status` ↔ root cause).
3. Nếu có lỗi, Verifier trả `REPAIR_REQUIRED` kèm danh sách lỗi; Coordinator chạy
   `normalize()` (cắt mảng theo giới hạn, khử trùng lặp, làm tròn 2 chữ số, đồng bộ lại
   `case_status`) rồi gửi verify lại, tối đa 2 vòng.
4. Chỉ output sạch lỗi mới được ghi ra `output/`. Lượt chạy hiện tại: 50/50 case pass ngay
   vòng đầu, 0 lần phải sửa.

Sau khi pipeline kết thúc, `validate_submission.py` audit lại từ đĩa: đọc lại 50 file JSON,
chạy lại toàn bộ luật Verifier với CSV, soi nội dung `output.zip`, kiểm tra `trace.jsonl`
chỉ có một `run_id` và phủ đủ 50 case với đủ 6 sub-agent, và kiểm tra `metadata.json` khai
báo model ≤ 10B.

## 5. Model và ranh giới quyết định

- **Model**: `Qwen/Qwen2.5-7B-Instruct` — 7.6B tham số, thỏa ràng buộc ≤ 10B. Tên model khai
  báo cứng trong `src/agent_system.py` (`MODEL_NAME`) và `metadata.json`; `.env` chỉ chứa
  endpoint và API key, không chứa tên model.
- **Ranh giới**: mọi con số, ID và nhãn trong output đều do rule-engine deterministic sinh ra
  từ CSV. Model 7B đóng vai *reviewer*: nhận tóm tắt bằng chứng, xác nhận hoặc nêu nghi vấn về
  kết luận, và kết quả đó chỉ đi vào `trace.jsonl`. Lý do: mọi trường trong schema phải kiểm
  chứng được từ dữ liệu và evidence sai định dạng bị tính false positive, nên để LLM ghi trực
  tiếp vào output là rủi ro thuần túy. Khi không cấu hình API key, hệ chạy hoàn toàn
  deterministic và trace ghi rõ `llm_available: false`.

## 6. Chạy lại toàn bộ

```bash
pip install -r requirements.txt
python main.py
python validate_submission.py
python tests/test_policy_engine.py
```
