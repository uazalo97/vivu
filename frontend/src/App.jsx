import { useEffect, useRef, useState } from 'react'
import { Bot, Menu } from 'lucide-react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import ChatMessage from './components/ChatMessage'
import ChatInput from './components/ChatInput'
import { useChat } from './hooks/useChat'

function TypingIndicator() {
  return (
    <div className="flex w-full justify-start">
      <div className="flex max-w-[82%] gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-accent-500 text-white">
          <Bot size={18} />
        </div>
        <div className="flex items-center gap-1 rounded-2xl bg-white px-4 py-3 shadow-chat">
          <span className="typing-dot h-2 w-2 rounded-full bg-surface-400" />
          <span className="typing-dot h-2 w-2 rounded-full bg-surface-400" />
          <span className="typing-dot h-2 w-2 rounded-full bg-surface-400" />
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const scrollRef = useRef(null)
  const bottomRef = useRef(null)

  const { messages, input, setInput, isLoading, suggestions, loadSuggestions, sendMessage, clearChat } =
    useChat()

  useEffect(() => {
    loadSuggestions()
  }, [loadSuggestions])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSuggestionClick = (text) => {
    sendMessage(text)
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-surface-50">
      <Header onClear={clearChat} />

      <div className="relative flex flex-1 overflow-hidden">
        <button
          onClick={() => setSidebarOpen(true)}
          className="absolute left-4 top-4 z-10 rounded-lg border border-surface-200 bg-white p-2 text-surface-600 shadow-chat hover:bg-surface-50 md:hidden"
          aria-label="Mở gợi ý"
        >
          <Menu size={20} />
        </button>

        <Sidebar
          suggestions={suggestions}
          onSuggestionClick={handleSuggestionClick}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <main className="flex flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
            <div className="mx-auto flex max-w-4xl flex-col gap-6">
              {messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
              {isLoading && messages[messages.length - 1]?.role !== 'assistant' && (
                <TypingIndicator />
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={sendMessage}
            isLoading={isLoading}
          />
        </main>
      </div>
    </div>
  )
}
