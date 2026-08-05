# Member Role Report — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Trung Long |
| Mã học viên | 2A202601514 |
| Khóa/Lớp | K4 |
| Vai trò chính | Multi-Agent System Architect & Lead Implementer |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Thiết kế workflow multi-agent | `src/graph.py`, `src/state.py`, `architecture.md` | Một case khiếu nại và các báo cáo agent | Luồng điều phối specialist → policy → verifier, có revision loop | Hoàn thành về mặt triển khai |
| Agent runtime và A2A handoff | `src/agents/runtime.py`, `src/agents/specialists.py`, `src/agents/policy_adjudicator.py`, `src/agents/verifier.py` | System prompt, nhiệm vụ, tool allow-list và dữ liệu case | Báo cáo có cấu trúc, policy decision và verification result | Hoàn thành về mặt triển khai |
| Tool layer và truy xuất dữ liệu | `src/tools/` | `claimed_order_id` và tham số tool | Dữ liệu Olist theo từng miền, phép tính tiền/thời gian và kiểm tra evidence | Hoàn thành |
| Data contracts và output schema | `src/models/`, `src/output_writer.py` | Kết quả từ các agent | JSON theo schema yêu cầu | Hoàn thành |
| Batch runner, concurrency và tracing | `src/main.py`, `run.py`, `src/tracing.py` | 50 file `input/EC_xxx.json` | 50 file trong `output/`, trace JSONL và `output.zip` | Hoàn thành về mặt vận hành |
| Tích hợp model/provider | `provider.py`, `src/config.py`, `.env.example`, `logging/metadata.json` | API key từ `.env` | OpenAI-compatible runtime sử dụng `gpt-4o-mini` | Hoàn thành, còn rủi ro compliance về số tham số không công bố |
| Kiểm thử nền tảng | `tests/` | Fixtures và dữ liệu đầu vào giả lập | Test contracts, tools, CLI, agent contracts và verifier | Đã xây dựng, chưa đủ để dự đoán hidden leaderboard |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Chuẩn hóa kiến trúc và tài liệu | Nhóm dự án | Viết `architecture.md`, mô tả quyền truy cập, handoff, revision và failure handling |
| Chuẩn bị artifact nộp bài | Nhóm dự án | Sinh `output/EC_001.json` đến `output/EC_050.json`, `output.zip`, trace và metadata |
| Phân tích kết quả sau chấm | Nhóm dự án | Xác định khoảng cách giữa internal validation và semantic correctness của hidden grader |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng graph điều phối bốn specialist chạy song song | `src/graph.py` | Customer, Order/Product, Payment và Delivery Agent chạy concurrent trước Policy Agent | Đọc `SPECIALISTS`, `ThreadPoolExecutor` và `run_case_async()` |
| Giới hạn quyền tool theo từng agent | `src/agents/runtime.py`, `src/tools/registry.py` | Mỗi agent chỉ được gọi tool trong allow-list | Kiểm tra cấu hình `allowed_tools` ở từng agent call |
| Triển khai Policy Adjudicator dựa trên policy text | `src/agents/policy_adjudicator.py`, `src/policies/EC_POLICY_V2.md` | Model đọc dossier và tạo `PolicyDecision`/`FinalCaseOutput` | Chạy một case và xem event `policy_decision_created` trong trace |
| Triển khai verifier độc lập và revision loop | `src/agents/verifier.py`, `src/graph.py` | Trả `VERIFIED` hoặc `REVISION_REQUIRED`, retry có giới hạn | Kiểm tra `deterministic_checks()` và `max_revisions` |
| Tạo pipeline xử lý batch | `src/main.py`, `run.py` | Xử lý 50 input, ghi output và dừng khi vượt ngưỡng lỗi | `python run.py --case-id EC_001` và `python run.py` |
| Tạo artifact đầu ra | `output/`, `output.zip`, `logging/trace.jsonl`, `logging/metadata.json` | Có đủ output `EC_001.json` đến `EC_050.json` trong branch | Kiểm tra thư mục `output/` và file ZIP |

### Kết quả thực tế

Hệ thống đã chạy thành công về mặt vận hành và tạo đủ 50 file đầu ra. Tuy nhiên, kết quả leaderboard chỉ đạt **2/100 điểm**. Điểm số này cho thấy việc pipeline chạy hết, output đúng schema và verifier nội bộ trả pass không đồng nghĩa với việc các trường nghiệp vụ khớp ground truth của hệ thống chấm.

Kết quả quan trọng nhất của phần việc là một kiến trúc multi-agent hoàn chỉnh, có specialist agents, restricted tools, handoff, tracing, policy reasoning và revision loop. Hạn chế lớn nhất là chưa có một bộ reference evaluation đủ mạnh để phát hiện sai lệch semantic trước khi nộp.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Một case khiếu nại Olist cần tổng hợp dữ liệu từ nhiều bảng khác nhau: customer, order, item, product, seller, payment và delivery timestamp. Hệ thống cần tách trách nhiệm theo miền, tránh cho một agent duy nhất truy cập toàn bộ dữ liệu và tự tạo kết luận không thể kiểm chứng.

