import re

_TOKEN_RE = re.compile(r"[a-zà-ỹ0-9]+", re.UNICODE)


def build_structured_context(tool_results: list[dict], query: str = "") -> str:
    sections = []

    for tr in tool_results:
        if not tr.get("success", True):
            continue

        tool = tr["tool"]
        result = tr["result"]

        if tool == "get_price":
            sections.append(_format_prices(result))
        elif tool == "get_specs":
            sections.append(_format_specs(result))
        elif tool == "search_knowledge_base":
            sections.append(_format_search_results(result))
        elif tool == "get_colors":
            sections.append(_format_colors(result))
        elif tool == "get_options":
            sections.append(_format_options(result))
        elif tool == "list_available_models":
            sections.append(_format_models(result))
        elif tool == "get_active_promotions":
            sections.append(_format_promotions(result))
        elif tool == "get_onroad_cost_link":
            sections.append(_format_link(result, "chi phí lăn bánh"))
        elif tool == "get_loan_estimate_link":
            sections.append(_format_links(result, "trả góp/thẩm định vay"))
        elif tool == "get_showroom_charging_link":
            sections.append(_format_link(result, "showroom/trạm sạc"))
        elif tool == "get_booking_link":
            sections.append(_format_link(result, "đặt lịch"))
        elif tool == "get_maintenance_link":
            sections.append(_format_maintenance(result))

    return "\n\n".join(sections)


def _format_prices(result: dict) -> str:
    source_url = result.get("source_url", "")
    lines = [f"Giá xe {result['model_code']}:"]
    for p in result.get("prices", []):
        promo = f"{p['promo_price_vnd']:,} VNĐ" if p.get("promo_price_vnd") else "N/A"
        price = f"{p['price_vnd']:,} VNĐ" if p.get("price_vnd") else "N/A"
        lines.append(f"  - {p['version_name']}: Giá niêm yết {price} | Giá ưu đãi {promo}")
    if source_url:
        lines.append(f"\n  Nguồn: {source_url}")
    related = result.get("related_models", [])
    if related:
        lines.append("\n  Model liên quan:")
        for rm in related:
            rm_price = f"{rm['price_vnd']:,} VNĐ" if rm.get("price_vnd") else "N/A"
            lines.append(f"    - {rm['model_code']} ({rm.get('version_name', '')}): từ {rm_price}")
    note = result.get("note", "")
    if note:
        lines.append(f"\n  Lưu ý: {note}")
    return "\n".join(lines)


_SPEC_KEY_LABELS = {
    "power_kw": "Công suất tối đa",
    "torque_nm": "Mô-men xoắn cực đại",
    "range_km": "Quãng đường di chuyển",
    "battery_kwh": "Dung lượng pin",
    "fast_charge_min": "Thời gian sạc nhanh (10%-70%)",
    "acceleration_0_100_s": "Tăng tốc 0-100 km/h",
    "top_speed_kmh": "Tốc độ tối đa",
    "drivetrain": "Dẫn động",
    "seats": "Số chỗ ngồi",
    "airbags": "Túi khí",
    "length_mm": "Dài",
    "width_mm": "Rộng",
    "height_mm": "Cao",
    "wheelbase_mm": "Chiều dài cơ sở",
    "ground_clearance_mm": "Khoảng sáng gầm",
    "curb_weight_kg": "Trọng lượng không tải",
    "wheel_size_inch": "Kích thước mâm",
    "trunk_capacity": "Dung tích cốp",
    "head_up_display": "Màn hình HUD",
    "surround_view_camera": "Camera 360",
    "leatherette_seats": "Ghế bọc da",
    "speakers": "Số loa",
    "display_inch": "Màn hình cảm ứng",
    "sunroof_type": "Cửa sổ trời",
    "wireless_charging": "Sạc không dây điện thoại",
    "ac_type": "Điều hòa",
    "cabin_air_filter": "Lọc không khí cabin",
    "rear_ac_vents": "Cửa gió điều hòa hàng ghế sau",
    "smart_key": "Chìa khóa thông minh",
    "subwoofer": "Loa trầm",
    "tpms": "Cảnh báo áp suất lốp",
    "usb_port_type_a": "Cổng USB-A",
    "usb_port_type_c": "Cổng USB-C",
    "isofix": "Móc ghế trẻ em ISOFIX",
    "windshield_type": "Kính chắn gió",
    "rollover_mitigation": "Hệ thống chống lật",
    "frunk_capacity_l": "Dung tích cốp trước",
    "privacy_glass": "Kính tối màu",
    "battery_heater": "Gia nhiệt pin",
    "charge_management": "Quản lý sạc",
    "charger_map": "Bản đồ trạm sạc",
}


def _format_colors(result: dict) -> str:
    mc = result.get("model_code", "")
    colors = result.get("colors", [])
    interiors = result.get("interiors", [])
    variants = result.get("variants", [])

    lines = [f"Màu sắc {mc}:"]
    if colors:
        lines.append(f"  Màu ngoại thất ({len(colors)}): {', '.join(colors)}")
    if interiors:
        lines.append(f"  Màu nội thất ({len(interiors)}): {', '.join(interiors)}")

    if variants:
        # Group by color to show fee
        seen = set()
        lines.append(f"\n  Chi tiết màu:")  # noqa: F541
        for v in variants:
            key = f"{v['color']}|{v['interior']}"
            if key in seen:
                continue
            seen.add(key)
            fee = v.get("color_fee_vnd") or 0
            color_type = v.get("color_type") or ""
            fee_str = f" (+{fee:,} VNĐ)" if fee > 0 else ""
            type_str = f" [{color_type}]" if color_type else ""
            lines.append(f"    - {v['color']}{type_str} / Nội thất: {v['interior']}{fee_str}")

    return "\n".join(lines)


