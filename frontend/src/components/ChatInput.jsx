import { Send, Loader2 } from 'lucide-react'
import { useRef } from 'react'

export default function ChatInput({ value, onChange, onSubmit, isLoading }) {
  const textareaRef = useRef(null)

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit(value)
    }
  }

  return (
    <div className="sticky bottom-0 z-20 border-t border-surface-200 bg-white/90 p-3 backdrop-blur-md md:p-4">
      <div className="mx-auto flex max-w-4xl items-end gap-2 rounded-2xl border border-surface-300 bg-white p-2 shadow-float transition-colors focus-within:border-primary-400 focus-within:ring-2 focus-within:ring-primary-400/20">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Hỏi về giá, thông số, màu sắc, chính sách..."
          disabled={isLoading}
          className="max-h-40 min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] text-surface-900 outline-none placeholder:text-surface-400"
          style={{ fieldSizing: 'content' }}
        />
        <button
          onClick={() => onSubmit(value)}
          disabled={isLoading || !value.trim()}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-600 text-white shadow-chat transition-all hover:bg-primary-700 hover:shadow-float disabled:cursor-not-allowed disabled:bg-surface-300 disabled:shadow-none"
          aria-label="Gửi tin nhắn"
        >
          {isLoading ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
        </button>
      </div>
      <p className="mt-2 text-center text-xs text-surface-400">
        Nhấn Enter để gửi, Shift + Enter để xuống dòng · VIVU Assistant có thể đưa ra thông tin chưa chính xác
      </p>
    </div>
  )
}
