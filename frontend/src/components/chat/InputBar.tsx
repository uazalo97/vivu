/**
 * Vùng nhập liệu: textarea auto-grow, Enter gửi / Shift+Enter xuống dòng.
 * Khi đang stream → nút gửi chuyển thành nút "Dừng".
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useChatStore } from "../../store/chatStore";
import { SendHorizontal, Square } from "lucide-react";

export function InputBar() {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stop = useChatStore((s) => s.stop);
  const isStreaming = useChatStore((s) => s.isStreaming);

  // Auto-grow tối đa ~4 dòng
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }, [value]);

  const handleSend = () => {
    const text = value.trim();
    if (!text || isStreaming) return;
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    void sendMessage(text);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="shrink-0 bg-white p-4">
      <div className="relative flex items-end gap-2 rounded-[24px] bg-[#f3f4f6] px-2 py-1.5 focus-within:bg-[#f3f4f6] focus-within:ring-1 focus-within:ring-primary/20 transition-all">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          maxLength={2000}
          autoFocus
          placeholder="Nhập tin nhắn..."
          aria-label="Tin nhắn"
          className="scrollbar-hide max-h-[120px] flex-1 resize-none bg-transparent px-4 py-2 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-soft/70"
        />
        <button
          type="button"
          onClick={isStreaming ? stop : handleSend}
          disabled={!isStreaming && !value.trim()}
          aria-label={isStreaming ? "Dừng" : "Gửi"}
          className={
            "group relative flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-full transition-all duration-200 " +
            (isStreaming
              ? "text-ink hover:bg-ink/10 active:scale-95"
              : value.trim()
                ? "text-primary hover:bg-primary/10 active:scale-95"
                : "text-ink/30 bg-transparent disabled:cursor-not-allowed")
          }
        >
          {isStreaming ? (
            <Square fill="currentColor" size={20} />
          ) : (
            <SendHorizontal size={24}/>
          )}
          <span className="pointer-events-none absolute -top-8 left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink/90 px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
            {isStreaming ? "Dừng tạo câu trả lời" : "Gửi"}
          </span>
        </button>
      </div>
    </div>
  );
}
