/**
 * Gợi ý câu hỏi nhanh — hiện đầu hội thoại (chỉ khi store còn 1 message welcome).
 */
import { SUGGESTIONS } from "../../config";
import { useChatStore } from "../../store/chatStore";

export function SuggestionChips() {
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);

  return (
    <div className="bubble-enter ml-9 flex flex-wrap gap-2">
      {SUGGESTIONS.map((s) => (
        <button
          key={s.text}
          type="button"
          disabled={isStreaming}
          onClick={() => void sendMessage(s.text)}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-dashed border-primary/40 bg-white px-3 py-1.5 text-[13px] font-medium text-primary transition-all hover:border-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span aria-hidden>{s.icon}</span>
          {s.label}
        </button>
      ))}
    </div>
  );
}
