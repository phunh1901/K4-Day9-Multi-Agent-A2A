# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                                                       |
| --------------- | -------------------------------------------------------------- |
| Họ và tên       | Đinh Quốc Việt                                                  |
| MSSV/MHV        | 01891                                                           |
| Khóa/Lớp        | K4 — E403                                                       |
| Vai trò chính   | Pipeline owner nhánh `viet`: rule-engine EC_POLICY_V2, giao thức A2A và Verifier |
| Ngày hoàn thành | 2026-08-05                                                      |

Nhóm thống nhất mỗi thành viên tự triển khai một bản hoàn chỉnh trên nhánh riêng
(`viet`, `longnt`, `phunh`) để không giẫm chân nhau. Báo cáo này chỉ nhận ownership cho
phần code trên nhánh `viet`.

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Tầng dữ liệu Olist | `src/data_engine.py` — `OlistRepository.build`, `compute_payment_reconciliation`, `compute_delivery_variance`, `compute_handoff_variance` | 9 CSV trong `data/` | Index dict tra cứu O(1) + các chỉ số tiền/giờ đã làm tròn 2 chữ số | Hoàn thành |
| Rule-engine chính sách | `src/policy_engine.py` — `determine_primary_issue`, `determine_secondary_issues`, `build_delivery_analysis`, `build_resolution_actions`, `build_evidence_ids`, `compute_confidence` | Bằng chứng do các agent bàn giao | `case_assessment`, `root_cause_analysis`, `financial_resolution`, `resolution_actions`, `evidence_ids` | Hoàn thành |
| Giao thức A2A + trace | `src/logger.py` — `TraceLogger.log_message`, `request`, `response`, `Stopwatch` | Lời gọi từ Coordinator/sub-agent | `trace.jsonl` dạng message có `msg_id`/`parent_msg_id`/`latency_ms` | Hoàn thành |
| Hệ agent và điều phối | `src/agent_system.py` — `CoordinatorAgent.dispatch`, `process_case`, `verify_with_repair`, `normalize`, 6 sub-agent | 50 file `input/EC_xxx.json` | Output JSON đã qua kiểm chứng | Hoàn thành |
| Verifier | `src/verifier.py` — `verify_output` | Output draft + `OlistRepository` | Danh sách lỗi (rỗng = pass) | Hoàn thành |
| Runner và đóng gói | `main.py` — `main`, `write_metadata`, `package_output_zip` | `input/` | `output/EC_001..050.json`, `output.zip`, `trace.jsonl`, `metadata.json` | Hoàn thành |
| Audit trước khi nộp | `validate_submission.py` | Artifact đã ghi ra đĩa | Báo cáo ĐẠT/KHÔNG ĐẠT, exit code | Hoàn thành |
| Test luật nghiệp vụ | `tests/test_policy_engine.py` | Dữ liệu dựng sẵn | 31 assertion về các nhánh quyết định | Hoàn thành |
| Tài liệu kiến trúc | `architecture.md` | — | Sơ đồ agent, bảng quyền dữ liệu, mô tả giao thức | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Rà soát khai báo model của repo nhóm | `metadata.json`, `src/agent_system.py` | Phát hiện bản trên `main` khai `model_name: gpt-4o` nhưng `parameter_size: 7B` — sai ràng buộc "mỗi agent chỉ dùng model ≤ 10B". Nhánh `viet` chuyển sang `Qwen/Qwen2.5-7B-Instruct` (7.6B) và thêm bước tự kiểm tra ngưỡng 10B trong `validate_submission.py`. |
| Bổ sung script audit dùng chung được | `validate_submission.py` | Bất kỳ nhánh nào cũng chạy được để soi `output.zip`, `trace.jsonl`, `metadata.json` trước khi nộp. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Chạy pipeline trên 50 case chính thức | `main.py` | 50/50 output, 0 case lỗi, 6.0s | `python main.py` |
| Kiểm chứng lại từ đĩa | `validate_submission.py` | ĐẠT, exit code 0 | `python validate_submission.py` |
| Chốt các nhánh luật dễ sai | `tests/test_policy_engine.py` | 31/31 assertion PASS | `python tests/test_policy_engine.py` |
| Ghi trace A2A một lượt chạy | `trace.jsonl` | 700 message, 1 `run_id`, phủ đủ 50 case, đủ 6 sub-agent | Mục `[4]` trong output của validate |
| Đóng gói nộp bài | `output.zip` | 50 JSON `output/EC_001..050.json`, 0.05 MB, không file lạ | Mục `[3]` trong output của validate |

