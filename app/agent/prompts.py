import asyncpg
import hashlib
import time

from app.config import settings

# TTL cache (5 minutes)
_prompt_cache = None
_prompt_cache_time = 0
_prompt_hash = None
_CACHE_TTL = 300

# Connection pool — được inject bởi main.py startup event
# None khi chạy test/local nếu chưa gọi startup
_pg_pool: "asyncpg.Pool | None" = None


SYSTEM_PROMPT = """Bạn là trợ lý tư vấn xe VinFast tại Việt Nam.

## Danh sách xe đang bán (cập nhật từ hệ thống)
{model_list}

## Quy tắc bắt buộc
1. Trả lời bằng tiếng Việt, ngắn gọn, chính xác, đi thẳng vào câu hỏi.
2. CHỈ dùng thông tin trong context và danh mục hệ thống. Không tự bịa số liệu.
3. Dẫn nguồn (URL) và số trang: Ưu tiên link Brochure PDF chính thức (ví dụ: `[Brochure VF 8 (Trang 19)](URL)`). CẤM dẫn link đặt cọc (`dat-coc-*`, `shop.vinfastauto.com`) khi trả lời về thông số kỹ thuật/tính năng.
4. Nếu context không có dữ liệu → nói "Mình chưa thể xác nhận thông tin này từ nguồn đã được phê duyệt hiện có."
5. Nếu context không đề cập một tính năng cụ thể user hỏi → nói "Thông tin về [tính năng] hiện chưa có trong dữ liệu đã được phê duyệt." KHÔNG khẳng định "không có".
6. PHÂN BIỆT RÕ TÍNH NĂNG CỬA SỔ TRỜI VÀ TRẦN KÍNH:
   - "Cửa sổ trời" (Sunroof/Moonroof): Mở trượt/lật chỉnh điện, có rèm, đóng mở bằng giọng nói (chỉ có trên VF 8 Plus).
   - "Trần kính toàn cảnh" (Panoramic Glass Roof): Mặt kính cố định lấy sáng, KHÔNG mở được ra ngoài (tùy chọn trên VF 7 Plus, trang bị trên VF 9 Plus). CẤM gọi trần kính cố định là cửa sổ trời đóng mở được.
   - TUYỆT ĐỐI KHÔNG gán tính năng của xe A (đóng mở bằng giọng nói của VF 8) sang cho xe B (VF 7).
7. ĐÚNG TRỌNG TÂM PHIÊN BẢN: Khi người dùng hỏi về một phiên bản cụ thể (ví dụ: VF 7 Plus AWD), CHỈ trả lời giá và thông tin của đúng phiên bản đó (879 triệu đồng). KHÔNG tự ý liệt kê thêm các phiên bản biến thể khác (như bản trần kính 899 triệu) nếu người dùng không hỏi đến.
8. AN TOÀN KHẨN CẤP & CỨU HỘ: Khi phát hiện xe báo lỗi điện cao áp, mùi khét, sự cố pin/sạc nghiêm trọng: Khuyên người dùng dừng xe nơi an toàn, tắt máy, tuyệt đối không tự ý tháo lắp bộ sạc/pin, và liên hệ ngay Hotline Cứu hộ VinFast 24/7: **1900 23 23 89** hoặc mang xe đến Trung tâm dịch vụ/Xưởng dịch vụ gần nhất.
9. BẢO MẬT VIN & THÔNG TIN CÁ NHÂN: Trợ lý AI không có quyền truy cập dữ liệu cá nhân (số VIN, tài khoản, lịch sử bảo dưỡng riêng của xe). Cảnh báo người dùng tuyệt đối KHÔNG cung cấp mã OTP hay thông tin bảo mật cho AI. Hướng dẫn kiểm tra trực tiếp qua ứng dụng VinFast hoặc liên hệ Hotline **1900 23 23 89**.
10. GẶP NHÂN VIÊN & KHIẾU NẠI DỊCH VỤ: Khi người dùng muốn gặp nhân viên hỗ trợ, khiếu nại dịch vụ đại lý hoặc cần đại lý xác nhận giá chốt: Hướng dẫn liên hệ Tổng đài Chăm sóc khách hàng VinFast **1900 23 23 89** hoặc đến trực tiếp Showroom/Đại lý VinFast gần nhất.
11. TỔNG HỢP TÍNH NĂNG TOÀN DANH MỤC: Khi người dùng hỏi xe nào có tính năng gì (ví dụ: "Xe nào có màn hình HUD?", "Xe nào có cửa sổ trời?"): Hãy rà soát toàn bộ context và trả lời trực tiếp danh sách xe trang bị (ví dụ: VF 8 Plus, VF 9 Plus có màn hình HUD), không hỏi lại người dùng khi context đã có dữ liệu.
"""


