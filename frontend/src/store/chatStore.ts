/**
 * Zustand store quản lý toàn bộ trạng thái chat.
 * Widget chat tự chứa store riêng → độc lập, dễ nhúng vào trang khác.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { chatOnce, chatStream, setApiBase } from "../api/chat";
import type { SseEvent, Source } from "../api/types";
import { BRAND, HISTORY_LIMIT, WELCOME_MESSAGE } from "../config";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  clarify?: boolean;
  error?: boolean;
}

interface ChatState {
  sessionId: string;
  open: boolean;
  messages: ChatMessage[];
  isStreaming: boolean;
  toolCalls: string[];

  setApiBase: (base: string) => void;
  toggleOpen: () => void;
  closeChat: () => void;
  openChat: () => void;
  clearChat: () => void;
  stop: () => void;
  sendMessage: (text: string) => Promise<void>;
  resendLastUser: () => void;
}

let uidCounter = 0;
function uid(): string {
  return `msg-${Date.now()}-${uidCounter++}`;
}

let abortController: AbortController | null = null;
let lastAborted = false;

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
  sessionId: crypto.randomUUID(),
  open: false,
  messages: [{ id: uid(), role: "assistant", content: WELCOME_MESSAGE }],
  isStreaming: false,
  toolCalls: [],

  setApiBase: (base) => setApiBase(base),

  toggleOpen: () => set((s) => ({ open: !s.open })),
  closeChat: () => set({ open: false }),
  openChat: () => set({ open: true }),

  clearChat: () =>
    set({
      sessionId: crypto.randomUUID(), // Reset session id on clear chat
      messages: [{ id: uid(), role: "assistant", content: WELCOME_MESSAGE }],
      toolCalls: [],
      isStreaming: false,
    }),

  stop: () => {
    lastAborted = true;
    abortController?.abort();
  },

  sendMessage: async (text) => {
    const trimmed = text.trim();
    if (!trimmed || get().isStreaming) return;

    // History = các message trước đó (backend dùng 6 message gần nhất).
    const history = get()
      .messages.filter(
        (m) => (m.role === "user" || m.role === "assistant") && m.content.trim()
      )
      .slice(-HISTORY_LIMIT)
      .map((m) => ({ role: m.role, content: m.content }));

    const userMsg: ChatMessage = { id: uid(), role: "user", content: trimmed };
    const assistantMsg: ChatMessage = { id: uid(), role: "assistant", content: "" };
    set((s) => ({
      messages: [...s.messages, userMsg, assistantMsg],
      isStreaming: true,
      toolCalls: [],
    }));
    lastAborted = false;
    abortController = new AbortController();

    const onEvent = (ev: SseEvent) => {
      if (ev.type === "tool_call" && ev.content.success !== false) {
        set((s) => ({ toolCalls: [...s.toolCalls, ev.content.tool] }));
        return;
      }
      if (ev.type === "status") {
        set((s) => ({ toolCalls: [...s.toolCalls, ev.content] }));
        return;
      }
      if (ev.type === "error") {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, content: ev.content, error: true } : m
          ),
        }));
        return;
      }
      if (ev.type === "token") {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, content: m.content + ev.content } : m
          ),
        }));
        return;
      }
      if (ev.type === "answer" || ev.type === "clarify") {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: ev.content, clarify: ev.type === "clarify" }
              : m
          ),
        }));
        return;
      }
      if (ev.type === "sources") {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, sources: ev.content } : m
          ),
        }));
      }
    };

    try {
      await chatStream(get().sessionId, trimmed, history, onEvent, abortController.signal);
    } catch (err) {
      const isAbort = (err as Error)?.name === "AbortError";
      if (!isAbort) {
        // Fallback: thử lại bằng API non-stream
        try {
          const res = await chatOnce(get().sessionId, trimmed, history);
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, content: res.response, sources: res.sources ?? [], clarify: false }
                : m
            ),
          }));
        } catch {
          set((s) => ({
            messages: s.messages.map((m) =>
              m.id === assistantMsg.id
                ? {
                    ...m,
                    content: `Xin lỗi, mình chưa thể kết nối được hệ thống lúc này. 🙏\n\nBạn vui lòng thử lại sau hoặc gọi hotline **${BRAND.hotline}** để được hỗ trợ.`,
                    error: true,
                  }
                : m
            ),
          }));
        }
      }
    } finally {
      abortController = null;

      // Nếu không có nội dung nào (stream rỗng) → hiện thông báo rõ ràng.
      const state = get();
      const msg = state.messages.find((m) => m.id === assistantMsg.id);
      const isEmpty = !msg?.content.trim();
      if (isEmpty) {
        const content = lastAborted
          ? "Bạn đã dừng câu trả lời."
          : `Xin lỗi, mình chưa thể hoàn tất câu trả lời lúc này. Vui lòng thử lại hoặc gọi hotline **${BRAND.hotline}**.`;
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content, error: !lastAborted }
              : m
          ),
        }));
      }
      set({ isStreaming: false, toolCalls: [] });
    }
  },

  resendLastUser: () => {
    const { messages, sendMessage } = get();
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) void sendMessage(lastUser.content);
  },
    }),
    {
      name: "vivu_chat_storage",
      partialize: (state) => ({
        sessionId: state.sessionId,
        messages: state.messages,
      }),
    }
  )
);
