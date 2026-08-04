import { MessageSquare, Sparkles } from 'lucide-react'

export default function Sidebar({ suggestions, onSuggestionClick, isOpen, onClose }) {
  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-surface-950/40 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-72 transform border-r border-surface-200 bg-white p-4 transition-transform duration-300 ease-in-out
          md:relative md:inset-auto md:translate-x-0 md:bg-transparent md:p-0
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <div className="flex h-full flex-col md:h-[calc(100vh-5rem)]">
          <div className="mb-4 flex items-center gap-2 px-2 pt-2 md:hidden">
            <Sparkles className="text-primary-600" size={20} />
            <span className="font-semibold text-surface-900">Gợi ý câu hỏi</span>
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto px-2 pb-4">
            <p className="mb-3 hidden text-sm font-medium text-surface-500 md:block">
              Câu hỏi gợi ý
            </p>
            {suggestions.map((s, idx) => (
              <button
                key={idx}
                onClick={() => {
                  onSuggestionClick(s)
                  onClose()
                }}
                className="flex w-full items-start gap-3 rounded-xl border border-surface-200 bg-white p-3 text-left text-sm text-surface-700 shadow-chat transition-all hover:border-primary-300 hover:bg-primary-50"
              >
                <MessageSquare size={16} className="mt-0.5 shrink-0 text-primary-500" />
                <span className="line-clamp-2">{s}</span>
              </button>
            ))}
          </div>

          <div className="mt-auto border-t border-surface-200 p-2">
            <p className="text-xs leading-relaxed text-surface-500">
              Dữ liệu hiện tại là mock để demo giao diện. Sau này sẽ kết nối backend RAG thật.
            </p>
          </div>
        </div>
      </aside>
    </>
  )
}