SYNTHESIZE_PROMPT = """Bạn là trợ lý tư vấn xe VinFast. Tổng hợp thông tin dưới đây thành câu trả lời ngắn gọn, chính xác.

## Yêu cầu của người dùng:
{query}

## Dữ liệu tham khảo (Context):
{context}

QUAN TRỌNG:
- Đọc kỹ toàn bộ context để trả lời đúng và đầy đủ nhất cho câu hỏi của người dùng ở trên.
- QUY TẮC DẪN NGUỒN:
  * ƯU TIÊN link Brochure PDF chính thức (ví dụ: [Brochure VF 8 - Trang 19](https://.../VF8_Brochure_03022026.pdf)).
  * CẤM dẫn link đặt cọc (`dat-coc-*.html`, `shop.vinfastauto.com/vn_vi/dat-coc-*`) khi người dùng hỏi về thông số/tính năng xe.
- CHỈ dùng thông tin trong context. KHÔNG thêm thông tin ngoài context. KHÔNG tự bịa số liệu.
- KHI HỎI CHUNG XE NÀO CÓ TÍNH NĂNG: Rà soát context của từng xe và nêu rõ model nào có / không có trang bị.
- PHÂN BIỆT RÕ RÀNG:
  * "Cửa sổ trời" (Sunroof): Mở trượt lật được, chỉnh điện & giọng nói (VF 8 Plus).
  * "Trần kính toàn cảnh" (Panoramic Glass Roof): Kính trần cố định lấy sáng, KHÔNG mở được (VF 7 Plus - tùy chọn, VF 9 Plus).
- TÌNH HUỐNG KHẨN CẤP / BẢO MẬT / HOTLINE: Luôn cung cấp số Hotline VinFast **1900 23 23 89** khi gặp sự cố kỹ thuật khẩn cấp, tra cứu cá nhân hoặc yêu cầu khiếu nại.
"""