_OPTION_GROUP_LABELS = {
    "wheel": "Mâm/lazang",
    "hud": "Màn hình HUD",
    "driveTypes": "Hệ dẫn động",
    "options": "Tùy chọn khác",
    "roof": "Trần xe",
    "interior": "Nội thất",
    "color": "Màu",
}


def _format_options(result: dict) -> str:
    lines = [f"Tùy chọn (option) {result.get('model_code', '')}:"]
    cur_group = None
    for o in result.get("options", []):
        g = o.get("group", "")
        if g != cur_group:
            cur_group = g
            label = _OPTION_GROUP_LABELS.get(g, g)
            lines.append(f"\n  [{label}]")
        fee = o.get("price_extra_vnd") or 0
        fee_str = f" (+{fee:,} VNĐ)" if fee else ""
        ver = o.get("version", "")
        ver_str = f"{ver} — " if ver else ""
        lines.append(f"    {ver_str}{o.get('value_name', '')}{fee_str}")
    source_url = result.get("source_url", "")
    if source_url:
        lines.append(f"\n  Nguồn: {source_url}")
    return "\n".join(lines)


def _format_specs(result: dict) -> str:
    """Format specs, deduplicating identical values across versions to cut tokens."""
    source_url = result.get("source_url", "")
    lines = [f"Thông số kỹ thuật {result['model_code']}:"]

    specs = result.get("specs", [])

    # Group by (category, key) while preserving order
    grouped: dict[tuple, list] = {}
    for s in specs:
        grouped.setdefault((s["category"], s["key"]), []).append(s)

    current_cat = None
    count = 0
    MAX_SPEC_KEYS = 30  # cap total spec lines to keep context small (TPM budget)
    for (cat, key), rows in grouped.items():
        if count >= MAX_SPEC_KEYS:
            lines.append("\n  ... (còn nhiều thông số khác)")
            break
        count += 1
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n  [{current_cat.upper()}]")
        unit = f" {rows[0]['unit']}" if rows[0].get("unit") else ""
        label = _SPEC_KEY_LABELS.get(key, "")
        label_str = f" ({label})" if label else ""

        # All versions share the same value → collapse to one line
        first_val = rows[0]["value"]
        first_page = next((r["page"] for r in rows if r.get("page")), None)
        first_page_str = f" (Trang {first_page})" if first_page else ""
        if all(r["value"] == first_val for r in rows):
            vers = sorted({r["version_name"] for r in rows})
            if vers == ["ALL"]:
                lines.append(f"    {key}{label_str}: {first_val}{unit}{first_page_str}")
            else:
                lines.append(f"    {key}{label_str}: {first_val}{unit} (mọi phiên bản){first_page_str}")
        else:
            # Values differ → show per-version, but dedupe identical values
            seen = {}
            for r in rows:
                v = r["value"]
                if v in seen:
                    continue
                seen[v] = True
                vers = sorted({x["version_name"] for x in rows if x["value"] == v})
                ver_str = ", ".join(vers)
                r_page = r.get("page") or first_page
                r_page_str = f" (Trang {r_page})" if r_page else ""
                lines.append(f"    {ver_str} — {key}{label_str}: {v}{unit}{r_page_str}")

    if source_url:
        lines.append(f"\n  Nguồn tài liệu chính thức (Brochure PDF): {source_url}")
    note = result.get("note", "")
    if note:
        lines.append(f"\n  Lưu ý: {note}")
    return "\n".join(lines)


def _format_search_results(result: dict) -> str:
    lines = [f'Kết quả tìm kiếm cho: "{result["query"]}":']
    for i, r in enumerate(result.get("results", []), 1):
        src = r.get("source_url", "")
        lines.append(f"\n  [{i}] ({r['source_type']}, score={r['score']})")
        lines.append(f"      {r['text']}")
        if src and "dat-coc" not in src.lower():
            lines.append(f"      Nguồn tham khảo: {src}")
    return "\n".join(lines)


def _format_models(result: dict) -> str:
    lines = ["Danh sách xe VinFast:"]
    for m in result.get("models", []):
        vers = ", ".join(m.get("versions", []))
        lines.append(f"  - {m['model_code']} — Phiên bản: {vers}")
    return "\n".join(lines)


def _format_promotions(result: dict) -> str:
    url = result.get("url", "")
    label = result.get("label", "Khuyến mãi")
    note = result.get("note", "")
    if url:
        return f"{label}: {url}\n{note}" if note else f"{label}: {url}"
    return "Hiện tại không có thông tin khuyến mãi."


def _format_link(result: dict, label: str) -> str:
    url = result.get("url", "")
    lbl = result.get("label", label)
    if url:
        return f"Link {label}: {lbl}\n  URL: {url}"
    return f"Không tìm thấy link {label}."


def _format_links(result: dict, label: str) -> str:
    links = result.get("links", [])
    if not links:
        return f"Không tìm thấy link {label}."
    lines = [f"Link {label}:"]
    for l in links:  # noqa: E741
        lines.append(f"  - {l['label']}: {l['url']}")
    return "\n".join(lines)


def _format_maintenance(result: dict) -> str:
    links = result.get("links", [])
    if not links:
        return "Không tìm thấy link bảo dưỡng."
    lines = ["Link bảo dưỡng:"]
    for l in links:  # noqa: E741
        lines.append(f"  - Năm {l['year']}: {l['source_url']}")
    return "\n".join(lines)