Output cụ thể phần việc của tôi tạo ra — phân bố nhãn trên 50 case (lấy từ `metadata.json`
mục `run.primary_issue_distribution`):

| primary_issue | Số case |
| --- | --- |
| `late_delivery_seller` | 10 |
| `late_delivery_logistics` | 10 |
| `unsupported_late_claim` | 8 |
| `canceled_order_paid` | 8 |
| `valid_split_payment` | 8 |
| `unavailable_order_paid` | 6 |

`case_status`: 34 `action_required` / 16 `no_action`; tổng refund đề xuất 3437.76 BRL.
Phân bố này phủ cả 6 nhánh của bảng chính sách và khá cân (10/10/8/8/8/6), phù hợp với một
bộ đề được thiết kế để kiểm tra đủ mọi nhánh — đây là tín hiệu cho thấy thứ tự ưu tiên đã
được cài đúng chứ không dồn hết về một nhãn mặc định.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Mỗi case chỉ cho một `claimed_order_id`; toàn bộ 40+ trường trong output phải được dựng lại
bằng cách join 9 bảng CSV, rồi áp một bảng chính sách có thứ tự ưu tiên. Hai rủi ro lớn nhất
là (1) kết luận sai nhánh vì áp luật không đúng thứ tự, và (2) sinh ra ID không tồn tại trong
CSV — bị tính là false positive.

### Cách triển khai

**Tầng dữ liệu.** Nạp 9 CSV đúng một lần rồi dựng sẵn các index dict: `orders_by_id`,
`items_by_order`, `payments_by_order`, `customers_by_id`, `orders_by_customer_unique`,
`products_by_id`. Item được sort theo `order_item_id`, payment theo `payment_sequential`, nên
thứ tự mọi mảng trong output là xác định, không phụ thuộc thứ tự dòng CSV. Null được chuẩn hóa
một lần tại đây (`""`/`nan`/`NaT` → `None`).

**Luật chính sách.** `determine_primary_issue` duyệt đúng thứ tự bảng EC_POLICY_V2 và trả về
kèm chuỗi lý do được ghi vào trace:

1. `canceled` + tổng payment > 0 → `canceled_order_paid`
2. `unavailable` + tổng payment > 0 → `unavailable_order_paid`
3. giao trễ (`delivery_variance_hours > 0`) và có ≥ 1 seller bàn giao sau `shipping_limit_date` → `late_delivery_seller`
4. giao trễ nhưng không seller nào muộn → `late_delivery_logistics`
5. ≥ 2 payment row và `|difference_brl| ≤ 0.10` → `valid_split_payment`
6. còn lại → `unsupported_late_claim`

`handoff_variance_hours` được tính theo **`shipping_limit_date` sớm nhất của từng seller**, nên
mỗi seller chỉ xuất hiện đúng một dòng trong `seller_handoff_analysis` dù order có nhiều item
của cùng seller. Với order không có item row, `expected_total_brl`, `difference_brl`,
`reconciled` trả `null` và các mảng item/seller/product/category/handoff để rỗng đúng như đề bài.

**Giao thức A2A.** Coordinator không tự tính gì: nó phát `REQUEST` cho từng sub-agent, nhận
`RESPONSE`, và mọi message đều có `msg_id` + `parent_msg_id` + `latency_ms` nên trace dựng lại
được cây handoff. PolicyAgent cố tình không có quyền đọc CSV — nó chỉ được kết luận trên bằng
chứng đã được bàn giao.

