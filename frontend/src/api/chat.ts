/**
 * Giao tiếp với backend Vivu.
 * - chatStream(): POST /api/chat/stream — đọc SSE qua fetch stream (không dùng
 *   EventSource vì đây là POST).
 * - chatOnce():  POST /api/chat — fallback non-stream khi stream lỗi.
 */
import { API_BASE } from "../config";
import type { ChatMessagePayload, ChatResponse, SseEvent } from "./types";

/** Base URL có thể đổi lúc runtime (khi nhúng widget vào trang khác origin). */
let apiBase = API_BASE;

export function setApiBase(base: string): void {
  apiBase = base.replace(/\/$/, "");
}

/**
 * Đọc toàn bộ stream SSE, gọi onEvent cho từng event hợp lệ.
 * Ném AbortError khi tín hiệu abort — caller tự xử lý.
 */
export async function chatStream(
  message: string,
  history: ChatMessagePayload[],
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${apiBase}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body) throw new Error("Response không có body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE dùng \n\n phân cách event; parse từng dòng "data: ..."
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        try {
          const event = JSON.parse(trimmed.slice(6)) as SseEvent;
          onEvent(event);
        } catch {
          // bỏ qua frame không phải JSON hợp lệ
        }
      }
    }
  }
}

/** Fallback non-stream: POST /api/chat. */
export async function chatOnce(
  message: string,
  history: ChatMessagePayload[]
): Promise<ChatResponse> {
  const res = await fetch(`${apiBase}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data: ChatResponse = await res.json();
  return data;
}