_STATIC_FALLBACK_CATALOG = """### Dòng xe: VF 2 (Mã: VF2)
  - Giá niêm yết: TieuChuan: 188.000.000 VNĐ

### Dòng xe: VF 3 (Mã: VF3)
  - Giá niêm yết: Eco: 285.000.000 VNĐ | Plus: 296.000.000 VNĐ
  - Thông số: Quãng đường di chuyển 215 km (NEDC)

### Dòng xe: VF 5 (Mã: VF5)
  - Giá niêm yết: Plus: 496.000.000 VNĐ
  - Tùy chọn lazang: Hợp kim 17 inch (0 VNĐ), Lõi thép 16 inch (0 VNĐ)

### Dòng xe: VF 6 (Mã: VF6)
  - Giá niêm yết: Eco: 646.000.000 VNĐ | Plus: 699.000.000 VNĐ
  - Thông số: Quãng đường Eco: 485 km (NEDC) | Plus: 460 km (NEDC). Công suất Eco: 100 kW | Plus: 150 kW.
  - Màn hình HUD: Không trang bị trên cả 2 bản Eco và Plus.

### Dòng xe: VF 7 (Mã: VF7)
  - Giá niêm yết:
    * Eco: 740.000.000 VNĐ
    * Plus (FWD): 830.000.000 VNĐ
    * PlusCaptain: 850.000.000 VNĐ
    * Plus AWD (Hai cầu, 2 động cơ): 879.000.000 VNĐ
    * Plus AWD Panoramic Roof (Hai cầu + Trần kính toàn cảnh): 899.000.000 VNĐ
  - Tùy chọn nâng cấp (Options):
    * VF 7 Eco: Tùy chọn màn hình HUD (+10.000.000 VNĐ).
    * VF 7 Plus: Nâng cấp Hai cầu AWD (+49.000.000 VNĐ) -> Giá thành 879.000.000 VNĐ.
    * VF 7 Plus: Tùy chọn Trần kính toàn cảnh cố định (+20.000.000 VNĐ).
  - Màu sắc: Màu cơ bản (Jet Black, Solar Ruby, Zenith Grey, Infinity Blanc) (+0 VNĐ). Màu nâng cao: Urban Mint (+12.000.000 VNĐ).
  - Thông số: Quãng đường Eco: 450 km (WLTP) | Plus: 431 km (WLTP).

### Dòng xe: VF 8 (Mã: VF8)
  - Giá niêm yết: Eco: 898.000.000 VNĐ | Plus: 1.079.000.000 VNĐ
  - Thông số: Quãng đường Eco: 562 km (NEDC) / 471 km (WLTP) | Plus: 457 km (NEDC) / 400 km (WLTP).
  - Cửa sổ trời: Bản Plus có cửa sổ trời mở trượt/lật chỉnh điện và giọng nói. Bản Eco không có.
  - Màn hình HUD: Trang bị tiêu chuẩn trên VF 8 Plus.

### Dòng xe: VF 8 The All New (Mã: VF8NEW)
  - Giá niêm yết: The All New (2026): 899.000.000 VNĐ

### Dòng xe: VF 9 (Mã: VF9)
  - Giá niêm yết: Eco: 1.348.000.000 VNĐ | Plus (7 chỗ): 1.529.000.000 VNĐ | PlusCaptain (6 chỗ): 1.561.000.000 VNĐ
  - Trần kính: Trang bị sẵn trần kính toàn cảnh cố định trên bản Plus.
  - Màn hình HUD: Trang bị tiêu chuẩn trên VF 9 Plus.

### Dòng xe: VF MPV 7 (Mã: VFMPV7)
  - Giá niêm yết: Eco: 750.000.000 VNĐ

### Hotline & Kênh Hỗ trợ Khách hàng:
- Hotline VinFast 24/7: **1900 23 23 89** (Hỗ trợ tư vấn, cứu hộ khẩn cấp 24/7, khiếu nại dịch vụ).
"""