**Verifier.** Kiểm 5 nhóm: schema/tập giá trị hợp lệ, giới hạn mảng + thứ tự nghiệp vụ của
secondary issues và actions, grounding (mọi `item:`/`payment:`/`seller:`/`order:` phải khớp
CSV, `policy:` phải thuộc 6 root-cause code), null handling khi order không có item, và nhất
quán nghiệp vụ (refund ↔ `case_status`, root cause ↔ primary issue, tiền làm tròn 2 chữ số,
timestamp đúng `YYYY-MM-DD HH:MM:SS`). Khi có lỗi, Verifier trả `REPAIR_REQUIRED`, Coordinator
chạy `normalize()` rồi verify lại (tối đa 2 vòng).

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `input/EC_xxx.json` (`case_id`, `customer_request.claimed_order_id`, `investigation_scope`, `policy_version`) + 9 CSV Olist |
| Output | `output/EC_xxx.json` đúng schema đề bài; phụ trợ: `trace.jsonl`, `metadata.json`, `output.zip` |
| Module phụ thuộc | `src/data_engine.py` (dữ liệu), `src/policy_engine.py` (luật), `src/logger.py` (trace) |
| Module sử dụng output | `src/verifier.py`, `main.py`, `validate_submission.py` |
| Điều kiện lỗi cần xử lý | order không tồn tại trong CSV; order không có item row (6/50 case); order chưa giao nên `delivered_at`/`carrier_handoff_at` là null; payment lệch ngoài ngưỡng 0.10 BRL; console Windows cp1252 làm vỡ log tiếng Việt |

### Cách xác minh

```bash
python main.py
```

```bash
python validate_submission.py
```

```bash
python tests/test_policy_engine.py
```

- **Kết quả mong đợi:** 50/50 case qua Verifier; audit độc lập báo ĐẠT; toàn bộ assertion luật PASS.
- **Kết quả thực tế:** `main.py` — 50/50 case, 0 lần phải sửa, 6.0s, `output.zip` 50 JSON /
  0.05 MB. `validate_submission.py` — `[✓] ĐẠT`, exit code 0.
  `tests/test_policy_engine.py` — 31/31 assertion đạt.
- **Artifact/log:** `output/`, `output.zip`, `trace.jsonl`, `metadata.json` (mục `run`).
  Không artifact nào chứa API key hay secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Trường `product_context.category_names` lấy từ đâu — tên category gốc trong
  `olist_products_dataset.csv` (tiếng Bồ Đào Nha, ví dụ `beleza_saude`) hay bản dịch tiếng Anh
  qua `product_category_name_translation.csv` (`health_beauty`)? Bản trước trong repo nhóm
  đang dịch sang tiếng Anh.
- **Các phương án đã cân nhắc:** (1) dịch sang tiếng Anh cho dễ đọc; (2) giữ nguyên giá trị thô
  trong products CSV; (3) xuất cả hai — bất khả thi vì schema chỉ có một mảng.
- **Phương án đã chọn:** giữ nguyên `product_category_name` thô (phương án 2).
- **Lý do:** đề bài liệt kê các khóa join tới `products` nhưng **không** mô tả bất kỳ bước dịch
  nào trong `EC_POLICY_V2`, đồng thời yêu cầu "array phải giữ thứ tự ổn định theo dữ liệu
  nguồn" và "chỉ được nộp giá trị dựng trực tiếp từ dữ liệu". Bản dịch là một phép biến đổi
  thêm, không kiểm chứng được từ bảng `products`. Khi hai cách đọc đề đều hợp lý, tôi chọn cách
  bám sát dữ liệu gốc.
- **Bằng chứng quyết định phù hợp:** file dịch không nằm trong danh sách khóa join ở mục 2 của
  đề; ngoài ra tôi đã kiểm tra 50 case không có case nào `product_category_name` null, nên chọn
  giá trị thô không tạo thêm null. Quyết định được ghi thành docstring tại
  `OlistRepository.get_category_name` để reviewer biết đây là lựa chọn có chủ đích.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**
  `UnicodeEncodeError: 'charmap' codec can't encode character 'Đ' in position 4:
  character maps to <undefined>` — pipeline chết ngay dòng log đầu tiên, chưa xử lý được case nào.
- **Lệnh hoặc bước tái hiện:** `python main.py` trên Windows 11, console mặc định code page 1252.
- **Nguyên nhân gốc:** không phải lỗi dữ liệu. `sys.stdout` của Python trên Windows dùng
  encoding `cp1252`, không biểu diễn được ký tự tiếng Việt (`Đ`, `ã`...) trong log tiến độ. File
  JSON và trace vẫn ghi UTF-8 bình thường vì tôi mở file với `encoding="utf-8"` — chỉ có
  **stdout** là điểm chết.
