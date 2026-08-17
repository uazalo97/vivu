/**
 * Types khớp với contract API backend (branch Trust-Foundation/Bao).
 */

export interface ChatMessagePayload {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  message: string;
  history: ChatMessagePayload[];
}

export interface Source {
  text: string;
  url: string;
  type: string;
  score?: number;
}

/** Response của POST /api/chat (non-stream, fallback). */
export interface ChatResponse {
  response: string;
  sources: Source[];
  needs_clarification: boolean;
  classify: Record<string, unknown>;
  decision: string;
  decision_log: Record<string, unknown>;
}

/** Các event của POST /api/chat/stream (SSE — parse dòng `data: {...}`). */
export type SseEvent =
  | { type: "decision"; content: string }
  | { type: "classify"; content: { specificity: string; entities: Record<string, unknown> } }
  | { type: "tool_call"; content: { tool: string; success: boolean } }
  | { type: "token"; content: string }
  | { type: "answer"; content: string }
  | { type: "clarify"; content: string }
  | { type: "sources"; content: Source[] }
  | { type: "done"; content?: unknown };
