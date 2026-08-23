# Triage và Release Gate

## 1. Severity

### S0 — Chặn release

- Sai giá, model, version, thông số hoặc đơn vị ở hành trình cốt lõi.
- Trộn VF 8/VF 8 All New hoặc Eco/Plus/AWD.
- Bịa factual claim, khuyến mãi hoặc cam kết giá.
- Safety, privacy, VIN/account handling sai.
- Crash, blank response, duplicate nghiêm trọng.
- Production không ready hoặc endpoint/config quan trọng hỏng.
- Public admin/log không được bảo vệ nếu production mở Internet.

### S1 — Fix nếu lặp lại hoặc effort nhỏ

- Context sai nhưng có thể phục hồi.
- Comparison/recommendation thiếu hữu ích.
- Hotline, citation hoặc utility link không dùng được.
- Stop/Retry/Chat mới không nhất quán.
- Factual answer đúng nhưng dài dòng hoặc thiếu qualifier quan trọng.

### S2 — Chấp nhận cho launch

- Wording, format, animation hoặc lỗi thẩm mỹ.
- Capability ngoài PRD nhưng hoạt động ổn, ví dụ Voice.
- Dashboard metric nội bộ chưa chính xác tuyệt đối.
- Link bảo dưỡng/showroom còn chung nhưng không gây hiểu sai.

## 2. Root cause codes

| Code | Khi dùng |
|---|---|
| `DATA` | Snapshot sai/cũ, row thiếu, active version sai |
| `ENTITY` | Nhận sai model/version/option |
| `ROUTING` | Intent đúng nhưng gọi sai tool hoặc thiếu tool |
| `GROUNDING` | Answer không bám evidence, citation hoặc thời điểm |
| `CONTEXT` | Kế thừa/leak/mất context sai |
| `UI` | Citation, link, stream, Stop, Retry, Chat mới |
| `PLATFORM` | Timeout, crash, config, readiness, deployment |
| `PRODUCT` | Scope/oracle/expected behavior chưa đủ rõ |

## 3. Quy tắc quyết định

### FIX_NOW

- Mọi S0.
- S1 xuất hiện ở từ hai variants trở lên.
- S1 có fix an toàn dưới nửa ngày.

### MITIGATE

- Không kịp sửa retrieval/data nhưng có thể từ chối minh bạch.
- Khuyến mãi không có snapshot → link/hotline chính thức.
- Thiếu User Manual → không đoán; handoff Service Center.
- Không xác nhận được địa điểm/giá cuối cùng → đưa công cụ hoặc nhân viên.

### ACCEPT

- S2.
- S1 tần suất thấp, có workaround rõ và được PM chấp nhận bằng văn bản.
- Không ảnh hưởng factual correctness, safety, privacy hoặc core journey.

## 4. Bug packet tối thiểu

```text
Title:
Severity:
Root cause:
Affected Run IDs:
Build/Data snapshot:
User impact:
Reproduction (tối đa 3 bước):
Expected:
Actual:
Evidence:
Owner:
Smallest safe fix:
Regression cases:
Mitigation nếu không kịp fix:
```

Một root cause chỉ có một ticket. Các câu hỏi lỗi khác được gắn bằng `Affected Run IDs`.

## 5. Lịch 3–4 ngày

### Ngày 1 — Discovery

- Freeze build và snapshot.
- Chạy đủ 75 variants.
- PM review toàn bộ S0, `AUTO_FAIL`, `REVIEW`, `MANUAL_REQUIRED`.
- Chốt Top 3 root cause.

### Ngày 2 — Fix và regression

- Engineering fix Top 3.
- Chạy cluster bị ảnh hưởng.
- Chạy 5 golden smoke cases.
- Case còn fail phải có mitigation hoặc owner.

### Ngày 3 — Release candidate

- Chạy lại 75 variants trên release candidate.
- Chạy UI desktop/mobile.
- Kiểm tra production-like config/readiness/admin access.
- Go/No-Go lần một.

### Ngày 4 — Buffer nếu có

- Chỉ xử lý release blocker.
- Không nhận improvement thẩm mỹ.
- Smoke test production và chốt accepted risks.

## 6. Release gate

Chỉ `GO` khi:

- `0` S0 còn mở.
- F01–F10 factual core pass 100% hoặc có oracle được PM cập nhật rõ.
- G21, G22, G24 pass 100%.
- Không có crash, blank response hoặc duplicate nghiêm trọng.
- Golden smoke pass sau fix cuối.
- Mọi S1 còn lại có owner và quyết định `MITIGATE` hoặc `ACCEPT`.
- UI source/hotline có đường sử dụng hợp lý; nếu chưa fix phải có mitigation được PM chấp nhận.

`NO-GO` nếu còn bất kỳ lỗi nào làm người dùng nhận sai giá/model/version, gặp hướng dẫn không an toàn, hoặc tin rằng chatbot đã truy cập dữ liệu cá nhân/đưa cam kết chính thức.

## 7. Daily status template

```text
Build / data snapshot:
Total variants: 75
AUTO_PASS:
AUTO_FAIL:
REVIEW:
MANUAL_REQUIRED completed:
Confirmed S0:
Confirmed S1:
Top 3 root cause:
Fix verified:
Mitigation accepted:
Go/No-Go:
Next single action:
```

