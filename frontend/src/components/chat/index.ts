/**
 * Public API của module chat — dùng để nhúng widget.
 *
 *   import { ChatWidget, type Source } from "…/components/chat";
 */
export { ChatWidget } from "./ChatWidget";
export { ChatPanel } from "./ChatPanel";
export { useChatStore } from "../../store/chatStore";
export type { ChatMessage } from "../../store/chatStore";
export type { SseEvent, Source, ChatRequest, ChatResponse } from "../../api/types";
