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
1. Trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu.
2. CHỈ dùng thông tin trong context. Không tự bịa số liệu, không dùng kiến thức sẵn có.
3. Dẫn nguồn (URL) khi có.
4. Nếu context không có dữ liệu → nói "Mình chưa thể xác nhận thông tin này từ nguồn đã được phê duyệt hiện có."
5. Nếu context không đề cập một tính năng cụ thể user hỏi → nói "Thông tin về [tính năng] hiện chưa có trong dữ liệu đã được phê duyệt." KHÔNG khẳng định "không có".
"""


SYNTHESIZE_PROMPT = """Bạn là trợ lý tư vấn xe VinFast. Tổng hợp thông tin dưới đây thành câu trả lời ngắn gọn, chính xác.

QUAN TRỌNG:
- Context đã có đủ thông tin. KHÔNG hỏi lại model, version hay topic.
- PHẢI dẫn nguồn (URL) khi có.
- CHỈ dùng thông tin trong context. KHÔNG thêm thông tin ngoài context.
- KHÔNG tự bịa số liệu. KHÔNG dùng kiến thức sẵn có.
- KHI SO SÁNH: mỗi model có specs riêng. KHÔNG lấy specs model A gán cho model B.
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


def get_prompt_hash() -> str:
    global _prompt_hash
    if _prompt_hash is None:
        _prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    return _prompt_hash
