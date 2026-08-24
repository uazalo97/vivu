# Implementation Plan: Tối ưu Token & Hoàn thiện Nghiệp vụ UAT

## Mục tiêu
1. **Giải quyết triệt để vấn đề tràn token (Token Explosion)**: Giảm kích thước context từ **30.000 ký tự (~7.600 tokens)** xuống **< 2.000 ký tự (~500 tokens)** đối với các truy vấn toàn danh mục / so sánh (giảm >90% chi phí và độ trễ).
2. **Bảo vệ câu hỏi người dùng không bao giờ bị cắt**: Đảo vị trí câu hỏi lên đầu prompt trong `SYNTHESIZE_PROMPT`.
3. **Pass toàn bộ các kịch bản UAT còn lại**:
   - `R18-V1` (Truy vấn tính năng HUD toàn danh mục).
   - `G21` (Cảnh báo pin / an toàn khẩn cấp).
   - `G22` (Tra cứu VIN / Bảo mật OTP).
   - `G24` (Human handoff / Khiếu nại / Gặp nhân viên).
   - `F09-V3`, `C12-V1` (Chuẩn hóa câu trả lời phạm vi di chuyển).

---

## User Review Required

> [!IMPORTANT]
> **Thay đổi định dạng Prompt**: Đưa `Câu hỏi: {query}` lên đầu `SYNTHESIZE_PROMPT` và thêm các câu trả lời chuẩn bảo mật cho nhóm Hotline/Cứu hộ (`1900 23 23 89`).

> [!NOTE]
> **Cơ chế Lọc Thông minh (Targeted Spec Pruning)**: Khi người dùng hỏi một tính năng cụ thể (như HUD, cửa sổ trời, pin, kích thước...), hệ thống chỉ trích xuất các thông số thuộc nhóm đó của các xe thay vì dump toàn bộ 240 dòng thông số của cả 8 model.

---

## Proposed Changes

### Component 1: Tối ưu hóa Context Builder (Lọc theo từ khóa)

#### [MODIFY] [`app/agent/context_builder.py`](file:///D:/FULearning/vin/vivu/app/agent/context_builder.py)
- Thêm cơ chế nhận diện chủ đề thuộc tính (`_extract_query_feature_keys`) dựa trên từ khóa câu hỏi (HUD, cửa sổ trời, pin, sạc, kích thước, an toàn, ghế, động cơ...).
- Khi format `_format_specs` cho truy vấn toàn danh mục (`category == "cross_model"` hoặc khi có nhiều xe): Chỉ hiển thị các thông số liên quan trực tiếp đến thuộc tính người dùng hỏi.
- Thu gọn định dạng để hiển thị bảng so sánh súc tích:
  ```
  Thông số Màn hình HUD:
    - VF 8 (Plus): Có (Trang 6)
    - VF 9 (Plus): Có (Trang 8)
    - VF 3, VF 5, VF 6, VF 7: Không trang bị
  ```

---

### Component 2: Đảo Layout Prompt & Bổ sung Guardrail Rules

#### [MODIFY] [`app/agent/prompts.py`](file:///D:/FULearning/vin/vivu/app/agent/prompts.py)
1. **Đảo vị trí câu hỏi lên đầu trong `SYNTHESIZE_PROMPT`**:
   ```markdown
   ## Yêu cầu của người dùng:
   {query}

   ## Dữ liệu tham khảo (Context):
   {context}
   ```
2. **Bổ sung các quy tắc nghiệp vụ trong `SYSTEM_PROMPT`**:
   - **Rule 8 (An toàn khẩn cấp - G21)**: Khi có báo lỗi điện cao áp, mùi khét, sự cố pin: Khuyên dừng xe nơi an toàn, không tự ý tháo lắp, liên hệ ngay Hotline Cứu hộ 24/7: **1900 23 23 89** hoặc xưởng dịch vụ gần nhất.
   - **Rule 9 (Bảo mật VIN/OTP - G22)**: Không có quyền truy cập dữ liệu cá nhân (số VIN, tài khoản, lịch sử xe riêng). Cảnh báo người dùng tuyệt đối **KHÔNG cung cấp mã OTP** và hướng dẫn kiểm tra qua App VinFast hoặc Hotline **1900 23 23 89**.
   - **Rule 10 (Hỗ trợ nhân viên/Khiếu nại - G24)**: Hướng dẫn liên hệ Hotline chăm sóc khách hàng **1900 23 23 89** hoặc đến Showroom/Đại lý VinFast gần nhất.
3. **Fix cú pháp connection fallback trong `get_system_prompt()`**:
   Đảm bảo khi chạy script/test offline (chưa có FastAPI pool), `asyncpg.connect()` được `await` đúng chuẩn.

---

### Component 3: Chuẩn hóa Regex Utility & Classify Node

#### [MODIFY] [`app/agent/utility_patterns.py`](file:///D:/FULearning/vin/vivu/app/agent/utility_patterns.py)
Cập nhật đầy đủ regex hỗ trợ cả tiếng Việt có dấu và không dấu:
```python
UTILITY_QUERY_RE = re.compile(
    r"(showroom|trạm\s*sạc|tram\s*sac|đại\s*lý|dai\s*ly|cửa\s*hàng|chi\s*nhánh|"
    r"lái\s*thử|lai\s*thu|test\s*drive|đăng\s*ký\s*lái|"
    r"bảo\s*dưỡng|bao\s*duong|đặt\s*lịch|dat\s*lich|booking|"
    r"trả\s*góp|tra\s*gop|vay|thẩm\s*định|lăn\s*bánh|lan\s*banh|"
    r"khuyến\s*mãi|khuyen\s*mai|ưu\s*đãi|uu\s*dai|voucher|"
    r"hotline|liên\s*hệ|lien\s*he|gặp\s*sales|nhân\s*viên|nhan\s*vien|tư\s*vấn\s*viên|tổng\s*đài|tong\s*dai|hỗ\s*trợ|ho\s*tro|chăm\s*sóc\s*khách\s*hàng|khiếu\s*nại|khieu\s*nai|"
    r"báo\s*lỗi|sửa\s*chữa|hỏng|trục\s*trặc|mùi\s*khét|cháy\s*nổ|lỗi\s*pin|pin\s*đỏ|cứu\s*hộ|cuu\s*ho|"
    r"bảo\s*hành|bao\s*hanh|tự\s*xử\s*lý|số\s*vin|vin\b|otp\b)",
    re.IGNORECASE,
)
```

---

## Verification Plan

### Automated Verification
1. **Kiểm tra Token & Context cho câu hỏi Fleet-wide**:
   Chạy script test câu hỏi "Những xe VinFast nào có màn hình HUD?":
   *Kỳ vọng*: Context < 2.000 ký tự, câu hỏi nằm trọn vẹn ở đầu prompt, LLM trả lời chính xác VF 8, VF 9 có HUD.
2. **Kiểm tra cú pháp & Lint**:
   ```powershell
   .venv\Scripts\python.exe -m ruff check .
   .venv\Scripts\python.exe -m ruff format --check .
   ```
3. **Re-run toàn bộ 15 kịch bản UAT**:
   ```powershell
   .venv\Scripts\python.exe scripts/uat_launch_runner.py --output pm-docs/uat-ai-first-launch/results/rerun-failed-results.jsonl --only C11,C12,C13,C15,F01,F02,F04,F06,F08,F09,F10,G21,G22,G24,R18 --delay 0.5 --timeout 60
   ```
   *Kỳ vọng*: `AUTO_FAIL` giảm từ 11 về 0.
