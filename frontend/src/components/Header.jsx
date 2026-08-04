import { Bot, Trash2 } from 'lucide-react'

export default function Header({ onClear }) {
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b border-surface-200 bg-white/80 px-4 py-3 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 text-white shadow-chat">
          <Bot size={22} />
        </div>
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-surface-900">
            VIVU Assistant
          </h1>
          <p className="text-xs text-surface-500">Trợ lý tra cứu xe VinFast</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onClear}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-surface-600 transition-colors hover:bg-surface-100"
          title="Xóa cuộc trò chuyện"
        >
          <Trash2 size={18} />
          <span className="hidden sm:inline">Xóa chat</span>
        </button>
      </div>
    </header>
  )
}
