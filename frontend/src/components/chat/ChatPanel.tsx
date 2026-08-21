/**
 * Khung chat chính: header + message list + input.
 * Responsive: full-screen trên mobile, panel 400px góc phải dưới trên desktop.
 */
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { InputBar } from "./InputBar";

export function ChatPanel() {
  return (
    <div
      role="dialog"
      aria-label="Chat tư vấn VinFast"
      className="fixed inset-0 z-[60] flex flex-col overflow-hidden sm:overflow-visible bg-white/95 backdrop-blur-xl shadow-[0_8px_40px_rgb(0,0,0,0.12)] sm:inset-auto sm:bottom-6 sm:right-6 sm:h-[min(80vh,700px)] sm:w-[450px] sm:rounded-2xl transition-all animate-in slide-in-from-bottom-6 fade-in duration-300"
    >
      <ChatHeader />
      <MessageList />
      <InputBar />
    </div>
  );
}
