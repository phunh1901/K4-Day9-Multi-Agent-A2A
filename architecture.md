# Kiến trúc Multi-Agent (A2A) — Dispute Resolution System

## 1. Sơ đồ Tổng quan Kiến trúc

```
                            +-------------------+
                            |   Customer Request|
                            +---------+---------+
                                      |
                                      v
                            +-------------------+
                            | Coordinator Agent |
                            +----+----+----+----+
                                 |    |    |
        +------------------------+    |    +------------------------+
        |                             |                             |
        v                             v                             v
+---------------+           +-------------------+         +-------------------+
| Customer Agent|           |OrderProduct Agent |         |   Payment Agent   |
+-------+-------+           +---------+---------+         +---------+---------+
        |                             |                             |
        +------------------------+    |    +------------------------+
                                 |    |    |
                                 v    v    v
                            +-------------------+
                            |  Delivery Agent   |
                            +---------+---------+
                                      |
                                      v
                            +-------------------+
                            |   Policy Agent    |
                            +---------+---------+
                                      |
                                      v
                            +-------------------+
                            |  Verifier Agent   |
                            +---------+---------+
                                      |
                                      v
                            +-------------------+
                            | Output JSON & Zip |
                            +-------------------+
```

## 2. Vai trò và Quyền truy cập Dữ liệu của các Agent

| Agent | Vai trò & Trách nhiệm | Dữ liệu truy cập | Output bàn giao |
| :--- | :--- | :--- | :--- |
| **Coordinator Agent** | Tiếp nhận case khiếu nại, phân chia nhiệm vụ cho các sub-agent, tổng hợp kết quả. | `input/EC_xxx.json` | JSON Output hoàn chỉnh |
| **Customer Agent** | Truy vết `customer_unique_id` và lịch sử mua hàng qua nhiều đơn. | `olist_customers_dataset.csv`<br>`olist_orders_dataset.csv` | `customer_unique_id`<br>`related_order_ids` |
| **Order & Product Agent** | Kiểm tra chi tiết item, sản phẩm, danh mục tiếng Anh và thông tin seller. | `olist_order_items_dataset.csv`<br>`olist_products_dataset.csv`<br>`product_category_name_translation.csv` | `item_ids`, `product_ids`<br>`seller_ids`, `category_names` |
| **Payment Agent** | Tổng hợp danh sách payment row, tính tổng tiền thanh toán và đối soát với kỳ vọng. | `olist_order_payments_dataset.csv` | `payment_ids`<br>`reconciliation` |
| **Delivery Agent** | Tính toán độ lệch ngày giao hàng thực tế vs dự kiến, độ lệch bàn giao seller vs shipping limit. | `olist_orders_dataset.csv`<br>`olist_order_items_dataset.csv` | `delivery_variance_hours`<br>`seller_handoff_analysis`<br>`late_handoff_seller_ids` |
| **Policy Agent** | Tổng hợp bằng chứng từ các Agent, áp dụng chính sách `EC_POLICY_V2` phân định trách nhiệm & khoản hoàn. | Dữ liệu tổng hợp từ các Agent trước | `primary_issue`, `secondary_issues`<br>`financial_resolution`, `evidence_ids`<br>`resolution_actions` |
| **Verifier Agent** | Thẩm định tính hợp lệ của Output JSON (Schema, Array Limits, Format ID, Refund vs Status) trước khi ghi file. | Output JSON draft | Kết quả Validation (Pass/Fail) |

## 3. Quy trình Truyền tin Handoff (Agent-to-Agent Protocol)

Mọi bước handoff dữ liệu giữa các Agent đều được tự động ghi lại dưới dạng sự kiện JSONL trong file `trace.jsonl` với cấu trúc:

```json
{
  "timestamp": "2026-08-05T15:20:00.123456",
  "case_id": "EC_001",
  "sender_agent": "PolicyAgent",
  "receiver_agent": "CoordinatorAgent",
  "action": "POLICY_EVALUATION_COMPLETE",
  "message": "Đã áp dụng EC_POLICY_V2. Primary: late_delivery_seller, Refund: 18.27 BRL...",
  "payload_summary": { ... },
  "evidence_ids": [ "order:...", "item:...", "seller:...", "policy:..." ]
}
```

## 4. Mô hình và Môi trường Thực thi (Runtime & Model Specification)

- **Model sử dụng**: `Qwen/Qwen2.5-7B-Instruct` (Parameters $\le 10\text{B}$).
- **Framework**: Custom Agent-to-Agent Architecture (Python 3.10+ / Pandas).
- **Security**: API Keys lưu trong `.env` (không commit git). Tên model khai báo tại `main.py`, `src/agent_system.py` và `metadata.json`.
