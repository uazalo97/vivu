# VIVU Chatbot Frontend

Giao diện chatbot RAG cho dự án VIVU, xây dựng bằng **React 18 + Vite + Tailwind CSS v4**.

## Tính năng

- Giao diện chat hiện đại, responsive.
- Sidebar gợi ý câu hỏi nhanh.
- Hiển thị nguồn tham khảo (sources) dưới mỗi câu trả lời: chunks từ Qdrant, giá từ PostgreSQL, link brochure.
- Streaming response với typing indicator.
- Dark / light mode.
- Markdown rendering cho câu trả lời.

## Công nghệ

- React 18 + Hooks
- Vite 6
- Tailwind CSS v4 (CSS-based configuration)
- lucide-react (icons)
- react-markdown

## Cài đặt

```bash
cd frontend
npm install
```

## Chạy development

```bash
npm run dev
```

Mở trình duyệt tại `http://localhost:5173`.

## Build production

```bash
npm run build
npm run preview
```

## Kết nối backend thật

Hiện tại frontend đang dùng `src/lib/mockApi.js` để demo giao diện. Khi backend FastAPI sẵn sàng, thay thế các hàm trong `mockApi.js` bằng fetch thật, ví dụ:

```javascript
export async function* sendMessageStream(message) {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // parse SSE events...
  }
}
```

Vite config đã cấu hình proxy `/api` → `http://localhost:8000`.

## Cấu trúc thư mục

```text
frontend/
├── index.html
├── package.json
├── vite.config.js
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── index.css          # Tailwind v4 + custom styles
│   ├── components/
│   │   ├── Header.jsx
│   │   ├── Sidebar.jsx
│   │   ├── ChatMessage.jsx
│   │   ├── ChatInput.jsx
│   ├── hooks/
│   │   └── useChat.js
│   └── lib/
│       └── mockApi.js
```
