/**
 * ─────────────────────────────────────────────────────────────────────────
 * ChatWidget — điểm vào DUY NHẤT để nhúng chatbot vào bất kỳ trang nào.
 *
 * Cách nhúng vào trang chính thức:
 *   import { ChatWidget } from "./components/chat";
 *   <ChatWidget apiBase="/api" />
 *
 * - Tự render nút floating + panel chat.
 * - apiBase: đường dẫn/URL backend. Mặc định lấy từ VITE_API_BASE hoặc "/api".
 * - Widget tự chứa store riêng → mở/đóng, hội thoại độc lập với trang host.
 * ─────────────────────────────────────────────────────────────────────────
 */
import { useEffect } from "react";
import { useChatStore } from "../../store/chatStore";
import { ChatLauncher } from "./ChatLauncher";
import { ChatPanel } from "./ChatPanel";

export function ChatWidget({ apiBase }: { apiBase?: string }) {
  const open = useChatStore((s) => s.open);
  const toggleOpen = useChatStore((s) => s.toggleOpen);
  const setApiBase = useChatStore((s) => s.setApiBase);

  useEffect(() => {
    if (apiBase) setApiBase(apiBase);
  }, [apiBase, setApiBase]);

  return (
    <>
      {open && <ChatPanel />}
      <ChatLauncher open={open} onClick={toggleOpen} />
    </>
  );
}
