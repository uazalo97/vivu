# Vivu Chat UI — Frontend

Chatbox tư vấn xe VinFast, kết nối backend FastAPI (branch `Trust-Foundation/Bao`).
Chatbox được thiết kế **độc lập** — dễ nhúng vào landing page chính thức.

## Chạy

```bash
npm install
npm run dev      # http://localhost:5173 (proxy /api → localhost:8000)
npm run build    # build production (đầu ra dist/)
npm run preview  # xem thử build
```

> Backend cần chạy trên `:8000` (xem `GUIDE.md` ở backend) để chat chạy được.

## Cấu trúc thư mục

```
src/
├─ config.ts                 # Brand, API base, suggestions, welcome message (dễ chỉnh)
├─ api/
│  ├─ types.ts               # Types khớp contract backend (SseEvent, Source...)
│  └─ chat.ts                # chatStream() SSE + chatOnce() fallback
├─ store/
│  └─ chatStore.ts           # Zustand: messages, streaming, tools, actions
└─ components/
   ├─ landing/
   │  └─ LandingPage.tsx     # Landing page (TẠM ĐỂ TRẮNG — sẽ thiết kế sau)
   └─ chat/                  # TOÀN BỘ widget chat, độc lập
      ├─ ChatWidget.tsx      # ĐIỂM VÀO nhúng (floating button + panel)
      ├─ ChatPanel.tsx       # Khung chat (header + list + input)
      ├─ ChatHeader.tsx      # Avatar, tên bot, xóa hội thoại, đóng
      ├─ MessageList.tsx     # Danh sách + auto-scroll
      ├─ MessageBubble.tsx   # Bubble user/bot, markdown, streaming, sources, error
      ├─ SourceChips.tsx     # Chips nguồn tham khảo
      ├─ ToolsIndicator.tsx  # "Đang tra cứu ..." khi agent gọi tool
      ├─ SuggestionChips.tsx # Gợi ý câu hỏi đầu hội thoại
      ├─ InputBar.tsx        # Textarea + nút gửi/dừng
      └─ index.ts            # Public exports cho việc nhúng
```

## Nhúng vào trang chính thức

```tsx
import { ChatWidget } from "./components/chat";

<ChatWidget apiBase="/api" />   // mặc định /api, đổi được lúc runtime
```

- **Cùng origin**: để `apiBase="/api"`, cấu hình proxy/reverse trên server trang chính thức trỏ về backend.
- **Khác origin**: đổi `apiBase="https://api.example.com"` và backend phải thêm **CORS middleware** (hiện backend chưa có).

## Design tokens (đã chốt)

| Token              | Giá trị   |
| ------------------ | ----------- |
| `color-primary`  | `#2C72C6` |
| `color-bg`       | `#FFFFFF` |
| `font-family`    | Mulish      |
| `font-size-base` | `16px`    |

Xem chi tiết plan: [`plan.md`](./plan.md).

## Việc còn lại

- [ ] Thiết kế landing page chính thức (đang để trắng).
- [ ] Nếu chạy production khác origin: thêm CORS vào backend.