- **Cách xử lý:** gọi `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (và tương tự
  cho `stderr`) ở đầu `main.py`, đặt sau phần import và có kiểm tra `hasattr` để không vỡ trên
  môi trường stdout không hỗ trợ reconfigure.
- **Cách xác minh sau khi sửa:** chạy lại `python main.py` — chạy hết 50 case, log tiếng Việt
  hiển thị đúng; sau đó `python validate_submission.py` báo ĐẠT.
- **Điều học được:** khi log bằng tiếng Việt, phải tách bạch encoding của *nội dung ghi file*
  và encoding của *console*. Ghi file đúng chưa đủ để pipeline chạy được, và một lỗi thuần
  hiển thị vẫn có thể chặn toàn bộ lượt chạy nếu nó nằm trên đường đi chính.

## 7. Hiểu biết về luồng end-to-end

> Bộ câu hỏi mẫu trong template được viết cho lab RAG/Crossref. Dưới đây tôi trả lời theo đúng
> tinh thần từng câu nhưng ánh xạ sang bài lab Multi-Agent A2A này.

**Câu trả lời:**

1. **Dữ liệu đi từ nguồn tới kết luận như thế nào?** `input/EC_xxx.json` chỉ đưa một
   `claimed_order_id`. Coordinator dùng nó tra `orders`, rồi phát REQUEST cho 4 agent thu thập
   bằng chứng: CustomerAgent (`customers` → `customer_unique_id` → các order khác),
   OrderProductAgent (`order_items` → seller/product → `products` → category), PaymentAgent
   (`order_payments` + item để đối soát), DeliveryAgent (mốc thời gian giao hàng và bàn giao).
   Bằng chứng hợp nhất mới được đưa cho PolicyAgent để áp EC_POLICY_V2, cuối cùng Verifier gác
   cổng trước khi ghi file.
2. **Ground-truth và cách đo chất lượng ở đây là gì?** Ground truth là chính 9 CSV Olist, không
   phải lời khiếu nại của khách. Vì vậy Verifier đo "đúng" theo hai trục: grounding (mọi ID
   trong output phải dựng lại được từ CSV) và nhất quán nội tại (refund ↔ `case_status`, root
   cause ↔ primary issue, `late_handoff_seller_ids` ↔ `seller_handoff_analysis`). Ngoài ra
   `tests/test_policy_engine.py` đo phần luật bằng dữ liệu dựng sẵn có đáp án biết trước.
3. **Kiểm chứng khác gì với chạy trơn tru?** Pipeline chạy hết 50 case mà không exception vẫn
   có thể sai âm thầm — ví dụ mảng vượt giới hạn hoặc evidence trỏ tới item không tồn tại.
   VerifierAgent kiểm *nội dung* từng case ngay trong luồng, còn `validate_submission.py` kiểm
   *bộ artifact* sau khi đã ghi ra đĩa (số file, nội dung zip, trace một lượt chạy, model ≤ 10B).
   Hai lớp này bắt hai loại lỗi khác nhau.
4. **Vì sao phải dùng lại đúng dữ liệu nguồn cho mọi lần chạy?** Vì kết quả phải tái lập được:
   rule-engine là hàm thuần, LLM chạy `temperature=0.0` và không được ghi vào output, `trace.jsonl`
   luôn reset đầu mỗi lượt. Nhờ vậy hai lần chạy trên cùng CSV cho ra output byte-for-byte giống
   nhau, và khi có khác biệt thì chắc chắn do code chứ không do ngẫu nhiên.
5. **Dựa vào artifact/metric nào để coi là hoàn tất?** `output/` đủ 50 JSON, `validate_submission.py`
   exit code 0, `tests/test_policy_engine.py` 31/31 PASS, `trace.jsonl` có đúng 1 `run_id` phủ
   50 case với đủ 6 sub-agent, `metadata.json` khai báo model 7.6B ≤ 10B, `output.zip` chứa đúng
   50 file JSON và không file lạ.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Đinh Quốc Việt
**Ngày xác nhận:** 2026-08-05