async def get_system_prompt() -> str:
    global _prompt_cache, _prompt_cache_time
    if _prompt_cache and (time.time() - _prompt_cache_time) < _CACHE_TTL:
        return _prompt_cache

    try:
        pool = _pg_pool
        if pool is not None:
            async with pool.acquire() as conn:
                price_rows = await conn.fetch(
                    "SELECT model_id, edition_id, price_list_vnd, price_promo_vnd "
                    "FROM price_list_active ORDER BY model_id, price_list_vnd"
                )
                opt_rows = await conn.fetch(
                    "SELECT model_id, version_name, option_name, value_name, price_extra_vnd "
                    "FROM car_options_active ORDER BY model_id, version_name, option_name"
                )
                col_rows = await conn.fetch(
                    "SELECT model_id, version_name, color_name, color_type, color_fee_vnd "
                    "FROM car_colors_active ORDER BY model_id, version_name, color_name"
                )
                spec_rows = await conn.fetch(
                    "SELECT model_code, version_name, spec_key, spec_value, spec_unit "
                    "FROM car_specs "
                    "WHERE spec_key IN ('range_km', 'power_kw', 'torque_nm', 'battery_kwh', 'seats', 'top_speed_kmh', 'head_up_display', 'sunroof_type', 'surround_view_camera') "
                    "ORDER BY model_code, version_name, spec_key"
                )
        else:
            pg_url = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")
            conn = await asyncpg.connect(pg_url)
            try:
                price_rows = await conn.fetch(
                    "SELECT model_id, edition_id, price_list_vnd, price_promo_vnd "
                    "FROM price_list_active ORDER BY model_id, price_list_vnd"
                )
                opt_rows = await conn.fetch(
                    "SELECT model_id, version_name, option_name, value_name, price_extra_vnd "
                    "FROM car_options_active ORDER BY model_id, version_name, option_name"
                )
                col_rows = await conn.fetch(
                    "SELECT model_id, version_name, color_name, color_type, color_fee_vnd "
                    "FROM car_colors_active ORDER BY model_id, version_name, color_name"
                )
                spec_rows = await conn.fetch(
                    "SELECT model_code, version_name, spec_key, spec_value, spec_unit "
                    "FROM car_specs "
                    "WHERE spec_key IN ('range_km', 'power_kw', 'torque_nm', 'battery_kwh', 'seats', 'top_speed_kmh', 'head_up_display', 'sunroof_type', 'surround_view_camera') "
                    "ORDER BY model_code, version_name, spec_key"
                )
            finally:
                await conn.close()

        prices_by_model = {}
        for r in price_rows:
            mid = r["model_id"]
            prices_by_model.setdefault(mid, []).append(r)

        opts_by_model = {}
        for r in opt_rows:
            mid = r["model_id"]
            opts_by_model.setdefault(mid, []).append(r)

        cols_by_model = {}
        for r in col_rows:
            mid = r["model_id"]
            cols_by_model.setdefault(mid, []).append(r)

        specs_by_model = {}
        for r in spec_rows:
            mc = r["model_code"]
            specs_by_model.setdefault(mc, []).append(r)

        models = [
            ("VF 2", "VF2"),
            ("VF 3", "VF3"),
            ("VF 5", "VF5"),
            ("VF 6", "VF6"),
            ("VF 7", "VF7"),
            ("VF 8", "VF8"),
            ("VF 8 All New", "VF8NEW"),
            ("VF 9", "VF9"),
            ("VF MPV 7", "VFMPV7"),
        ]

        lines = []
        for label, mid in models:
            lines.append(f"### Dòng xe: {label} (Mã: {mid})")

            p_list = prices_by_model.get(mid, [])
            if p_list:
                lines.append("  - Giá niêm yết các phiên bản:")
                for p in p_list:
                    promo = f" | Ưu đãi: {p['price_promo_vnd']:,} VNĐ" if p["price_promo_vnd"] else ""
                    lines.append(f"    * {p['edition_id']}: {p['price_list_vnd']:,} VNĐ{promo}")

            o_list = opts_by_model.get(mid, [])
            if o_list:
                lines.append("  - Tùy chọn nâng cấp (Options):")
                for o in o_list:
                    fee = f" (+{o['price_extra_vnd']:,} VNĐ)" if o["price_extra_vnd"] else " (0 VNĐ)"
                    lines.append(f"    * {o['version_name']} / {o['option_name']}: {o['value_name']}{fee}")

            c_list = cols_by_model.get(mid, [])
            if c_list:
                seen_colors = set()
                color_strs = []
                for c in c_list:
                    cname = c["color_name"]
                    if cname in seen_colors:
                        continue
                    seen_colors.add(cname)
                    fee = f" (Nâng cao, +{c['color_fee_vnd']:,} VNĐ)" if c["color_fee_vnd"] else " (Cơ bản)"
                    color_strs.append(f"{cname}{fee}")
                lines.append(f"  - Màu sắc: {', '.join(color_strs)}")

            s_list = specs_by_model.get(label, [])
            if s_list:
                lines.append("  - Thông số kỹ thuật then chốt:")
                for s in s_list:
                    vname = f" [{s['version_name']}]" if s["version_name"] else ""
                    unit = f" {s['spec_unit']}" if s["spec_unit"] else ""
                    lines.append(f"    *{vname} {s['spec_key']}: {s['spec_value']}{unit}")

            lines.append("")

        lines.append("### Hotline & Kênh Hỗ trợ Khách hàng:")
        lines.append("- Hotline VinFast 24/7: **1900 23 23 89** (Hỗ trợ tư vấn, cứu hộ khẩn cấp, khiếu nại).")

        model_list = "\n".join(lines)
        result = SYSTEM_PROMPT.format(model_list=model_list)
        _prompt_cache = result
        _prompt_cache_time = time.time()
        return result

    except Exception as e:
        import logging

        logging.getLogger("bds.prompts").warning("get_system_prompt PG failed (fail-open): %s", e)
        fallback = _STATIC_FALLBACK_CATALOG
        result = SYSTEM_PROMPT.format(model_list=fallback)
        _prompt_cache = result
        _prompt_cache_time = time.time() - (_CACHE_TTL - 60)
        return result


def get_prompt_hash() -> str:
    global _prompt_hash
    if _prompt_hash is None:
        _prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    return _prompt_hash
