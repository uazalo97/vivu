/**
 * Zustand store quản lý toàn bộ trạng thái chat.
 * Widget chat tự chứa store riêng → độc lập, dễ nhúng vào trang khác.
 */
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
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
  status?: "sending" | "streaming" | "done" | "error";
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

const vivuStorage = {
  getItem(name: string): string | null {
    try {
      return localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem(name: string, value: string): void {
    try {
      localStorage.setItem(name, value);
    } catch (e) {
      const err = e as { name?: string; code?: number };
      const isQuota =
        (e instanceof DOMException && (e.name === "QuotaExceededError" || e.code === 22 || e.code === 1014)) ||
        err?.name === "QuotaExceededError" ||
        err?.code === 22 ||
        err?.code === 1014;
      if (isQuota) {
        console.warn("[vivu_chat_storage] QuotaExceededError, pruning to last 20 and retrying", e);
        try {
          const parsed = JSON.parse(value) as { state?: { messages?: unknown[] } };
          if (Array.isArray(parsed?.state?.messages) && parsed.state.messages.length > 20) {
            parsed.state.messages = parsed.state.messages.slice(-20);
            localStorage.setItem(name, JSON.stringify(parsed));
            return;
          }
        } catch {
          // ignore parse error
        }
        try {
          localStorage.removeItem(name);
        } catch {
          // ignore
        }
        console.warn("[vivu_chat_storage] cleared storage after QuotaExceeded");
      } else {
        console.warn("[vivu_chat_storage] setItem failed", e);
        try {
          localStorage.removeItem(name);
        } catch {
          // ignore
        }
      }
    }
  },
  removeItem(name: string): void {
    try {
      localStorage.removeItem(name);
    } catch {
      // ignore
    }
  },
};

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

    let bufferedContent = "";
    let bufferedSources: Source[] = [];
    let isClarify = false;

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
        // Stream thật: render NGAY từng token (không gom buffer chờ done)
        bufferedContent += ev.content;
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, content: bufferedContent, status: "streaming" } : m
          ),
        }));
        return;
      }
      if (ev.type === "answer" || ev.type === "clarify") {
        bufferedContent = ev.content;
        isClarify = ev.type === "clarify";
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, content: bufferedContent, clarify: isClarify, status: "streaming" } : m
          ),
        }));
        return;
      }
      if (ev.type === "sources") {
        bufferedSources = ev.content;
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, sources: bufferedSources } : m
          ),
        }));
        return;
      }
      if (ev.type === "done") {
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, content: bufferedContent, sources: bufferedSources, clarify: isClarify, status: "done" }
              : m
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
      version: 2,
      storage: createJSONStorage(() => vivuStorage as unknown as Storage),
      partialize: (state) => ({
        sessionId: state.sessionId,
        messages: state.messages.slice(-50),
      }),
      migrate: (persistedState: unknown, version: number) => {
        const s = persistedState as { messages?: ChatMessage[] } | null | undefined;
        if (version < 2 && s && typeof s === "object") {
          s.messages = (s.messages?.slice(-50) ?? []) as ChatMessage[];
        }
        return persistedState as ChatState;
      },
      onRehydrateStorage: () => (state, error) => {
        void state;
        if (error) {
          console.warn("[vivu_chat_storage] rehydrate failed", error);
        }
      },
    }
  )
);
