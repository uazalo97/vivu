import { useCallback, useRef, useState } from 'react'
import { sendMessageStream, getSuggestions } from '../lib/api'

function createMessage(role, content = '', sources = null) {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    sources,
    stages: [],
    metrics: null,
    isStreaming: false,
    createdAt: new Date().toISOString(),
  }
}

export function useChat() {
  const [messages, setMessages] = useState([
    createMessage(
      'assistant',
      'Xin chào! Tôi là **VIVU Assistant**, trợ lý tra cứu thông tin xe VinFast. Bạn muốn hỏi gì về giá, thông số, màu sắc, chính sách hay brochure?'
    ),
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const abortRef = useRef(null)

  const loadSuggestions = useCallback(async () => {
    try {
      const items = await getSuggestions()
      setSuggestions(items)
    } catch {
      setSuggestions([])
    }
  }, [])

  const sendMessage = useCallback(
    async (text) => {
      if (!text.trim() || isLoading) return

      const userMsg = createMessage('user', text.trim())
      const assistantMsg = createMessage('assistant')
      assistantMsg.isStreaming = true

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setInput('')
      setIsLoading(true)

      try {
        const stream = sendMessageStream(userMsg.content)
        abortRef.current = stream

        for await (const event of stream) {
          if (event.type === 'stage') {
            assistantMsg.stages = [...assistantMsg.stages, event.data.label]
          } else if (event.type === 'sources') {
            assistantMsg.sources = event.data
          } else if (event.type === 'delta') {
            // append token (backend gửi từng phần mới)
            assistantMsg.content += event.data.content
          } else if (event.type === 'metrics') {
            assistantMsg.metrics = event.data
          } else if (event.type === 'done') {
            assistantMsg.id = event.data.id
            assistantMsg.content = event.data.content
          }

          setMessages((prev) => {
            const next = [...prev]
            next[next.length - 1] = { ...assistantMsg }
            return next
          })
        }
      } catch (err) {
        assistantMsg.content =
          assistantMsg.content ||
          'Đã có lỗi xảy ra khi kết nối đến hệ thống. Vui lòng thử lại sau.'
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { ...assistantMsg }
          return next
        })
      } finally {
        assistantMsg.isStreaming = false
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { ...assistantMsg }
          return next
        })
        setIsLoading(false)
        abortRef.current = null
      }
    },
    [isLoading]
  )

  const clearChat = useCallback(() => {
    setMessages([
      createMessage(
        'assistant',
        'Xin chào! Tôi là **VIVU Assistant**, trợ lý tra cứu thông tin xe VinFast. Bạn muốn hỏi gì về giá, thông số, màu sắc, chính sách hay brochure?'
      ),
    ])
  }, [])

  return {
    messages,
    input,
    setInput,
    isLoading,
    suggestions,
    loadSuggestions,
    sendMessage,
    clearChat,
  }
}
