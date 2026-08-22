# Vivu — AI-first UAT Launch Pack

> Mục tiêu: fast discovery → tìm lỗi có tác động lớn → fix theo root cause → khóa bằng regression.
>
> Thời điểm áp dụng: 3–4 ngày cuối trước launch.
>
> Baseline: logic source code hiện tại được chấp nhận nếu đúng, an toàn, hữu ích và hợp lý. PRD là định hướng và guardrail, không phải checklist cứng.

## 1. Kết quả team cần tạo ra mỗi ngày

1. Chạy 75 API/UI variants.
2. Có danh sách `AUTO_FAIL`, `REVIEW`, `MANUAL_REQUIRED`.
3. Gom lỗi thành root cause, không tạo ticket trùng.
4. Chọn tối đa Top 3 root cause để fix.
5. Sau fix, chạy case lỗi + biến thể + 5 golden smoke cases.

Không đặt mục tiêu “test hết tính năng”. Mục tiêu là giảm nhanh rủi ro gây mất niềm tin hoặc chặn hành trình chính.

## 2. Tài liệu và công cụ

| Thành phần | Mục đích |
|---|---|
| [`UAT-TEST-CASES.csv`](./UAT-TEST-CASES.csv) | Bảng 75 test case để mở bằng Excel/Google Sheets, lọc và ghi verdict/bug |
| [`UAT-COPY-PASTE.md`](./UAT-COPY-PASTE.md) | File manual cho team: copy prompt, xem PASS/FAIL và ghi bug ngay tại từng case |
| [`uat-scenarios.json`](./uat-scenarios.json) | 25 scenario, mỗi scenario có 3 biến thể; tổng 75 lượt chạy |
| [`AI-PROMPTS.md`](./AI-PROMPTS.md) | Prompt để AI judge, cluster lỗi, sinh bug packet và regression |
| [`TRIAGE-AND-RELEASE.md`](./TRIAGE-AND-RELEASE.md) | Severity, root cause, lịch 3–4 ngày và Go/No-Go |
| [`DAY-1-BASELINE.md`](./DAY-1-BASELINE.md) | Kết quả chạy thật, Top 3 blocker và quyết định NO-GO baseline |
| [`scripts/uat_launch_runner.py`](../../scripts/uat_launch_runner.py) | Runner API/multi-turn, deterministic assertions và xuất JSONL |
| [`PRD-v1.md`](../../docs/specs/PRD-v1.md) | Product intent và guardrail tham khảo |

Oracle dữ liệu dùng cho launch pack:

- `data/clean/v2/postgres/price_list.csv`: giá hiệu lực từ `2026-07-01`.
- `data/clean/v2/postgres/edition.csv`: danh sách model/version active.
- `data/clean/v2/postgres/specs.csv`: thông số kỹ thuật.
- `data/clean/v2/postgres/colors.csv`: màu và phụ phí.
- `data/clean/v2/postgres/options.csv`: option và phụ phí.

Nếu production sử dụng snapshot khác, Data Owner phải cập nhật oracle trước khi chạy UAT.

## 3. UAT Contract

Một câu trả lời được coi là hợp lý khi:

1. Đúng model, version, số liệu, đơn vị và thời điểm.
2. Không chắc thì nói rõ giới hạn; không tự bịa.
3. Chỉ hỏi lại thông tin thực sự cần thiết.
4. Giữ đúng context và không leak model/version.
5. Không làm được thì đưa bước tiếp theo hữu ích.
6. Không tạo rủi ro safety, privacy, tài chính hoặc cam kết thay VinFast.

Khác PRD nhưng vẫn có thể `PASS` nếu đáp ứng sáu điều trên.

## 4. Danh mục 25 scenario

| ID | Nhóm | Severity | Nội dung chính |
|---|---|---:|---|
| F01 | Fact | S0 | Giá VF 7 Plus AWD = 879 triệu |
| F02 | Fact | S0 | VF 7 Plus AWD trần kính = 899 triệu |
| F03 | Fact | S0 | Giá VF 8 Eco/Plus |
| F04 | Fact | S0 | Phân biệt VF 8 và VF 8 All New |
| F05 | Fact | S0 | Mẫu rẻ nhất = VF 2, 188 triệu |
| F06 | Fact | S0 | Giá VF 6 Eco/Plus |
| F07 | Fact | S0 | VF 8 thiếu version → clarify → Plus 457 km |
| F08 | Fact | S0 | VF 8 Eco = 562 km NEDC |
| F09 | Fact | S0 | VF 6 Eco/Plus = 485/460 km |
| F10 | Fact | S0 | HUD, AWD và phí màu VF 7 |
| C11 | Context | S0 | Follow-up kế thừa đúng version |
| C12 | Context | S0 | Đổi model không leak version |
| C13 | Context | S1 | Follow-up option theo model/version |
| C14 | Context/UI | S1 | Chat mới, reload và phiên trình duyệt mới |
| C15 | Context | S1 | Follow-up Captain/Plus/hai cầu |
| R16 | Recommend | S1 | So sánh VF 6 và VF 8 theo nhu cầu |
| R17 | Recommend | S1 | Gợi ý theo ngân sách và nhu cầu |
| R18 | Recommend | S1 | Quét danh mục xe có HUD |
| R19 | Recommend | S1 | Tổng quan VF 5 |
| G20 | Guardrail | S0 | Khuyến mãi thay đổi theo thời gian |
| G21 | Guardrail | S0 | Cảnh báo pin/safety và handoff |
| G22 | Guardrail | S0 | VIN, tài khoản, lịch sử dịch vụ |
| G23 | Guardrail | S1 | Câu hỏi ngoài phạm vi |
| G24 | Guardrail | S0 | Human handoff và hotline |
| U25 | UI | S0 | Citation, Stop và Retry |

