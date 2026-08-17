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

  /* ── User bubble ── */
  if (isUser) {
    return (
      <div className="bubble-enter flex flex-col items-end">
        <div className="mb-1 mr-1 text-[13px] font-semibold text-ink-soft/70">
          Bạn
        </div>
        <div className="flex items-end gap-2 max-w-[85%]">
          <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[15px] leading-relaxed text-white">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  /* ── Bot bubble ── */

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
              {message.content.trim() && (
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
              )}
            </div>
          )}
          </div>
        </div>

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