Ngoài việc trả kết quả đúng schema, hệ thống còn phải thể hiện được quá trình agent-to-agent thực tế, giới hạn quyền truy cập, trace tool call và cơ chế kiểm tra độc lập trước khi ghi output.

### Cách triển khai

Tôi triển khai kiến trúc explicit state graph gồm các bước:

1. Coordinator nhận input case và tạo assignment cho bốn specialist agents.
2. Customer Investigator, Order/Product Investigator, Payment Auditor và Delivery Investigator chạy song song.
3. Mỗi specialist sử dụng system prompt riêng và chỉ được gọi nhóm tool thuộc domain của mình.
4. Coordinator tổng hợp bốn structured report thành `investigation_dossier`.
5. Policy Adjudicator không được truy cập raw CSV; agent đọc `EC_POLICY_V2` và dossier để sinh quyết định cùng final output.
6. Verifier Agent kiểm tra candidate với dossier, gọi tool kiểm tra evidence và giới hạn mảng, sau đó trả `VERIFIED` hoặc `REVISION_REQUIRED`.
7. Nếu verifier từ chối, graph gửi defect trở lại Policy Agent hoặc specialist liên quan; số vòng sửa được giới hạn.
8. Output chỉ được ghi khi state có `final_output`.

Phần deterministic được sử dụng cho những tác vụ không nên giao cho LLM: load và index CSV, phép tính tiền bằng `Decimal`, phép tính timestamp, kiểm tra evidence tồn tại, Pydantic schema validation, array limit và serialization.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `input/EC_xxx.json`, gồm `case_id`, `claimed_order_id`, investigation scope và policy version |
| Shared state | `InvestigationState` chứa specialist reports, dossier, policy decision, verifier result, revision count và errors |
| Output | `output/EC_xxx.json` theo 11 top-level sections của đề bài |
| Model | `gpt-4o-mini` qua OpenAI SDK |
| Tool/data dependency | `DataStore`, `ToolRegistry`, các CSV Olist và policy document |
| Failure handling | Provider error, invalid JSON, invalid Pydantic output, missing record, verifier rejection và revision limit |

### Cách xác minh

```bash
python -m pytest -q
python run.py --dry-run
python run.py --case-id EC_001
python run.py
```

- **Kết quả mong đợi:** test nền tảng pass, datastore load được, một case chạy độc lập, sau đó xử lý đủ 50 case và tạo output đúng schema.
- **Kết quả thực tế đã ghi nhận:** branch chứa đủ 50 output JSON và `output.zip`; pipeline không bị lỗi vận hành ở lần chạy cuối. Tuy nhiên hidden leaderboard chỉ đạt **2/100**, nên semantic correctness chưa đạt yêu cầu.
- **Artifact/log:** `output/`, `output.zip`, `logging/trace.jsonl`, `logging/metadata.json`, commit `3ac4006` (`feat: first run success`).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần chứng minh đây là hệ thống multi-agent thực sự, không phải một prompt duy nhất hoặc một rule engine được đổi tên thành agent.
- **Các phương án đã cân nhắc:**
  1. Một hàm deterministic đọc toàn bộ dữ liệu và áp policy trực tiếp.
  2. Một LLM duy nhất nhận toàn bộ CSV context và sinh final JSON.
  3. Nhiều specialist agent với tool riêng, Policy Adjudicator không có raw-data access và Verifier độc lập.
- **Phương án đã chọn:** Phương án 3.
- **Lý do:** Có separation of concerns, least-privilege tool access, traceable handoff và revision workflow; kiến trúc phản ánh đúng yêu cầu multi-agent của bài.
- **Trade-off:** Mỗi lần suy luận qua LLM tạo thêm rủi ro stochastic error. Việc để Policy Adjudicator sinh toàn bộ final output khiến một lỗi reasoning có thể ảnh hưởng đồng thời nhiều field.
- **Bằng chứng:** `src/graph.py` điều phối bốn specialist, `src/agents/policy_adjudicator.py` không bind raw-data tools, và `src/agents/verifier.py` là bước xác minh riêng. Tuy nhiên điểm 2/100 cho thấy kiến trúc đúng chưa đủ; cần thêm reference oracle và evaluation theo field.

## 6. Một lỗi hoặc blocker đã xử lý

### Blocker: Internal verifier pass nhưng leaderboard chỉ đạt 2/100

