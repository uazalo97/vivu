/**
 * Nút floating mở/đóng chatbox — góc phải dưới màn hình.
 */
import type { CSSProperties } from "react";

import { MessageCircle, X } from "lucide-react";

interface ChatLauncherProps {
  open: boolean;
  onClick: () => void;
  style?: CSSProperties;
  className?: string;
}

export function ChatLauncher({ open, onClick, style, className = "" }: ChatLauncherProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={open ? "Đóng chat" : "Mở chat"}
      title="Tư vấn VinFast"
      style={style}
      className={
        "fixed bottom-6 right-6 z-[60] flex h-14 w-14 cursor-pointer items-center justify-center rounded-full bg-primary text-white shadow-[0_8px_30px_rgb(0,0,0,0.12)] transition-all duration-300 sm:h-14 sm:w-14 md:h-14 md:w-14 " +
        (open ? "scale-0 opacity-0 pointer-events-none " : "hover:bg-primary-hover hover:scale-105 active:scale-95 ") +
        className
      }
    >
      <MessageCircle size={24} className="animate-in zoom-in duration-300" />
    </button>
  );
}
