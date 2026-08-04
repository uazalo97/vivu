import { Bot, User, Check, Loader2, Zap } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

// Tự chuyển URL trần trong câu trả lời thành link markdown (vì react-markdown mặc định
// không nhận diện URL trần). Không cần remark-gfm.
function linkifyUrls(text) {
  if (!text) return text
  return text.replace(
    /(^|\s)(https?:\/\/[^\s<>]+?)(?=[\s<>]|$)/g,
    (match, lead, url) => {
      const clean = url.replace(/[.,;:!?)]+$/, '')
      return `${lead}[${clean}](${clean})`
    }
  )
}

function StepsIndicator({ stages, isStreaming }) {
  if (!stages || stages.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-surface-500">
      {stages.map((label, i) => {
        const isLast = i === stages.length - 1
        const done = !isStreaming || !isLast
        return (
          <span key={i} className="inline-flex items-center gap-1.5">
            {done ? (
              <Check size={12} className="text-emerald-500" />
            ) : (
              <Loader2 size={12} className="animate-spin text-primary-500" />
            )}
            {label}
            {!isLast && <span className="text-surface-300">→</span>}
          </span>
        )
      })}
    </div>
  )
}

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`message-enter flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div className={`flex max-w-[90%] gap-3 md:max-w-[82%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
            isUser
              ? 'bg-surface-200 text-surface-700'
              : 'bg-gradient-to-br from-primary-500 to-accent-500 text-white'
          }`}
        >
          {isUser ? <User size={18} /> : <Bot size={18} />}
        </div>

        <div className={`min-w-0 ${isUser ? 'items-end' : 'items-start'}`}>
          <div
            className={`rounded-2xl px-4 py-3 text-[15px] leading-relaxed shadow-chat ${
              isUser ? 'bg-primary-600 text-white' : 'bg-white text-surface-800'
            }`}
          >
            {isUser ? (
              <p>{message.content}</p>
            ) : (
              <div className="markdown-body">
                <ReactMarkdown
                  components={{
                    // Link trong câu trả lời luôn mở tab mới, không điều hướng trang hiện tại
                    a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
                  }}
                >
                  {linkifyUrls(message.content) || ' '}
                </ReactMarkdown>
                <StepsIndicator stages={message.stages} isStreaming={message.isStreaming} />
                {message.metrics && (
                  <div className="mt-2 flex items-center gap-1 border-t border-surface-100 pt-2 text-[11px] text-surface-400">
                    <Zap size={11} />
                    {message.metrics.total_ms}ms · {message.metrics.tokens_in} in /{' '}
                    {message.metrics.tokens_out} out
                    {message.metrics.ttft_ms != null && ` · TTFT ${message.metrics.ttft_ms}ms`}
                  </div>
                )}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  )
}
