/**
 * Danh sách hội thoại: auto-scroll xuống cuối, hiện chips gợi ý + tool indicator.
 */
import { useEffect, useRef } from "react";
import { useChatStore } from "../../store/chatStore";
import { MessageBubble } from "./MessageBubble";
import { SuggestionChips } from "./SuggestionChips";
import { ToolsIndicator } from "./ToolsIndicator";

export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const toolCalls = useChatStore((s) => s.toolCalls);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) {
      if (messages.length === 1 && !isStreaming) {
        el.scrollTop = 0;
      } else {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [messages, isStreaming, toolCalls]);

  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  const showSuggestions = messages.length === 1 && !isStreaming;

  return (
    <div ref={listRef} className="scroll-slim flex-1 overflow-y-auto bg-primary-soft">
      <div className="flex flex-col space-y-4 px-4 py-4 overflow-hidden">
        {messages.map((m, i) => (
          <MessageBubble
            key={m.id}
            message={m}
            streaming={isStreaming && m.id === lastAssistantId}
            isLast={i === messages.length - 1}
          />
        ))}

        {/* Gợi ý đầu hội thoại */}
        {showSuggestions && <SuggestionChips key={`suggestions-${messages[0]?.id}`} />}
      </div>
    </div>
  );
}
