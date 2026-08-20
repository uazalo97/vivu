/**
 * Cấu hình chung của app — tập trung mọi thứ dễ thay đổi ở 1 chỗ.
 */

export const BRAND = {
  name: "Vivu",
  tagline: "Trợ lý tư vấn VinFast",
  hotline: "1900 23 23 89",
} as const;

/** Base URL API. Dev: /api (Vite proxy → localhost:8000). */
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

/** Số message gần nhất gửi lên backend làm context. */
export const HISTORY_LIMIT = 6;

/** Gợi ý câu hỏi hiển thị đầu hội thoại. */
export const SUGGESTIONS = [
  { icon: "💰", label: "Giá xe VF 7", text: "Giá xe VF 7 là bao nhiêu?" },
  { icon: "📊", label: "So sánh VF 8 vs VF 9", text: "So sánh VF 8 và VF 9" },
  { icon: "🎁", label: "Khuyến mãi đang có", text: "VinFast đang có khuyến mãi gì?" },
  { icon: "🔋", label: "Pin & sạc", text: "Chính sách pin và sạc của VinFast như thế nào?" },
] as const;

export const WELCOME_MESSAGE = `Xin chào! 👋 Mình là **${BRAND.name}**, trợ lý tư vấn xe VinFast.

Bạn có thể hỏi mình về:
- 💰 Giá bán, ưu đãi, khuyến mãi
- 📊 Thông số kỹ thuật & so sánh các dòng xe
- 🔋 Chi phí lăn bánh, trả góp, pin & sạc
- 🏬 Showroom, đặt lịch lái thử, bảo dưỡng

Mình sẽ hỗ trợ bạn ngay!`;
