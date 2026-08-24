import re

# Shared utility query regex — import from here instead of defining locally
# in classify.py and call_tools.py to stay in sync.
UTILITY_QUERY_RE = re.compile(
    r"(showroom|trạm\s*sạc|tram\s*sac|đại\s*lý|dai\s*ly|cửa\s*hàng|cua\s*hang|chi\s*nhánh|chi\s*nhanh|"
    r"lái\s*thử|lai\s*thu|test\s*drive|đăng\s*ký\s*lái|dang\s*ky\s*lai|"
    r"bảo\s*dưỡng|bao\s*duong|đặt\s*lịch|dat\s*lich|booking|"
    r"trả\s*góp|tra\s*gop|vay|thẩm\s*định|tham\s*dinh|lăn\s*bánh|lan\s*banh|"
    r"khuyến\s*mãi|khuyen\s*mai|ưu\s*đãi|uu\s*dai|voucher|"
    r"hotline|liên\s*hệ|lien\s*he|gặp\s*sales|gap\s*sales|nhân\s*viên|nhan\s*vien|tư\s*vấn\s*viên|tu\s*van\s*vien|"
    r"tổng\s*đài|tong\s*dai|hỗ\s*trợ|ho\s*tro|chăm\s*sóc\s*khách\s*hàng|cham\s*soc\s*khach\s*hang|khiếu\s*nại|khieu\s*nai|"
    r"báo\s*lỗi|bao\s*loi|sửa\s*chữa|sua\s*chua|hỏng|hong|trục\s*trặc|truc\s*trac|mùi\s*khét|mui\s*khet|cháy\s*nổ|chay\s*no|"
    r"lỗi\s*pin|loi\s*pin|pin\s*đỏ|pin\s*do|cứu\s*hộ|cuu\s*ho|khẩn\s*cấp|khan\s*cap|điện\s*cao\s*áp|dien\s*cao\s*ap|"
    r"bảo\s*hành|bao\s*hanh|tự\s*xử\s*lý|tu\s*xu\s*ly|"
    r"số\s*vin|so\s*vin|\bvin\b|\botp\b|lịch\s*sử\s*bảo\s*dưỡng|hồ\s*sơ\s*xe)",
    re.IGNORECASE,
)