- **Triệu chứng:** Hệ thống tạo đủ 50 output và vượt qua schema/evidence checks nội bộ, nhưng điểm chấm cuối chỉ là **2/100**.
- **Bước tái hiện:** Chạy pipeline để tạo `output.zip`, nộp archive lên leaderboard và nhận kết quả 2/100.
- **Nguyên nhân gốc:** Chưa thể khẳng định hoàn toàn vì không có detailed grader report. Phân tích code cho thấy verifier deterministic hiện chủ yếu kiểm tra Pydantic schema, business shape, array limit và evidence existence. Phần kiểm tra policy semantics vẫn phụ thuộc vào một LLM verifier đọc cùng dossier với Policy Agent, nên lỗi reasoning có thể tương quan và không bị phát hiện.
- **Phạm vi bị ảnh hưởng:** `case_assessment`, root cause, responsible parties, evidence selection, refund và action ordering; một quyết định policy sai có thể kéo sai nhiều section cùng lúc.
- **Những gì đã loại trừ:** Không phải do thiếu số lượng output vì branch có `EC_001.json` đến `EC_050.json`; không phải do pipeline dừng giữa chừng; output đã qua Pydantic và evidence-format checks nội bộ.
- **Cách xử lý đã thực hiện:** Ghi nhận vấn đề, đối chiếu kiến trúc với cách chấm theo field và xác định cần tách structural validation khỏi semantic evaluation.
- **Bước tiếp theo có thể kiểm chứng:**
  1. Xây deterministic reference evaluator cho toàn bộ `EC_POLICY_V2`.
  2. So sánh agent output với reference theo từng JSON path trước khi cho phép ghi file.
  3. Tạo representative tests cho cả sáu primary issues và các case priority conflict.
  4. Không để LLM sinh lại các field factual đã có trong specialist reports; final assembler phải copy deterministic.
  5. Chọn model có số tham số được công bố rõ ràng để bảo đảm điều kiện `<=10B`.
- **Điều học được:** Schema validity và self-consistency không phải correctness. Với hidden benchmark, cần một evaluation oracle độc lập và các regression tests bám sát scoring rubric, thay vì chỉ tin vào verifier do cùng loại model sinh ra.

## 7. Hiểu biết về luồng end-to-end

### 1. Dữ liệu đi qua hệ thống như thế nào?

`src/main.py` đọc input theo thứ tự tên file và khởi tạo `DataStore`. Mỗi case được đưa vào state graph. Bốn specialist agent truy vấn dữ liệu thông qua `ToolRegistry`, tạo structured report và gửi về Coordinator. Coordinator tạo dossier, Policy Adjudicator áp dụng policy, Verifier kiểm tra candidate, sau đó `output_writer` ghi JSON.

### 2. Vì sao không cho Policy Agent truy cập raw CSV?

Policy Agent chỉ nên phân xử trên các facts đã được specialist agents thu thập và chuẩn hóa. Điều này giảm context, tránh truy xuất tùy tiện và cho phép trace rõ claim nào đến từ agent nào. Nếu thiếu dữ liệu, Policy Agent phải yêu cầu điều tra lại thay vì tự truy cập bảng khác.

### 3. Deterministic tools khác agent reasoning ở đâu?

Tool chịu trách nhiệm trả dữ liệu nguồn và tính toán chính xác. Agent quyết định cần gọi tool nào, diễn giải kết quả và tạo report. Money, timestamp, schema và evidence existence phải deterministic; policy interpretation và task delegation được thực hiện bởi agent.

### 4. Verifier hiện kiểm tra được gì và còn thiếu gì?

Verifier kiểm tra schema, business shape, array limit và evidence existence, đồng thời dùng LLM để đánh giá candidate với dossier. Phần còn thiếu là một expected decision được tạo độc lập và chính xác theo policy, đủ để so sánh exact match ở từng field.

### 5. Vì sao điểm leaderboard thấp dù pipeline chạy đủ?

Pipeline success chỉ chứng minh hệ thống không crash và tạo được file. Leaderboard đo độ đúng của từng trường so với hidden ground truth. Khi Policy Agent hoặc Verifier hiểu sai priority, evidence, refund hay action ordering, output vẫn có thể hợp lệ về schema nhưng sai gần như toàn bộ nội dung chấm điểm.

### 6. Nếu làm lại, ưu tiên thay đổi gì?

Tôi sẽ giữ specialist agents và A2A trace để đáp ứng yêu cầu kiến trúc, nhưng thêm deterministic reference evaluator, final assembler và field-level diff. LLM chỉ nên quyết định phần policy cần reasoning; dữ liệu factual phải được copy trực tiếp từ specialist reports thay vì được model sinh lại.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đạt kết quả tốt” hoặc “đúng 100%” khi leaderboard thực tế chỉ đạt 2/100.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo phân biệt rõ kết quả vận hành với chất lượng semantic.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc thành viên khác.

**Họ và tên:** Nguyễn Trung Long  
**Mã học viên:** 2A202601514  
**Ngày xác nhận:** 2026-08-05