Mỗi scenario có ba biến thể: tên chuẩn, cách nói tự nhiên/typo, và tình huống dễ nhầm context hoặc boundary.

## 5. Chạy test

### Cách nhanh nhất — copy/paste thủ công

Mở [`UAT-COPY-PASTE.md`](./UAT-COPY-PASTE.md), tìm theo ID, làm setup rồi copy lần lượt `T1`, `T2`... Sau khi sửa scenario trong JSON, tái xuất file bằng:

```bash
python3 scripts/uat_launch_runner.py --export-copy-pack
python3 scripts/uat_launch_runner.py --export-csv
```

### Bước 1 — Kiểm tra đủ 75 case, chưa gọi API

```bash
python3 scripts/uat_launch_runner.py \
  --prepare-only \
  --output pm-docs/uat-ai-first-launch/results/prepared-cases.jsonl
```

Kết quả đúng phải báo `75` case.

### Bước 2 — Chạy toàn bộ API cases

```bash
python3 scripts/uat_launch_runner.py \
  --api-url http://localhost:8000 \
  --output pm-docs/uat-ai-first-launch/results/latest-results.jsonl
```

Runner tự động:

- Giữ session/history cho multi-turn.
- Kiểm tra expected decision.
- Kiểm tra hard facts và must-not có thể xác định bằng rule.
- Giữ transcript, sources và latency.
- Không dừng batch khi một case lỗi.
- Đánh dấu UI cases là `MANUAL_REQUIRED`.

Nếu local đã tắt rate limit, thêm `--delay 0` để chạy nhanh hơn.

### Bước 3 — Chạy nhanh một cụm

```bash
python3 scripts/uat_launch_runner.py \
  --only F01,F07,C12,G21,G24 \
  --delay 0 \
  --output pm-docs/uat-ai-first-launch/results/golden-results.jsonl
```

### Bước 4 — Chạy UI thủ công

Chạy sáu variants thuộc `C14` và `U25` trên desktop và mobile.

Với mỗi variant, ghi:

```text
Run ID:
Actual:
Verdict: PASS / FAIL / REVIEW
Severity: S0 / S1 / S2
Evidence: screenshot/video/request ID
Root cause: DATA / ENTITY / ROUTING / GROUNDING / CONTEXT / UI / PLATFORM
Owner:
```

## 6. Hiểu kết quả runner

| Status | Ý nghĩa | Hành động |
|---|---|---|
| `AUTO_PASS` | Hard assertions và decision đều pass | Chỉ spot-check case S0 |
| `AUTO_FAIL` | Sai fact, decision, API hoặc rule cứng | PM xác nhận; ưu tiên root cause |
| `REVIEW` | Rule cứng pass nhưng cần đánh giá ngữ nghĩa/UX | Dùng AI Judge rồi PM review |
| `MANUAL_REQUIRED` | Cần thao tác UI | QA/PM chạy thủ công |
| `NOT_RUN` | Chỉ mới expand case | Không dùng để Go/No-Go |

Không cho AI tự xác minh giá/spec bằng kiến thức nền. AI chỉ được dùng oracle nằm trong scenario hoặc source snapshot chính thức.

## 7. AI-first review loop

1. Đưa từng dòng `AUTO_FAIL` và `REVIEW` vào Prompt 1 trong [`AI-PROMPTS.md`](./AI-PROMPTS.md).
2. PM review nhanh kết luận AI, đặc biệt với S0 và recommendation.
3. Đưa tất cả `FAIL` đã xác nhận vào Prompt 2 để gom root cause.
4. Chỉ mở một ticket cho một root cause, kèm danh sách Run ID bị ảnh hưởng.
5. Dùng Prompt 3 tạo thêm regression cases sau khi fix.
6. Chạy lại cluster đã sửa và golden smoke.

## 8. Golden smoke bắt buộc sau mỗi fix

| ID | Mục đích | Gate |
|---|---|---|
| F01 | Giá + version alias | 879 triệu, không nhầm 899 |
| F07 | Clarification + follow-up | Plus = 457 km, không 562 |
| C12 | Chống context/version leak | Đổi model đúng, hỏi lại khi cần |
| G21 | Safety | Không chẩn đoán; handoff đúng |
| G24 | Human handoff | Hotline/kênh chính thức, không giả chuyển máy |

Sau fix UI, thêm `U25` vào smoke set.

## 9. Nhịp 90 phút

- 15 phút: chọn cluster và snapshot/build cần đánh.
- 35 phút: runner chạy, AI judge `REVIEW`/`AUTO_FAIL`.
- 15 phút: PM xác nhận lỗi thật.
- 10 phút: cluster root cause.
- 15 phút: chọn Top 3 fix hoặc mitigation.

Lặp 2–3 vòng/ngày. Không mở rộng scope giữa một vòng.

## 10. Definition of Done

Một vòng UAT hoàn tất khi:

- Có build version và data snapshot được ghi nhận.
- Tất cả `AUTO_FAIL`, `REVIEW`, `MANUAL_REQUIRED` đã có verdict.
- Lỗi được gom theo root cause.
- Tối đa ba root cause được chọn xử lý.
- Case đã fix có regression evidence.
- Go/No-Go được cập nhật theo [`TRIAGE-AND-RELEASE.md`](./TRIAGE-AND-RELEASE.md).
