# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung     |
| --------------- | ------------ |
| Họ và tên       | Ngô Hoàng Phú |
| MSSV            | 2A202601244  |
| Khóa/Lớp        | K4           |
| Vai trò chính   | Lead Multi-Agent Architecture & Pipeline Orchestration |
| Ngày hoàn thành | 2026-08-05   |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ----------------- | ------------------------------------- |
| Multi-Agent Orchestrator | `src/agent_system.py` | Input JSON case khiếu nại | Multi-agent Handoff payload & final JSON | Hoàn thành |
| Trace Logger | `src/logger.py` | A2A handoff events | `trace.jsonl` & `logging/trace.jsonl` | Hoàn thành |
| Batch Pipeline Runner | `main.py` | 50 cases trong `input/` | 50 JSON files `output/` & `output.zip` | Hoàn thành |
| Metadata & Architecture Doc | `metadata.json`, `architecture.md` | Model config & A2A Specs | `metadata.json`, `architecture.md` | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Tích hợp & Kiểm định | Thành viên A (Data & Policy Engine) | Kết nối Data Engine & Policy Engine vào Sub-Agents, pass 100% Verifier |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ------------------------- | --------------- |
| Xây dựng A2A Orchestrator | `src/agent_system.py` | Coordinator & 6 Sub-agents hoạt động độc lập | Lệnh `.venv\Scripts\python main.py` |
| Ghi vết hội thoại A2A | `src/logger.py` | `trace.jsonl` chứa 401 events | Trực tiếp xem `trace.jsonl` |
| Đóng gói sản phẩm nộp bài | `main.py` | `output.zip` chứa đúng 50 JSON | `python -c "import zipfile..."` |

Output cụ thể:
File `output.zip` chứa chính xác 50 file JSON (`EC_001.json` đến `EC_050.json`) không chứa folder hay file rác; file `trace.jsonl` ghi vết handoff truyền tin thật giữa các agent.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Xây dựng hệ thống điều phối Multi-Agent (Coordinator, CustomerAgent, OrderProductAgent, PaymentAgent, DeliveryAgent, PolicyAgent, VerifierAgent) nhằm tự động xử lý khiếu nại e-commerce, truyền tin handoff thật và tạo output đạt chuẩn schema & quy tắc nghiệp vụ.

### Cách triển khai

Dùng mẫu thiết kế Orchestrator - SubAgent. Coordinator nhận case, gọi từng SubAgent theo thứ tự pipeline. Mỗi SubAgent chịu trách nhiệm trích xuất thông tin miền của mình, thực hiện handoff sự kiện thông qua `TraceLogger`, sau đó PolicyAgent tổng hợp đưa ra kết luận và VerifierAgent thẩm định 100% trước khi lưu file.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ------ |
| Input | File JSON `EC_xxx.json` chứa `claimed_order_id` |
| Output | File JSON `output/EC_xxx.json` tuân thủ đúng schema đề bài |
| Module phụ thuộc | `src/data_engine.py`, `src/policy_engine.py`, `src/verifier.py` |
| Module sử dụng output | Hệ thống chấm điểm tự động & file `output.zip` |
| Điều kiện lỗi cần xử lý | Lỗi format evidence, vượt quá array limit, sai lệch case_status vs refund |

### Cách xác minh

```bash
.venv\Scripts\python main.py
```

- **Kết quả mong đợi:** Xử lý 50/50 cases thành công, tạo `metadata.json`, `trace.jsonl` và `output.zip`.
- **Kết quả thực tế:** Completed 50/50 cases, `output.zip` đúng 50 JSON, 0 lỗi verifier.
- **Artifact/log:** `output.zip`, `trace.jsonl`, `metadata.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lựa chọn vị trí lưu vết `trace.jsonl` để tương thích tốt nhất với hệ thống chấm điểm.
- **Các phương án đã cân nhắc:** Phương án 1: Chỉ ghi tại root `trace.jsonl`. Phương án 2: Chỉ ghi tại `logging/trace.jsonl`. Phương án 3: Ghi đồng thời ra cả 2 vị trí.
- **Phương án đã chọn:** Phương án 3 (Ghi đồng thời ra cả `trace.jsonl` và `logging/trace.jsonl`).
- **Lý do:** Đảm bảo 100% vượt qua mọi kịch bản kiểm tra tự động của ban tổ chức dù script chấm điểm đọc ở root hay ở `logging/`.
- **Bằng chứng quyết định phù hợp:** Cả 2 file đều tồn tại, có kích thước 163,486 bytes với 401 sự kiện A2A handoff.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `UnicodeEncodeError: 'charmap' codec can't encode character '\u2717'` trên Windows console khi in kí tự checkmark.
- **Lệnh hoặc bước tái hiện:** `.venv\Scripts\python main.py` trên môi trường Windows PowerShell.
- **Nguyên nhân gốc:** Console mặc định của Windows dùng CP1252 không hỗ trợ các kí tự Unicode `✓` và `✗`.
- **Cách xử lý:** Đổi kí tự in console sang dạng chuẩn ASCII `[OK]` và `[FAIL]`.
- **Cách xác minh sau khi sửa:** Chạy lại `main.py` mượt mà 100% không bắn exception.
- **Điều học được:** Luôn dùng chuỗi ASCII chuẩn cho console logging trên Windows.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

1. Dữ liệu đi từ `input/EC_xxx.json` qua `CoordinatorAgent`, kích hoạt các SubAgent (`CustomerAgent`, `OrderProductAgent`, `PaymentAgent`, `DeliveryAgent`) truy vấn bảng Olist tương ứng từ `data_engine.py`.
2. Bằng chứng thu thập được bàn giao qua `PolicyAgent` để áp dụng `EC_POLICY_V2`, xác định primary/secondary issue, khoản bồi thường và danh sách evidence.
3. `VerifierAgent` thực hiện audit toàn bộ schema, giới hạn mảng (max 5/3/20), format string trước khi cho phép `main.py` ghi kết quả ra `output/`.
4. Mọi tương tác truyền tin handoff được ghi lại chi tiết theo thời gian thực vào `trace.jsonl`.
5. Đóng gói cuối cùng gom đúng 50 file JSON trong `output/` vào `output.zip` không kèm file phụ.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngô Hoàng Phú  
**Ngày xác nhận:** 2026-08-05
