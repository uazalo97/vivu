/**
 * Mock API cho chatbot RAG.
 * Sau này khi backend FastAPI sẵn sàng, chỉ cần thay thế hàm sendMessage
 * bằng fetch thật tới /api/chat/stream.
 */

const MOCK_SUGGESTIONS = [
  'VF 9 Plus giá bao nhiêu?',
  'VF 8 có những màu ngoại thất nào?',
  'Chính sách bảo hành pin VinFast như thế nào?',
  'VF 6 Eco và VF 6 Plus khác gì nhau?',
  'Chi phí lăn bánh VF 7 tại Hà Nội?',
  'Tải brochure VF 9 ở đâu?',
]

const MOCK_CHUNKS = [
  {
    id: 'vivu_specs:vf9:plus:thong_so_ky_thuat:1',
    collection: 'vivu_specs',
    model_id: 'VF9',
    edition_id: 'Plus',
    section_path: ['thong_so_ky_thuat', 'Hiệu suất và động cơ'],
    text: 'VF9 Plus sử dụng động cơ điện công suất tối đa 300 kW (402 hp), mô-men xoắn cực đại 620 Nm. Xe tăng tốc 0–100 km/h trong 6,3 giây, trang bị pin có dung lượng 123 kWh theo chuẩn NEDC.',
    source_url: 'https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html',
    score: 0.92,
  },
  {
    id: 'vivu_product_info:vf9:all:mau_sac:2',
    collection: 'vivu_product_info',
    model_id: 'VF9',
    edition_id: null,
    section_path: ['mau_sac', 'Ngoại thất'],
    text: 'VF9 cung cấp 6 lựa chọn màu ngoại thất: VinFast Blue, Neptune Grey, Jet Black, Sunset Orange, Silver, và Deep Ocean. Nội thất có 2 tông màu Be và Black.',
    source_url: 'https://vinfastauto.com/vn_vi/vf9',
    score: 0.88,
  },
  {
    id: 'vivu_policy:vf9:all:bao_hanh:1',
    collection: 'vivu_policy',
    model_id: 'VF9',
    edition_id: null,
    section_path: ['chinh_sach', 'Bảo hành'],
    text: 'VinFast áp dụng chính sách bảo hành 10 năm hoặc 200.000 km cho pin và 3 năm không giới hạn km cho xe điện. Điều kiện bảo hành yêu cầu bảo dưỡng định kỳ tại hệ thống đại lý chính hãng.',
    source_url: 'https://vinfastauto.com/vn_vi/chinh-sach-bao-hanh',
    score: 0.85,
  },
]

const MOCK_PRICE = {
  model_id: 'VF9',
  edition_id: 'Plus',
  price_list_vnd: 1529000000,
  price_promo_vnd: 1452550000,
  promo_label: 'Ưu đãi đặt cọc 2026',
  vat_included: true,
  battery_included: true,
  valid_from: '2026-07-01',
  source_url: 'https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html',
  updated_at: '2026-08-03T10:00:00',
}

const MOCK_BROCHURES = [
  'https://storage.googleapis.com/vinfast-data-01/brochure/VF9_Brochure_03022026.pdf',
  'https://storage.googleapis.com/vinfast-data-01/brochure/VF8_Brochure_03022026.pdf',
]

function formatVnd(value) {
  if (!value) return null
  return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(value)
}

function buildResponse(query) {
  const lower = query.toLowerCase()
  const hasPrice = /giá|giá bao nhiêu|niêm yết|ưu đãi|khuyến mãi|đặt cọc/.test(lower)
  const hasColor = /màu|mau sac|ngoại thất/.test(lower)
  const hasWarranty = /bảo hành|bao hanh|pin/.test(lower)
  const hasBrochure = /brochure|tải/.test(lower)
  const hasCost = /lăn bánh|lan banh|chi phí/.test(lower)

  let answer = ''

  if (hasCost) {
    answer = `Để tính chi phí lăn bánh chính xác cho VF 9 Plus tại Hà Nội, bạn cần cung cấp thêm thông tin về phương thức thanh toán (trả thẳng/trả góp), loại hình đăng ký (cá nhân/công ty), và có thuê pin hay mua pin không.\n\nBạn có thể dùng công cụ tính chi phí lăn bánh chính thức của VinFast tại link bên dưới. Chatbot chỉ cung cấp link tham khảo, không tự nhập số liệu.`
  } else if (hasPrice) {
    const list = formatVnd(MOCK_PRICE.price_list_vnd)
    const promo = formatVnd(MOCK_PRICE.price_promo_vnd)
    answer = `**VF 9 Plus** hiện có giá niêm yết **${list}** và đang được ưu đãi còn **${promo}** trong chương trình **"${MOCK_PRICE.promo_label}"**.\n\nGiá đã bao gồm VAT và pin. Thông tin được cập nhật ngày ${new Date(MOCK_PRICE.updated_at).toLocaleDateString('vi-VN')}.`
  } else if (hasColor) {
    answer = `**VF 9** có 6 lựa chọn màu ngoại thất: VinFast Blue, Neptune Grey, Jet Black, Sunset Orange, Silver và Deep Ocean. Nội thất có 2 tông màu Be và Black. Bạn muốn xem xe màu nào?`
  } else if (hasWarranty) {
    answer = `VinFast áp dụng chính sách bảo hành **10 năm hoặc 200.000 km cho pin** và **3 năm không giới hạn km cho xe điện**. Điều kiện bảo hành yêu cầu bảo dưỡng định kỳ tại hệ thống đại lý chính hãng.`
  } else if (hasBrochure) {
    answer = `Bạn có thể tải brochure VF 9 tại link bên dưới. Đây là tài liệu chính thống từ VinFast, chatbot chỉ cung cấp link tham khảo.`
  } else {
    answer = `Cảm ơn bạn đã quan tâm đến xe VinFast. Tôi có thể hỗ trợ tra cứu **giá xe, thông số kỹ thuật, màu sắc, chính sách bảo hành và link brochure**. Bạn muốn hỏi gì thêm không?`
  }

  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: answer,
    sources: {
      chunks: MOCK_CHUNKS,
      price: hasPrice || hasCost ? MOCK_PRICE : null,
      brochures: hasBrochure || hasCost ? MOCK_BROCHURES : [],
    },
    createdAt: new Date().toISOString(),
  }
}

/**
 * Giả lập streaming response.
 * Trả về async generator yield {type, data}.
 */
export async function* sendMessageStream(message) {
  // Simulate network latency
  await new Promise((resolve) => setTimeout(resolve, 600))

  const response = buildResponse(message)

  // Yield sources first
  yield { type: 'sources', data: response.sources }

  await new Promise((resolve) => setTimeout(resolve, 200))

  // Stream answer word by word
  const words = response.content.split(/(\s+)/)
  let accumulated = ''
  for (const word of words) {
    accumulated += word
    yield { type: 'delta', data: { content: accumulated } }
    await new Promise((resolve) => setTimeout(resolve, 18))
  }

  yield { type: 'done', data: { id: response.id, content: response.content } }
}

export function getSuggestions() {
  return Promise.resolve([...MOCK_SUGGESTIONS])
}

export function checkHealth() {
  return Promise.resolve({
    status: 'ok',
    mode: 'mock',
    qdrant: 'mock',
    postgres: 'mock',
    llm: 'mock',
  })
}
