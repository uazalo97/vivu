/**
 * Header của chat panel: avatar + tên bot + các thao tác (thu nhỏ, xóa, đóng).
 */
import { useChatStore } from "../../store/chatStore";
import { RotateCw, X } from "lucide-react";
import logoUrl from "../../assets/images/VinFast-logo-2026.png";

export function ChatHeader() {
  const clearChat = useChatStore((s) => s.clearChat);
  const closeChat = useChatStore((s) => s.closeChat);

  return (
    <header className="flex shrink-0 items-center gap-3 bg-transparent px-4 py-3 text-ink sm:rounded-t-2xl">
      {/* Logo */}
      <div className="flex-1 flex h-6 shrink-0 items-center justify-start">
        <img src={logoUrl} alt="VinFast Logo" className="h-full w-auto object-contain" />
      </div>

      {/* Làm mới hội thoại */}
      <button
        type="button"
        onClick={clearChat}
        aria-label="Làm mới hội thoại"
        className="group relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-ink/5 hover:text-ink"
      >
        <RotateCw size={18} />
        <span className="pointer-events-none absolute -bottom-8 left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink/90 px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
          Làm mới
        </span>
      </button>

      {/* Đóng */}
      <button
        type="button"
        onClick={closeChat}
        aria-label="Đóng chat"
        className="group relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-ink-soft transition-colors hover:bg-ink/5 hover:text-ink"
      >
        <X size={20} />
        <span className="pointer-events-none absolute -bottom-8 left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink/90 px-2 py-1 text-[11px] font-medium text-white opacity-0 shadow-sm transition-opacity group-hover:opacity-100">
          Đóng
        </span>
      </button>
    </header>
  );
}
