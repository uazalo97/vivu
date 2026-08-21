#!/usr/bin/env python3
"""
table.py — Robust Spec Normalizer for VinFast Vehicles.
Maps Vietnamese table attributes to standardized English slugs, VN labels, standard units,
and standard categories (dimension, powertrain, battery, chassis, exterior, interior, infotainment, convenience, safety, security, adas, connected).
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from scripts.harness.schemas import SpecItem


def no_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm_label(s: str) -> str:
    s = no_diacritics(s).lower().replace("đ", "d")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip(":|-–— \t")


# Standard Categories mapping (slug -> VN label)
CATEGORY_VN_MAP = {
    "dimension": "Kích thước & trọng lượng",
    "powertrain": "Hệ thống truyền động",
    "battery": "Pin & sạc",
    "chassis": "Khung gầm & hệ thống treo",
    "exterior": "Ngoại thất",
    "interior": "Nội thất",
    "infotainment": "Giải trí & kết nối",
    "convenience": "Tiện nghi",
    "safety": "An toàn",
    "security": "An ninh",
    "adas": "Hỗ trợ lái nâng cao (ADAS)",
    "connected": "Kết nối thông minh",
}

# Detailed Attribute Mapping:
# norm_label_key -> (spec_key, spec_key_vn, default_unit, category_slug)
SPEC_MAPPING: Dict[str, Tuple[str, str, str, str]] = {
    # ── Powertrain & Battery ──
    "cong suat toi da": ("power_kw", "Công suất tối đa", "kW", "powertrain"),
    "cong suat": ("power_kw", "Công suất tối đa", "kW", "powertrain"),
    "mo men xoan cuc dai": ("torque_nm", "Mô men xoắn cực đại", "Nm", "powertrain"),
    "mo men xoan": ("torque_nm", "Mô men xoắn cực đại", "Nm", "powertrain"),
    "dong co": ("engine_type", "Loại động cơ", "", "powertrain"),
    "loai dong co": ("engine_type", "Loại động cơ", "", "powertrain"),
    "dan dong": ("drivetrain", "Hệ dẫn động", "", "powertrain"),
    "he dan dong": ("drivetrain", "Hệ dẫn động", "", "powertrain"),
    "toc do toi da": ("top_speed_kmh", "Tốc độ tối đa", "km/h", "powertrain"),
    "tang toc 0-100 km/h": ("acceleration_0_100_s", "Tăng tốc 0-100 km/h", "s", "powertrain"),
    "kha nang tang toc": ("acceleration_0_100_s", "Tăng tốc 0-100 km/h", "s", "powertrain"),
    "che do lai": ("drive_modes", "Chế độ lái", "", "powertrain"),
    "dung luong pin kha dung": ("battery_kwh", "Dung lượng pin khả dụng", "kWh", "battery"),
    "dung luong pin": ("battery_kwh", "Dung lượng pin khả dụng", "kWh", "battery"),
    "pack pin": ("battery_kwh", "Dung lượng pin khả dụng", "kWh", "battery"),
    "loai pin": ("battery_type", "Loại pin", "", "battery"),
    "quang duong chay mot lan sac day": ("range_km", "Quãng đường chạy 1 lần sạc đầy", "km", "battery"),
    "quang duong di chuyen": ("range_km", "Quãng đường di chuyển", "km", "battery"),
    "quang duong chay": ("range_km", "Quãng đường di chuyển", "km", "battery"),
    "quang duong": ("range_km", "Quãng đường di chuyển", "km", "battery"),
    "thoi gian nap pin nhanh nhat": ("fast_charge_min", "Thời gian nạp pin nhanh nhất", "phút", "battery"),
    "thoi gian sac nhanh": ("fast_charge_min", "Thời gian sạc nhanh", "phút", "battery"),
    "cong suat sac toi da": ("ac_charge_power_kw", "Công suất sạc tối đa", "kW", "battery"),
    "cong suat sac ac": ("ac_charge_power_kw", "Công suất sạc AC", "kW", "battery"),
    "cong suat sac dc": ("dc_charge_power_kw", "Công suất sạc DC", "kW", "battery"),
    "day sac di dong": ("portable_charger", "Dây sạc di động", "", "battery"),
    "thoi gian sac tieu chuan": ("standard_charge_hours", "Thời gian sạc tiêu chuẩn", "giờ", "battery"),
    "he thong phanh tai sinh": ("regenerative_braking", "Hệ thống phanh tái sinh", "", "powertrain"),
    # ── Dimensions & Weight ──
    "dai x rong x cao": ("dimension_triple", "Kích thước Dài x Rộng x Cao", "mm", "dimension"),
    "kich thuoc": ("dimension_triple", "Kích thước Dài x Rộng x Cao", "mm", "dimension"),
    "chieu dai tong the": ("length_mm", "Chiều dài tổng thể", "mm", "dimension"),
    "chieu rong tong the": ("width_mm", "Chiều rộng tổng thể", "mm", "dimension"),
    "chieu cao tong the": ("height_mm", "Chiều cao tổng thể", "mm", "dimension"),
    "chieu dai co so": ("wheelbase_mm", "Chiều dài cơ sở", "mm", "dimension"),
    "khoang sang gam xe khong tai": ("ground_clearance_mm", "Khoảng sáng gầm xe không tải", "mm", "dimension"),
    "khoang sang gam xe": ("ground_clearance_mm", "Khoảng sáng gầm xe", "mm", "dimension"),
    "khoang sang gam": ("ground_clearance_mm", "Khoảng sáng gầm xe", "mm", "dimension"),
    "trong luong khong tai": ("curb_weight_kg", "Trọng lượng không tải", "kg", "dimension"),
    "trong luong toan tai": ("gross_weight_kg", "Trọng lượng toàn tải", "kg", "dimension"),
    "tai trong": ("payload_kg", "Tải trọng", "kg", "dimension"),
    "tai hanh ly": ("trunk_payload_kg", "Tải hành lý", "kg", "dimension"),
    "tai trong hanh ly noc xe": ("roof_load_kg", "Tải trọng hành lý nóc xe", "kg", "dimension"),
    "ban kinh quay vong toi thieu": ("turning_radius_m", "Bán kính quay vòng tối thiểu", "m", "dimension"),
    "ban kinh quay dau": ("turning_radius_m", "Bán kính quay vòng tối thiểu", "m", "dimension"),
    "linh hoat": ("turning_radius_m", "Bán kính quay vòng tối thiểu", "m", "dimension"),
    "dung tich khoang hanh ly": ("trunk_capacity_l", "Dung tích khoang hành lý", "L", "dimension"),
    "dung tich cop xe": ("trunk_capacity_l", "Dung tích cốp xe", "L", "dimension"),
    # ── Chassis, Brakes & Wheels ──
    "he thong treo truoc": ("front_suspension", "Hệ thống treo trước", "", "chassis"),
    "he thong treo sau": ("rear_suspension", "Hệ thống treo sau", "", "chassis"),
    "he thong treo (truoc/sau)": ("suspension_type", "Hệ thống treo (trước/sau)", "", "chassis"),
    "he thong treo": ("suspension_type", "Hệ thống treo", "", "chassis"),
    "he thong phanh truoc": ("front_brakes", "Phanh trước", "", "chassis"),
    "he thong phanh sau": ("rear_brakes", "Phanh sau", "", "chassis"),
    "he thong phanh (truoc/sau)": ("brake_type", "Hệ thống phanh (trước/sau)", "", "chassis"),
    "he thong phanh": ("brake_type", "Hệ thống phanh", "", "chassis"),
    "phanh truoc/sau": ("brake_type", "Hệ thống phanh", "", "chassis"),
    "kich thuoc la-zang": ("wheel_size_inch", "Kích thước la-zăng", "inch", "chassis"),
    "kich thuoc mam xe": ("wheel_size_inch", "Kích thước mâm xe", "inch", "chassis"),
    "la-zang": ("wheel_size_inch", "Kích thước la-zăng", "inch", "chassis"),
    "kich thuoc lop": ("tire_size", "Kích thước lốp", "", "chassis"),
    "lop xe": ("tire_size", "Kích thước lốp", "", "chassis"),
    "bo va lop": ("tire_repair_kit", "Bộ vá lốp", "", "chassis"),
    "bo dung cu kich xe": ("jack_kit", "Bộ dụng cụ kích xe", "", "chassis"),
    # ── Exterior ──
    "den chieu sang phia truoc": ("headlight_type", "Đèn chiếu sáng phía trước", "", "exterior"),
    "den pha": ("headlight_type", "Đèn pha", "", "exterior"),
    "den chieu sang ban ngay": ("drl_type", "Đèn chiếu sáng ban ngày", "", "exterior"),
    "den hau": ("taillight_type", "Đèn hậu", "", "exterior"),
    "den suong mu": ("fog_light", "Đèn sương mù", "", "exterior"),
    "den cho dan duong": ("guide_me_home_light", "Đèn chờ dẫn đường", "", "exterior"),
    "dieu khien goc chieu den": ("headlight_leveling", "Điều khiển góc chiếu đèn", "", "exterior"),
    "guong chieu hau ngoai": ("side_mirrors", "Gương chiếu hậu ngoài", "", "exterior"),
    "guong chieu hau": ("side_mirrors", "Gương chiếu hậu", "", "exterior"),
    "gat mua truoc": ("windshield_wipers", "Gạt mưa trước", "", "exterior"),
    "dong/mo cop sau": ("tailgate_type", "Đóng/mở cốp sau", "", "exterior"),
    "cop sau": ("tailgate_type", "Cốp sau", "", "exterior"),
    "kinh cua so dien": ("power_windows", "Kính cửa sổ điện", "", "exterior"),
    "kinh cach nhiet": ("privacy_glass", "Kính cách nhiệt", "", "exterior"),
    "noc xe": ("roof_type", "Loại nóc xe", "", "exterior"),
    "tran kinh toan canh": ("panoramic_roof", "Trần kính toàn cảnh", "", "exterior"),
    # ── Interior & Convenience ──
    "so cho ngoi": ("seats_count", "Số chỗ ngồi", "chỗ", "interior"),
    "so ghe ngoi": ("seats_count", "Số chỗ ngồi", "chỗ", "interior"),
    "ghe lai": ("driver_seat", "Ghế lái", "", "interior"),
    "ghe phu": ("passenger_seat", "Ghế phụ", "", "interior"),
    "ghe hang 2": ("second_row_seats", "Hàng ghế thứ 2", "", "interior"),
    "hang ghe thu hai": ("second_row_seats", "Hàng ghế thứ 2", "", "interior"),
    "hang ghe thu 3": ("third_row_seats", "Hàng ghế thứ 3", "", "interior"),
    "ghe vip": ("vip_seats", "Ghế cơ trưởng (VIP)", "", "interior"),
    "boc ghe": ("seat_material", "Chất liệu bọc ghế", "", "interior"),
    "chat lieu ghe": ("seat_material", "Chất liệu bọc ghế", "", "interior"),
    "vo lang": ("steering_wheel", "Vô lăng", "", "interior"),
    "loai vo lang": ("steering_wheel", "Loại vô lăng", "", "interior"),
    "he thong dieu hoa": ("ac_system", "Hệ thống điều hòa", "", "interior"),
    "dieu hoa": ("ac_system", "Hệ thống điều hòa", "", "interior"),
    "dieu hoa khong khi": ("ac_system", "Hệ thống điều hòa", "", "interior"),
    "loc khong khi": ("air_filter", "Lọc không khí", "", "interior"),
    "guong chieu hau trong xe": ("rearview_mirror", "Gương chiếu hậu trong xe", "", "interior"),
    "den trang tri noi that": ("ambient_light", "Đèn trang trí nội thất", "", "interior"),
    # ── Infotainment & Connected ──
    "man hinh thong tin lai": ("driver_display_inch", "Màn hình thông tin lái", "inch", "infotainment"),
    "man hinh giai tri": ("center_display_inch", "Màn hình giải trí cảm ứng", "inch", "infotainment"),
    "man hinh trung tam": ("center_display_inch", "Màn hình giải trí trung tâm", "inch", "infotainment"),
    "man hinh hien thi kinh lai hud": ("hud_display", "Hiển thị kính lái HUD", "", "infotainment"),
    "hud": ("hud_display", "Hiển thị kính lái HUD", "", "infotainment"),
    "he thong am thanh": ("speakers_count", "Hệ thống âm thanh", "loa", "infotainment"),
    "he thong loa": ("speakers_count", "Hệ thống loa", "loa", "infotainment"),
    "chuc nang giai tri": ("entertainment_features", "Chức năng giải trí", "", "infotainment"),
    "ket noi": ("connectivity", "Kết nối (Bluetooth/Wifi/USB)", "", "infotainment"),
    "cong usb": ("usb_ports", "Cổng sạc USB", "", "infotainment"),
    "sac khong day": ("wireless_charger", "Sạc không dây", "", "infotainment"),
    "tro ly ao": ("voice_assistant", "Trợ lý ảo VinFast", "", "infotainment"),
    "tro ly ao vmi": ("voice_assistant", "Trợ lý ảo VMi", "", "infotainment"),
    "dieu khien bang giong noi": ("voice_control", "Điều khiển bằng giọng nói", "", "infotainment"),
    "ung dung vinfast": ("mobile_app", "Ứng dụng VinFast", "", "connected"),
    "ung dung tren dien thoai": ("mobile_app", "Ứng dụng trên điện thoại thông minh", "", "connected"),
    "cap nhat phan mem tu xa": ("ota_update", "Cập nhật phần mềm từ xa (OTA)", "", "connected"),
    "thanh toan phi sac": ("charging_payment", "Thanh toán phí sạc qua app", "", "connected"),
    "tu chan doan loi": ("auto_diagnostics", "Tự chẩn đoán lỗi", "", "connected"),
    "che do cam trai": ("camping_mode", "Chế độ cắm trại", "", "convenience"),
    "che do thu cung": ("pet_mode", "Chế độ thú cưng", "", "convenience"),
    "che do ngu": ("sleep_mode", "Chế độ ngủ", "", "convenience"),
    # ── Safety, Security & ADAS ──
    "tui khi": ("airbags_count", "Số lượng túi khí", "túi", "safety"),
    "he thong tui khi": ("airbags_count", "Hệ thống túi khí", "túi", "safety"),
    "tui khi danh cho nguoi lai": ("driver_airbag", "Túi khí người lái", "", "safety"),
    "he thong chong bo cung phanh (abs)": ("abs_brake", "Hệ thống chống bó cứng phanh (ABS)", "", "safety"),
    "chong bo cung phanh abs": ("abs_brake", "Hệ thống chống bó cứng phanh (ABS)", "", "safety"),
    "phan phoi luc phanh dien tu (ebd)": ("ebd_brake", "Phân phối lực phanh điện tử (EBD)", "", "safety"),
    "ho tro phanh khan cap (ba)": ("ba_brake", "Hỗ trợ phanh khẩn cấp (BA)", "", "safety"),
    "can bang dien tu (esc)": ("esc_system", "Hệ thống cân bằng điện tử (ESC)", "", "safety"),
    "kiem soat luc keo (tcs)": ("tcs_system", "Hệ thống kiểm soát lực kéo (TCS)", "", "safety"),
    "ho tro khoi hanh ngang doc (hsa)": ("hsa_system", "Hỗ trợ khởi hành ngang dốc (HSA)", "", "safety"),
    "chuc nang chong lat (rom)": ("rom_system", "Chức năng kiểm soát chống lật (ROM)", "", "safety"),
    "canh bao diem mu": ("bsd_system", "Cảnh báo điểm mù (BSD)", "", "adas"),
    "canh bao va cham": ("fwd_collision_warning", "Cảnh báo va chạm phía trước", "", "adas"),
    "phanh tu dong khan cap": ("aeb_system", "Phanh tự động khẩn cấp (AEB)", "", "adas"),
    "ho tro giu lan": ("lka_system", "Hỗ trợ giữ làn đường (LKA)", "", "adas"),
    "canh bao lech lan": ("ldw_system", "Cảnh báo chệch làn đường (LDW)", "", "adas"),
    "ho tro do xe": ("parking_assist", "Hệ thống hỗ trợ đỗ xe", "", "adas"),
    "camera lui": ("rear_camera", "Camera lùi", "", "safety"),
    "camera 360": ("camera_360", "Camera 360 độ", "", "safety"),
    "giam sat ap suat lop (tpms)": ("tpms_system", "Hệ thống giám sát áp suất lốp (TPMS)", "", "safety"),
    "khoa cua tu dong khi xe di chuyen": ("auto_door_lock", "Khóa cửa tự động khi xe di chuyển", "", "security"),
    "he thong chong trom": ("anti_theft_system", "Hệ thống báo động chống trộm", "", "security"),
    "moc co dinh ghe tre em isofix": ("isofix_anchor", "Móc cố định ghế trẻ em ISOFIX", "", "safety"),
    # ── Pricing & Warranty ──
    "gia ban chinh thuc": ("price_vnd", "Giá bán chính thức", "triệu", "pricing"),
    "gia ban": ("price_vnd", "Giá bán niêm yết", "triệu", "pricing"),
    "thoi gian bao hanh tieu chuan": ("warranty_years", "Thời gian bảo hành tiêu chuẩn", "năm", "warranty"),
    "quang duong bao hanh tieu chuan": ("warranty_km", "Quãng đường bảo hành tiêu chuẩn", "km", "warranty"),
    "bao hanh pin": ("battery_warranty_years", "Thời gian bảo hành pin", "năm", "warranty"),
}

ALIASES_BY_LEN = sorted(SPEC_MAPPING.keys(), key=len, reverse=True)


class TableNormalizer:
    def map_attribute(self, raw_attr: str, section_hint: Optional[str] = None) -> Tuple[str, str, str, str, str]:
        """
        Map raw attribute string to (spec_key, spec_key_vn, unit, category_slug, category_vn).
        """
        na = norm_label(raw_attr)

        # Direct exact match
        if na in SPEC_MAPPING:
            key, key_vn, unit, cat = SPEC_MAPPING[na]
            return key, key_vn, unit, cat, CATEGORY_VN_MAP.get(cat, cat.title())

        # Substring match (longest alias first)
        for a in ALIASES_BY_LEN:
            if a in na or na.startswith(a):
                key, key_vn, unit, cat = SPEC_MAPPING[a]
                return key, key_vn, unit, cat, CATEGORY_VN_MAP.get(cat, cat.title())

        # Fallback category inference from section hint
        cat_slug = "convenience"
        if section_hint:
            s_norm = norm_label(section_hint)
            if any(k in s_norm for k in ["kich thuoc", "trong luong", "tai trong"]):
                cat_slug = "dimension"
            elif any(k in s_norm for k in ["dong co", "van hanh", "truyen dong", "cong suat"]):
                cat_slug = "powertrain"
            elif any(k in s_norm for k in ["pin", "sac"]):
                cat_slug = "battery"
            elif any(k in s_norm for k in ["khung gam", "phanh", "treo", "mam", "lop", "vanh"]):
                cat_slug = "chassis"
            elif any(k in s_norm for k in ["ngoai that", "den", "guong", "cop"]):
                cat_slug = "exterior"
            elif any(k in s_norm for k in ["noi that", "ghe", "dieu hoa", "vo lang"]):
                cat_slug = "interior"
            elif any(k in s_norm for k in ["giai tri", "am thanh", "loa", "man hinh", "tro ly ao"]):
                cat_slug = "infotainment"
            elif any(k in s_norm for k in ["an toan", "tui khi"]):
                cat_slug = "safety"
            elif any(k in s_norm for k in ["adas", "tro lai", "va cham", "do xe", "lan duong"]):
                cat_slug = "adas"
            elif any(k in s_norm for k in ["ket noi", "ung dung", "app"]):
                cat_slug = "connected"

        clean_attr = raw_attr.strip(": \t")
        # slugify raw attr
        slug_key = no_diacritics(clean_attr).lower().replace(" ", "_")
        slug_key = re.sub(r"[^a-z0-9_]", "", slug_key)[:50] or "custom_spec"

        return slug_key, clean_attr, "", cat_slug, CATEGORY_VN_MAP.get(cat_slug, cat_slug.title())

    def normalize_number(self, val_str: str) -> Tuple[Optional[float], str]:
        s = str(val_str).strip()
        m = re.search(r"[\d][\d.,]*", s)
        if not m:
            return None, s
        tok = m.group(0)
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", tok):
            tok = tok.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d+,\d+", tok):
            tok = tok.replace(",", ".")
        try:
            val = float(tok)
            canon = str(int(val)) if val.is_integer() else f"{val:g}"
            return val, canon
        except ValueError:
            return None, s

    def normalize_spec_item(self, item: SpecItem) -> List[SpecItem]:
        raw_attr = item.attribute
        spec_key, spec_key_vn, def_unit, cat_slug, cat_vn = self.map_attribute(raw_attr, item.category)

        # Handle dimension triple ("3190 x 1679 x 1652")
        if spec_key == "dimension_triple":
            val_str = str(item.value)
            parts = [p.strip() for p in re.split(r"[xX*×]", val_str) if p.strip()]
            if len(parts) == 3:
                _, l_c = self.normalize_number(parts[0])
                _, w_c = self.normalize_number(parts[1])
                _, h_c = self.normalize_number(parts[2])
                return [
                    SpecItem(
                        category="dimension",
                        category_vn="Kích thước & trọng lượng",
                        attribute=f"{raw_attr} (Chiều dài)",
                        spec_key="length_mm",
                        spec_key_vn="Chiều dài tổng thể",
                        value=l_c,
                        unit="mm",
                        edition=item.edition,
                        evidence=item.evidence,
                        validation=item.validation,
                        provenance=item.provenance,
                    ),
                    SpecItem(
                        category="dimension",
                        category_vn="Kích thước & trọng lượng",
                        attribute=f"{raw_attr} (Chiều rộng)",
                        spec_key="width_mm",
                        spec_key_vn="Chiều rộng tổng thể",
                        value=w_c,
                        unit="mm",
                        edition=item.edition,
                        evidence=item.evidence,
                        validation=item.validation,
                        provenance=item.provenance,
                    ),
                    SpecItem(
                        category="dimension",
                        category_vn="Kích thước & trọng lượng",
                        attribute=f"{raw_attr} (Chiều cao)",
                        spec_key="height_mm",
                        spec_key_vn="Chiều cao tổng thể",
                        value=h_c,
                        unit="mm",
                        edition=item.edition,
                        evidence=item.evidence,
                        validation=item.validation,
                        provenance=item.provenance,
                    ),
                ]

        unit = item.unit or def_unit
        num_val, canon_val = self.normalize_number(str(item.value))
        final_val = canon_val if num_val is not None and def_unit else str(item.value).strip()

        item.category = cat_slug
        item.category_vn = cat_vn
        item.spec_key = spec_key
        item.spec_key_vn = spec_key_vn
        item.value = final_val
        item.unit = unit or None
        return [item]
