/**
 * Một câu chat: bubble người dùng (xanh, phải) / bot (trắng, trái).
 * Hỗ trợ: streaming token, markdown, sources, clarify, error + retry.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../store/chatStore";
import { useChatStore } from "../../store/chatStore";
import { SourceChips } from "./SourceChips";
import { TypingDots } from "./TypingDots";
import { RotateCcw } from "lucide-react";
import logoUrl from "../../assets/images/Vinfast-logo.png";
import { useRef } from "react";

interface MessageBubbleProps {
  message: ChatMessage;
  /** Đang stream vào chính message này (message assistant cuối cùng). */
  streaming?: boolean;
  isLast?: boolean;
}

function BotAvatar() {
  return (
    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center">
      <img src={logoUrl} alt="Bot Avatar" className="h-full w-full object-contain" />
    </div>
  );
}

export function MessageBubble({ message, streaming, isLast }: MessageBubbleProps) {
  const resendLastUser = useChatStore((s) => s.resendLastUser);
  const isUser = message.role === "user";
  const showTyping = streaming && !message.content.trim();

  const timeRef = useRef(
    new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false })
  );

  /* ── User bubble ── */
  if (isUser) {
    return (
      <div className="bubble-enter flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[15px] leading-relaxed text-white">
          {message.content}
        </div>
      </div>
    );
  }

  /* ── Bot bubble ── */
  const showStreamingText = streaming && message.content.trim().length > 0;

  return (
    <div className="bubble-enter flex items-end gap-2">
      <BotAvatar />
      <div className="min-w-0 max-w-[85%]">
        <div className="mb-1 ml-1 text-[13px] font-semibold text-ink-soft/70">
          Vivu by VinFast
        </div>
        <div className="flex items-end gap-2">
          <div
            className={
              "rounded-2xl rounded-bl-md px-4 py-2.5 text-[15px] leading-relaxed " +
              (message.error
                ? "bg-okbg text-ink"
                : "bg-white text-ink")
            }
          >
          {showTyping ? (
            <TypingDots />
          ) : (
            <div className={message.content.trim() ? "md-content" : ""}>
              {/* Stream đang chạy → render text thô + con trỏ (tránh markdown nửa chừng) */}
              {showStreamingText ? (
                <>
                  <span className="whitespace-pre-wrap">{message.content}</span>
                  <span className="stream-cursor" aria-hidden>
                    ▍
                  </span>
                </>
              ) : (
                message.content.trim() && (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      a: (props) => (
                        <a {...props} target="_blank" rel="noopener noreferrer" />
                      ),
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                )
              )}
            </div>
          )}
          </div>
          <span className="mb-1 shrink-0 text-[11px] font-medium text-ink-soft/40">
            {timeRef.current}
          </span>
        </div>

        {/* Gợi ý nhỏ cho câu hỏi dạng clarify (thiếu model/version) */}
        {message.clarify && !streaming && (
          <p className="mt-1.5 text-xs text-ink-soft">
            Bạn cứ trả lời tiếp — mình sẽ hỗ trợ chi tiết hơn 👍
          </p>
        )}

        {/* Nguồn tham khảo */}
        {!streaming && message.sources && <SourceChips sources={message.sources} />}

        {/* Lỗi → nút thử lại */}
        {message.error && isLast && !streaming && (
          <button
            type="button"
            onClick={resendLastUser}
            className="mt-2 inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-primary bg-white px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary-soft"
          >
            <RotateCcw size={14} className="mr-0.5" />
            Thử lại
          </button>
        )}
      </div>
    </div>
  );
}
