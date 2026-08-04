/**
 * API thật gọi backend FastAPI (proxy /api → localhost:8000).
 * Stream qua SSE. Event contract: {type, data}
 *   type ∈ stage | sources | delta | metrics | done
 */

const SUGGESTIONS = [
  'VF 9 Plus giá bao nhiêu?',
  'VF 8 có những màu ngoại thất nào?',
  'Chính sách bảo hành pin VinFast như thế nào?',
  'VF 6 Eco và VF 6 Plus khác gì nhau?',
  'Trễ hạn thanh toán phí thuê pin thì sao?',
  'Tải brochure VF 9 ở đâu?',
]

/**
 * Gửi message → stream SSE events ({type, data}).
 * parse `data: {json}` theo chuẩn SSE.
 */
export async function* sendMessageStream(message) {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status} — backend không phản hồi`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Tách từng SSE event theo '\n\n'
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data:')) continue
        const payload = line.slice(5).trim()
        if (!payload || payload === '[DONE]') continue
        try {
          const event = JSON.parse(payload)
          if (event && event.type) yield event
        } catch {
          /* bỏ event lỗi */
        }
      }
    }
  }
}

export function getSuggestions() {
  return Promise.resolve([...SUGGESTIONS])
}

export async function checkHealth() {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
