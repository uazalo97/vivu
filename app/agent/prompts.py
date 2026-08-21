import asyncpg
import hashlib
import time

from app.config import settings

# TTL cache (5 minutes)
_prompt_cache = None
_prompt_cache_time = 0
_prompt_hash = None
_CACHE_TTL = 300


SYSTEM_PROMPT = """Bạn là trợ lý tư vấn xe VinFast tại Việt Nam.

## Danh sách xe đang bán (cập nhật từ hệ thống)
{model_list}

## Quy tắc
1. Trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu, đi thẳng vào câu hỏi.
2. CHỈ dùng thông tin trong context. Không tự bịa số liệu, không dùng kiến thức sẵn có.
3. Dẫn nguồn (URL) và số trang: Ưu tiên link Brochure PDF chính thức (ví dụ: `[Brochure VF 8 (Trang 19)](URL)`). CẤM dẫn link đặt cọc (`dat-coc-*`, `shop.vinfastauto.com`) khi trả lời về thông số kỹ thuật/tính năng.
4. Nếu context không có dữ liệu → nói "Mình chưa thể xác nhận thông tin này từ nguồn đã được phê duyệt hiện có."
5. Nếu context không đề cập một tính năng cụ thể user hỏi → nói "Thông tin về [tính năng] hiện chưa có trong dữ liệu đã được phê duyệt." KHÔNG khẳng định "không có".
6. PHÂN BIỆT RÕ TÍNH NĂNG CỬA SỔ TRỜI VÀ TRẦN KÍNH:
   - "Cửa sổ trời" (Sunroof/Moonroof): Mở trượt/lật chỉnh điện, có rèm, đóng mở bằng giọng nói (chỉ có trên VF 8 Plus).
   - "Trần kính toàn cảnh" (Panoramic Glass Roof): Mặt kính cố định lấy sáng, KHÔNG mở được ra ngoài (tùy chọn trên VF 7 Plus, trang bị trên VF 9 Plus). CẤM gọi trần kính cố định là cửa sổ trời đóng mở được.
   - TUYỆT ĐỐI KHÔNG gán tính năng của xe A (đóng mở bằng giọng nói của VF 8) sang cho xe B (VF 7).
"""


SYNTHESIZE_PROMPT = """Bạn là trợ lý tư vấn xe VinFast. Tổng hợp thông tin dưới đây thành câu trả lời ngắn gọn, chính xác.

QUAN TRỌNG:
- Context đã có đủ thông tin. KHÔNG hỏi lại model, version hay topic.
- QUY TẮC DẪN NGUỒN:
  * ƯU TIÊN link Brochure PDF chính thức (ví dụ: [Brochure VF 8 - Trang 19](https://.../VF8_Brochure_03022026.pdf)).
  * CẤM dẫn link đặt cọc (`dat-coc-*.html`, `shop.vinfastauto.com/vn_vi/dat-coc-*`) khi người dùng hỏi về thông số/tính năng xe.
- CHỈ dùng thông tin trong context. KHÔNG thêm thông tin ngoài context.
- KHÔNG tự bịa số liệu. KHÔNG dùng kiến thức sẵn có.
- KHI SO SÁNH / HỎI CHUNG XE NÀO CÓ TÍNH NĂNG: Mỗi model có specs riêng. TUYỆT ĐỐI KHÔNG lấy specs/tính năng của model A gán cho model B.
- PHÂN BIỆT RÕ RÀNG:
  * "Cửa sổ trời" (Sunroof): Mở trượt lật được, chỉnh điện & giọng nói (VF 8 Plus).
  * "Trần kính toàn cảnh" (Panoramic Glass Roof): Kính trần cố định lấy sáng, KHÔNG mở được (VF 7 Plus - tùy chọn, VF 9 Plus). Nếu user hỏi cửa sổ trời, chỉ khẳng định VF 8 Plus có cửa sổ trời mở được, và có thể chú thích thêm VF 7/VF 9 có trần kính cố định.
- Nếu context không có thông tin được hỏi → nói rõ: "Thông tin về [topic] hiện chưa có trong dữ liệu đã được phê duyệt cho [model]."
- Nếu context chỉ có một phần thông tin → trả lời phần có, nói rõ phần chưa có.
- Nếu context có specs cho model A nhưng không có cho model B → chỉ trả lời cho model A, nói rõ model B chưa có dữ liệu.

Context:
{context}

Câu hỏi: {query}
"""


async def get_system_prompt() -> str:
    global _prompt_cache, _prompt_cache_time
    if _prompt_cache and (time.time() - _prompt_cache_time) < _CACHE_TTL:
        return _prompt_cache

    # Fail-open: nếu PG không kết nối được (local dev chưa chạy PG) -> dùng fallback model_list
    try:
        pg_url = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(pg_url)

        rows = await conn.fetch(
            "SELECT model_id, model_label, year_range, "
            "STRING_AGG(edition_id, ', ' ORDER BY edition_id) as editions "
            "FROM edition_active "
            "GROUP BY model_id, model_label, year_range "
            "UNION "
            "SELECT '' as model_id, model_code AS model_label, '' as year_range, "
            "STRING_AGG(DISTINCT version_name, ', ' ORDER BY version_name) as editions "
            "FROM car_specs "
            "WHERE model_code NOT IN (SELECT DISTINCT model_label FROM edition_active) "
            "AND model_code IS NOT NULL AND version_name IS NOT NULL "
            "GROUP BY model_code "
            "ORDER BY model_label"
        )

        await conn.close()

        lines = []
        for r in rows:
            yr = f" ({r['year_range']})" if r["year_range"] else ""
            editions = r["editions"] or ""
            lines.append(f"- {r['model_label']}{yr} — Phiên bản: {editions}")

        model_list = "\n".join(lines) if lines else "- Chưa có model nào trong hệ thống"

        result = SYSTEM_PROMPT.format(model_list=model_list)
        _prompt_cache = result
        _prompt_cache_time = time.time()
        return result
    except Exception as e:
        import logging

        logging.getLogger("bds.prompts").warning("get_system_prompt PG failed (fail-open): %s", e)
        # Fallback tĩnh — không làm sập request /api/chat
        fallback_list = "- VF 6 — Phiên bản: Eco, Plus\n- VF 8 — Phiên bản: Eco, Plus"
        result = SYSTEM_PROMPT.format(model_list=fallback_list)
        # Cache ngắn 60s để retry PG sau đó
        _prompt_cache = result
        _prompt_cache_time = time.time() - (_CACHE_TTL - 60)
        return result


def get_prompt_hash() -> str:
    global _prompt_hash
    if _prompt_hash is None:
        _prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    return _prompt_hash
