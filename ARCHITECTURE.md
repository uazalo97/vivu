# Vivu Chatbot — Kiến Trúc Hệ Thống

> Tài liệu phục vụ thuyết trình và Q&A về kiến trúc, luồng hoạt động của hệ thống chatbot tư vấn xe VinFast.

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Luồng xử lý request (LangGraph Pipeline)](#2-luồng-xử-lý-request-langgraph-pipeline)
3. [Cơ chế phân loại (Classify Node)](#3-cơ-chế-phân-loại-classify-node)
4. [Cơ chế retrieval (Qdrant Hybrid Search)](#4-cơ-chế-retrieval-qdrant-hybrid-search)
5. [Cơ chế caching (6 tầng)](#5-cơ-chế-caching-6-tầng)
6. [Session management (Redis)](#6-session-management-redis)
7. [Frontend architecture](#7-frontend-architecture)
8. [Data pipeline](#8-data-pipeline)
9. [Safety & guardrails](#9-safety--guardrails)
10. [Monitoring & metrics](#10-monitoring--metrics)
11. [Infrastructure & deployment](#11-infrastructure--deployment)
12. [Q&A thường gặp](#12-qa-thường-gặp)

---

## 1. Tổng quan hệ thống

Vivu là chatbot tư vấn xe VinFast, sử dụng kiến trúc **RAG (Retrieval-Augmented Generation)** với LangGraph pipeline. Hệ thống kết hợp **deterministic routing** (regex, không dùng LLM cho phân loại) + **LLM synthesis** (chỉ dùng LLM ở bước cuối tổng hợp câu trả lời).

### Sơ đồ kiến trúc tổng thể

```
┌─────────────────┐       ┌────────────────────────────────────────────┐       ┌─────────────────┐
│                 │       │                                            │       │                 │
│    Frontend     │──────→│        FastAPI + LangGraph Agent           │──────→│   Neon PG       │
│   React / Vite  │  SSE  │                                            │       │   (serverless)  │
│   Port 5173     │←──────│   classify → tools → generate → validate   │←──────│                 │
│                 │       │              → respond                     │       └─────────────────┘
└─────────────────┘       │                                            │
                          │   • Rate limiting (Redis, 10 msg/10s)      │       ┌─────────────────┐
                          │   • Backpressure (50 concurrent max)       │──────→│                 │
                          │   • Session store (Redis LIST + HASH)      │       │  Qdrant Cloud   │
                          │   • LLM fallback chain                     │       │  (vector DB)    │
                          │                                            │       └─────────────────┘
                          └────────────────────────────────────────────┘
                                           │                            ┌─────────────────┐
                                           │                            │                 │
                                 ┌──────────────────┐                   │  Upstash Redis  │
                                 │    OpenAI API     │                   │  (cache+session) │
                                 │    (LLM + embed)  │                   └─────────────────┘
                                 │    Cohere (rerank) │
                                 └──────────────────┘
```

### Công nghệ chính

| Layer | Công nghệ |
|-------|-----------|
| Backend | Python 3.11, FastAPI, LangGraph, uvicorn |
| Frontend | React 18, TypeScript, Vite, Zustand, Tailwind CSS |
| Database | PostgreSQL (Neon serverless), Redis (Upstash), Qdrant (cloud) |
| LLM | OpenAI GPT-4o-mini (primary), fallback model, Cohere rerank |
| Infrastructure | Docker, Nginx reverse proxy, AWS Lightsail |

### Design principles

1. **Fail-open everywhere** — Redis down → cache miss, PG down → empty defaults, Qdrant down → no KB results. Không có single point of failure.
2. **Deterministic first** — 4/5 node trong pipeline là regex-based, không gọi LLM. Tiết kiệm chi phí và giảm latency.
3. **True streaming** — Token-by-token qua SSE, frontend render real-time.
4. **Grounded answers** — 3 lớp chống hallucination: prompt, evidence scoring, number verification.

---

## 2. Luồng xử lý request (LangGraph Pipeline)

Mỗi request đi qua **5 node** theo thứ tự:

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. CLASSIFY NODE (deterministic, <1ms, KHÔNG gọi LLM)          │
│     • Regex safety/privacy/handoff gate → refuse                 │
│     • Regex greeting → greeting                                  │
│     • Regex utility (showroom, booking, loan) → utility          │
│     • Extract model_code + version từ query                      │
│     • Classify topic (giá, pin, màu sắc, thông số...)            │
│     • Route: clarify / out_of_scope / answer                     │
└─────────────────────────────────────────────────────────────────┘
    │
    ├─ clarify / OOS / refuse / greeting → RESPOND (skip tools + LLM)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. CALL TOOLS NODE (deterministic, async, có cache)             │
│     • Topic → tool mapping (xem bảng bên dưới)                   │
│     • Cross-model: parallel get_specs/get_price cho N models     │
│     • System prompt fetch SONG SONG với tool calls (~200ms saved)│
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. GENERATE NODE (LLM call — BƯỚC DUY NHẤT dùng LLM)           │
│     • build_structured_context(): format tool results → text     │
│     • SYNTHESIZE_PROMPT: "CHỈ dùng thông tin trong context"      │
│     • stream_chat_with_fallback(): primary → fallback model      │
│     • Token-level streaming qua LangGraph custom stream          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. VALIDATE NODE (deterministic grounding check)                │
│     • assess_evidence(): score specs bằng keyword + cosine sim   │
│     • _check_grounding(): verify số liệu trong response khớp    │
│       với tool results (anti-hallucination)                      │
│     • validate_citations(): filter valid source URLs             │
│     • Nếu "insufficient" → refuse                                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. RESPOND NODE                                                 │
│     • Build AgentResult (response, sources, decision_log)        │
│     • Record to LogStore (in-memory, exportable JSONL)           │
│     • Return SSE stream to frontend                              │
└─────────────────────────────────────────────────────────────────┘
```

### Graph edges

```python
classify → [conditional]
    ├─ answer     → call_tools → generate → validate → respond → END
    ├─ clarify    → respond → END
    ├─ out_of_scope → respond → END
    ├─ refuse     → respond → END
    └─ greeting   → respond → END
```

### Tại sao 4/5 node không dùng LLM?

| Node | LLM? | Latency | Chi phí |
|------|------|---------|---------|
| classify | Không (regex) | <1ms | $0 |
| call_tools | Không (DB query) | 50-200ms | $0 |
| generate | **Có** | 1-3s | ~$0.001 |
| validate | Không (rule-based) | <10ms | $0 |
| respond | Không (format) | <1ms | $0 |

Với ~1000 requests/ngày, kiến trúc này tiết kiệm ~$1/ngày + 200-400ms latency so với dùng LLM cho classification.

---

## 3. Cơ chế phân loại (Classify Node)

### Flow phân loại

```
Query: "VF 2 giá bao nhiêu?"
    │
    ├─ Safety gate (pin cháy, rò điện)?        → KHÔNG
    ├─ Privacy gate (OTP, CCCD, tài khoản)?    → KHÔNG
    ├─ Handoff gate (gặp nhân viên)?           → KHÔNG
    ├─ Greeting ("xin chào", "cảm ơn")?        → KHÔNG
    ├─ Ambiguous pronoun ("xe này", "mẫu này")?→ KHÔNG
    ├─ Utility (showroom, booking, loan)?      → KHÔNG
    ├─ Recommend ("nên mua", "gia đình")?      → KHÔNG
    ├─ Multi-model comparison (2+ models)?     → KHÔNG
    │
    ├─ Extract entities: model_code="VF 2", version=None
    ├─ Classify topic: "giá" (match regex r"\bgi[áa]\b")
    │
    └─ Decision: answer, category="giá", allowed_tools={get_price}
```

### Topic → Tool mapping

| Topic | Tools được gọi | Nguồn dữ liệu |
|-------|----------------|----------------|
| `giá` | `get_price` | PG `price_list_active` |
| `màu_sắc` | `get_colors` + `search_kb` | PG `car_colors_active` + Qdrant |
| `tổng_quan` | `get_price` + `get_specs` + `get_colors` | PG (nhiều bảng) |
| `thông_số_kỹ_thuật` | `get_specs(category)` | PG `car_specs` |
| `pin_và_sạc` | `get_specs("battery")` | PG `car_specs` |
| `an_toàn` | `get_specs("safety"+"adas")` + `search_kb` | PG + Qdrant |
| `option` | `get_options` + `search_kb` | PG `car_options_active` + Qdrant |
| `phiên_bản` | `list_available_models` + `get_specs` | PG `edition_active` |
| `kích_thước` | `get_specs("dimension")` | PG `car_specs` |
| `general` (có model) | → treat as `tổng_quan` | PG (full) |

### Các quyết định đặc biệt

| Pattern | Decision | Lý do |
|---------|----------|-------|
| "xe này giá bao nhiêu" | `clarify` | Ambiguous pronoun, thiếu model |
| "pin bao nhiêu kWh" (no model) | `clarify` | Thiếu model |
| "vf8 đi được bao xa" (no version) | `clarify` | Version-dependent topic, thiếu version |
| "xe nào có camera 360" | `answer` | Cross-model feature scan |
| "so sánh vf6 và vf8" | `answer` | Multi-model comparison |
| "viết code Python" | `out_of_scope` | Không liên quan VinFast |
| "pin đỏ, xe cháy" | `refuse` | Safety gate → hotline |

---

## 4. Cơ chế retrieval (Qdrant Hybrid Search)

### Flow retrieval

```
Query
    │
    ├─→ Embed (text-embedding-3-small, 1536 dim, cached 7 ngày)
    │
    ├─→ Dense search (song song 3 collections)
    │     • vivu_product_info — thông tin sản phẩm
    │     • vivu_policy — chính sách bảo hành, thanh toán
    │     • vivu_maintenance — bảo dưỡng, cứu hộ
    │
    ├─→ Sparse search (BM25 TF-IDF, Vietnamese tokenization)
    │
    ▼
RRF Fusion (k=60)
    │
    ▼
Dedup → Nav-menu filter → Cohere Rerank (multilingual-v3.0)
    │
    ▼
Top-K results → Cache (TTL 2h)
```

### Collections Qdrant

| Collection | Nội dung | Versioned |
|------------|----------|-----------|
| `vivu_product_info` | Thông tin sản phẩm xe | `<name>__<version>` + alias |
| `vivu_policy` | Chính sách bảo hành, thanh toán | Tương tự |
| `vivu_maintenance` | Bảo dưỡng, cứu hộ | Tương tự |
| `sparse` | BM25 TF-IDF index | `<name>__<version>` |

### Versioned collections

Mỗi collection có phiên bản `<name>__<version>` (e.g., `vivu_product_info__v2`) với alias để atomic promote/rollback. Khi promote version mới → swap alias, không downtime.

---

## 5. Cơ chế caching (6 tầng)

| Tầng | Key pattern | TTL | Mục đích |
|-------|-------------|-----|----------|
| Specs cache | `cache:{dv}:specs:{model}:{ver}:{cat}` | 24h | Thông số kỹ thuật |
| Price cache | `cache:{dv}:price:{model}:{ver}` | 15min | Giá (hay thay đổi) |
| List models | `cache:{dv}:list_models` | 1h | Danh sách xe |
| Embedding cache | `emb:{model}:{sha1}` | 7 ngày | Vector embedding |
| Hybrid search | `hs:{dv}:{query_hash}:...` | 2h | Kết quả search KB |
| KB search | `cache:kb:{dv}:...` | 2h | Knowledge base |

### Anti-stale mechanism

- Cache key chứa `data_version` từ PG `ingest_version.is_current`
- Khi data mới promote → key mới tự动生成, key cũ hết TTL tự xóa
- In-memory memo: 60s TTL cho `data_version()` query (giảm PG round-trip)

### Invalidation

```python
invalidate_entity(key)        # Xóa 1 key
invalidate_model(model_code)  # SCAN prefix delete cho model
invalidate_all()              # Nuclear: xóa tất cả cache + reset data_version
```

---

## 6. Session management (Redis)

### Cấu trúc dữ liệu

```
session:{id}:history  →  LIST (max 20 messages, sliding window RPUSH + LTRIM)
session:{id}:context  →  HASH {model_code, version, last_topic}
TTL: 6 giờ
```

### Multi-turn context flow

```
Turn 1: "VF 8 giá bao nhiêu?"
    → classify: model=VF 8, topic=giá
    → Redis: context.model_code=VF 8, context.last_topic=giá

Turn 2: "Còn màu sắc thì sao?"
    → classify: no model in query → inherit model=VF 8 từ history
    → topic=màu_sắc (từ query)
    → Tools: get_colors("VF 8")

Turn 3: "Bản Plus giá bao nhiêu?"
    → classify: version=Plus, inherit model=VF 8
    → topic=giá
    → Tools: get_price("VF 8", "Plus")
```

### Fail-open

Tất cả Redis operations được wrap trong try/except. Nếu Redis down → trả empty defaults, không crash. User vẫn nhận được câu trả lời, chỉ mất context multi-turn.

---

## 7. Frontend architecture

### Component tree

```
React App (Vite, Port 5173)
    │
    ├─ / → LandingPage
    │     └─ ChatWidget (floating button → expand panel)
    │           ├─ ChatPanel (message list, auto-scroll)
    │           │     └─ MessageBubble (markdown render, code highlight)
    │           ├─ InputBar (send/stop button, Enter to send)
    │           ├─ SuggestionChips (quick action buttons)
    │           └─ SourceChips (citation links)
    │
    └─ /admin → AdminDashboard
          ├─ KPI cards (total requests, tokens, cost, latency)
          ├─ Timeseries charts (Recharts LineChart)
          ├─ Intent distribution (PieChart)
          └─ Logs table (paginated, filterable)
```

### State management

```typescript
// Zustand store với persist (localStorage)
interface ChatStore {
  sessionId: string;        // UUID, persisted
  messages: Message[];      // Persisted
  isStreaming: boolean;
  sendMessage(text: string): void;  // SSE streaming
  stopGeneration(): void;           // AbortController
  clearChat(): void;                // Reset session
}
```

### API communication

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat/stream` | POST (SSE) | Streaming chat — token-by-token |
| `/api/chat` | POST | Non-stream fallback |
| `/api/health` | GET | Health check |
| `/api/admin/metrics/*` | GET | Dashboard data |

### Streaming flow

```
Frontend                          Backend
    │                                 │
    ├─ POST /api/chat/stream ────────→│
    │  {message, session_id}          ├─ classify_node
    │                                 ├─ call_tools_node
    │                                 ├─ generate_node (LLM)
    │  ←── SSE: token "Xe" ──────────┤   stream token
    │  ←── SSE: token " VinFast" ────┤   stream token
    │  ←── SSE: token " VF 8" ───────┤   stream token
    │  ←── SSE: [DONE] ──────────────┤
    │  ←── SSE: {sources, decision} ─┤   metadata
    │                                 │
```

---

## 8. Data pipeline

### Pipeline flow

```
data/raw/*.txt (crawl từ vinfastauto.com)
    │
    ▼
Step 1: clean_to_jsonl
    → data/intermediate/*.jsonl (cleaned text chunks)
    │
    ▼
Step 2: split_cold_hot
    → data/vector/*.jsonl (for Qdrant)
    → data/postgres/*.csv (for PostgreSQL)
    → _manifest.json (metadata)
    │
    ▼
Step 3: parse_specs
    → data/postgres/specs.csv (structured specs via Crawl4AI/vision)
    │
    ▼
Step 4: vector_ingest
    → Qdrant dense collections (incremental embed + content-hash cache)
    │
    ▼
Step 5: sparse_ingest
    → Qdrant sparse collection (BM25 TF-IDF)
    → data/clean/{version}/sparse_index.json
    │
    ▼
Step 6: postgres_ingest
    → PostgreSQL (versioned UPSERT)
```

### Version management

```bash
python scripts/version_manager.py list      # Liệt kê versions
python scripts/version_manager.py status    # Version hiện tại
python scripts/version_manager.py promote   # Atomic promote (swap aliases + flip is_current)
python scripts/version_manager.py rollback  # Rollback về version trước
```

**Atomic promote:** Swap Qdrant aliases + flip PG `is_current` trong 1 transaction. Không downtime.

### Crawl sources

| Source | Tool | Output |
|--------|------|--------|
| HTML pages | requests + BeautifulSoup | Markdown chunks |
| PDF brochures | PyMuPDF (primary) / pdfplumber | Text chunks |
| SPA/JS pages | Firecrawl API | Rendered HTML → chunks |

---

## 9. Safety & guardrails

### 3 lớp bảo vệ

```
┌─────────────────────────────────────────────────────────────┐
│  LỚP 1: Deterministic gates (classify_node, regex-based)    │
│  • Safety: pin cháy, rò điện, quá nhiệt → refuse + hotline  │
│  • Privacy: OTP, CCCD, tài khoản → refuse                   │
│  • Handoff: yêu cầu gặp nhân viên → refuse + hotline       │
│  • Out-of-scope: query không liên quan VinFast → refuse     │
│  → KHÔNG qua LLM, đảm bảo 100% chính xác cho safety        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  LỚP 2: Prompt constraints (generate_node)                  │
│  • "CHỈ dùng thông tin trong context"                       │
│  • "KHÔNG tự bịa số liệu, KHÔNG dùng kiến thức sẵn có"     │
│  • "Dẫn nguồn (URL) khi có"                                 │
│  → LLM bị ràng buộc bởi prompt                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  LỚP 3: Grounding validation (validate_node)                │
│  • _check_grounding(): verify số liệu trong response khớp   │
│    với tool results (e.g., "130 kW" phải có trong specs)    │
│  • assess_evidence(): score relevance → "insufficient" →    │
│    refuse                                                    │
│  • validate_citations(): filter invalid source URLs          │
│ → Post-LLM check, chặn hallucination lọt qua prompt         │
└─────────────────────────────────────────────────────────────┘
```

### Hotline response

Khi detect safety/privacy/handoff, hệ thống trả response cứng (không qua LLM):

```
"Để đảm bảo an toàn tuyệt đối, bạn vui lòng DỪNG ngay việc sử dụng xe/sạc
và KHÔNG tự xử lý các sự cố về pin/điện. Vui lòng liên hệ:
- Hotline VinFast (24/7): 1900 23 23 89
- Hoặc đặt lịch cứu hộ/dịch vụ qua app VinFast"
```

---

## 10. Monitoring & metrics

### Telemetry (bảng `request_metrics`)

Mỗi request được ghi 27+ columns:

| Field | Mô tả |
|-------|-------|
| `request_id` | UUID unique |
| `session_id` | User session |
| `query_text` | Câu hỏi gốc |
| `intent` | Intent được phân loại |
| `decision` | answer / clarify / refuse / OOS |
| `model_used` | LLM model (gpt-4o-mini, ...) |
| `prompt_tokens` / `completion_tokens` | Token usage |
| `cost_usd` / `cost_vnd` | Chi phí tính theo model pricing |
| `ttft_ms` | Time to first token |
| `ttot_ms` | Time to total output |
| `total_latency_ms` | End-to-end latency |
| `cache_hit` / `cache_type` | Cache hit rate |
| `tools_used` | Danh sách tools đã gọi |
| `user_feedback` | 👍 / 👎 |

### Admin API

| Endpoint | Mô tả |
|----------|-------|
| `GET /api/admin/metrics/overview` | KPI: total requests, tokens, cost, latency P50/P95/P99, cache hit rate |
| `GET /api/admin/metrics/timeseries` | Biểu đồ theo giờ: requests, latency, tokens, cost |
| `GET /api/admin/metrics/intents` | Phân bố intent (PieChart data) |
| `GET /api/admin/metrics/logs` | Chi tiết từng request (paginated, filterable) |
| `POST /api/admin/metrics/feedback` | Ghi nhận 👍/👎 per request |
| `GET /api/admin/metrics/realtime` | Per-minute metrics (1-60 min window) |

### Health checks

| Endpoint | Kiểm tra | Response |
|----------|----------|----------|
| `GET /healthz` | Liveness (FastAPI event loop alive) | 200, <1ms |
| `GET /ready` | Deep readiness: PG + Qdrant + Redis + LLM config | 200/503 |
| `GET /api/health` | Legacy compatibility | 200/503 |

### Prompt registry

- **Table:** `prompt_registry` — versioned prompts (system, synthesize, classify, summarize)
- **In-memory cache:** 5-minute TTL per prompt type
- **Atomic switch:** Transaction-based deactivate/activate
- **Admin API:** Full CRUD + test-render + activate

---

## 11. Infrastructure & deployment

### Docker

```dockerfile
# Multi-stage build
Stage 1 (builder): Python 3.11-slim + build-essential + pip install
Stage 2 (runner):  Python 3.11-slim + curl + copy venv + non-root user
```

- **Non-root:** `appuser:appgroup` (UID/GID 10001)
- **Health check:** `curl -f http://localhost:8000/healthz` mỗi 30s
- **Resource limits:** 2 CPU, 2GB RAM

### Docker Compose

| File | Môi trường | Services |
|------|-----------|----------|
| `docker-compose.yml` | Local dev | API + PostgreSQL 16 + Redis 7 + Qdrant |
| `docker-compose.local.yml` | Local fallback | Non-standard ports (16333, 15432) |
| `docker-compose.prod.yml` | Production | API only (cloud-managed DBs) |

### Production deployment (AWS Lightsail)

```
┌─────────────────────────────────────────────────────────────┐
│  AWS Lightsail (Ubuntu 22.04)                                │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐ │
│  │   Nginx      │───→│  Docker      │───→│  Cloud Services │ │
│  │   :80/:443   │    │  vivu_api    │    │  • Neon PG      │ │
│  │   SSL cert   │    │  :8000       │    │  • Qdrant Cloud │ │
│  │              │    │              │    │  • Upstash Redis│ │
│  │  / → frontend│    │  FastAPI +   │    │  • OpenAI API   │ │
│  │  /api → :8000│    │  LangGraph   │    │  • Cohere       │ │
│  └─────────────┘    └──────────────┘    └─────────────────┘ │
│                                                              │
│  Frontend: /home/ubuntu/vivu/frontend/dist (Vite build)      │
│  Backend:  Docker container (vivu_api)                        │
└─────────────────────────────────────────────────────────────┘
```

### Nginx config

```nginx
server {
    listen 80;
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/vivu.crt;
    ssl_certificate_key /etc/nginx/ssl/vivu.key;

    # Frontend (React SPA)
    root /home/ubuntu/vivu/frontend/dist;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API (FastAPI container)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;          # SSE streaming
        proxy_read_timeout 300s;      # Long-running queries
    }
}
```

---

## 12. Q&A thường gặp

### Q: Tại sao không dùng LLM cho classification?

**A:** Regex-based classify chạy **<1ms**, tiết kiệm 1 LLM call/request (~$0.001 + 200ms). Với ~1000 requests/ngày, tiết kiệm ~$1/ngày + 200s tổng latency. Hơn nữa, deterministic routing đảm bảo **100% chính xác** cho các trường hợp safety/privacy — không thể dùng LLM cho critical safety responses.

### Q: Nếu Redis/PG/Qdrant down thì sao?

**A:** Hệ thống **fail-open**:
- Redis down → cache miss (query trực tiếp PG), mất multi-turn context
- PG down → trả "Mình chưa thể xác nhận thông tin này từ nguồn đã được phê duyệt hiện có"
- Qdrant down → không có KB results nhưng specs/price/color vẫn hoạt động bình thường
- Không có single point of failure nào chặn hoàn toàn việc chat

### Q: Làm sao chống hallucination?

**A:** 3 lớp bảo vệ:
1. **Prompt layer:** "CHỈ dùng thông tin trong context. KHÔNG tự bịa số liệu."
2. **Evidence scoring:** `assess_evidence()` score specs relevance → "insufficient" → refuse
3. **Grounding check:** `_check_grounding()` verify số liệu trong response khớp tool results (e.g., "130 kW" phải tồn tại trong specs data)

### Q: Streaming hoạt động thế nào?

**A:**
1. Frontend gọi `POST /api/chat/stream` với `Accept: text/event-stream`
2. Backend dùng LangGraph `get_stream_writer()` stream token-by-token qua SSE
3. Nếu lỗi **trước** token đầu → fallback sang model khác
4. Nếu lỗi **sau** khi đã stream → giữ nguyên (tránh duplicate tokens)
5. Frontend dùng `fetch` + `ReadableStream` đọc SSE, render token real-time

### Q: Cache invalidation khi data thay đổi?

**A:**
- Cache key chứa `data_version` từ PG `ingest_version.is_current`
- Khi promote version mới → key mới tự动生成, key cũ hết TTL tự xóa
- TTL theo mức độ thay đổi: price=15min, specs=24h, embeddings=7 ngày
- Có thể gọi `invalidate_all()` để xóa ngay lập tức (nuclear option)

### Q: Multi-turn context hoạt động thế nào?

**A:**
- Frontend gửi `session_id` + 7 turn gần nhất (14 messages)
- Backend lưu vào Redis: `session:{id}:history` (LIST, max 20 messages) + `session:{id}:context` (HASH: model_code, version, last_topic)
- Khi query mới không có model → inherit từ history context
- Session TTL: 6 giờ, tự động cleanup

### Q: Hệ thống hỗ trợ những xe nào?

**A:** Hiện tại: VF 2, VF 3, VF 5, VF 6, VF 7, VF 8, VF 8 All New, VF 9, VF MPV 7, Herio Green, Minio Green. Danh sách được load động từ PG `edition_active` view.

### Q: Chi phí vận hành ước tính?

**A:**
- LLM: ~$0.001/request (GPT-4o-mini) × 1000 req/ngày = ~$1/ngày
- Embedding: cached 7 ngày, ~$0.0001/request
- Cohere rerank: ~$0.001/request (optional)
- Infrastructure: Lightsail $10/tháng + Neon free tier + Upstash free tier + Qdrant free tier
- **Tổng: ~$40-50/tháng** cho 1000 requests/ngày

### Q: Làm sao deploy update mà không downtime?

**A:**
1. `git pull` trên VPS
2. `docker compose up -d --build` — Docker recreate container (downtime ~2-3s)
3. Nginx vẫn serve frontend static files trong lúc rebuild
4. Data pipeline: atomic promote qua Qdrant aliases + PG `is_current` flag — không downtime

---

## File structure

```
vivu/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── api/
│   │   ├── chat.py                # POST /api/chat, /api/chat/stream
│   │   ├── health.py              # /healthz, /ready
│   │   ├── metrics.py             # Admin metrics API
│   │   └── admin_prompts.py       # Prompt registry CRUD
│   ├── agent/
│   │   ├── graph.py               # LangGraph definition
│   │   ├── agent_loop.py          # run() + run_stream()
│   │   ├── classifier.py          # Model/version extraction
│   │   ├── tools.py               # 13 tool functions
│   │   ├── llm.py                 # OpenAI client + fallback
│   │   ├── prompts.py             # System/synthesize prompts
│   │   ├── context_builder.py     # Format tool results → text
│   │   ├── decision.py            # Evidence assessment + logging
│   │   └── nodes/
│   │       ├── classify.py        # Deterministic intent routing
│   │       ├── call_tools.py      # Deterministic tool dispatch
│   │       ├── generate.py        # LLM synthesis
│   │       ├── validate.py        # Grounding check
│   │       └── respond.py         # Response assembly
│   └── core/
│       ├── db.py                  # PostgreSQL pool (asyncpg)
│       ├── cache.py               # 6-tier Redis cache
│       ├── memory.py              # Session store (Redis)
│       ├── retrieval.py           # Qdrant hybrid search
│       ├── rate_limit.py          # Token-bucket rate limiter
│       ├── telemetry.py           # Request metrics recording
│       └── prompt_manager.py      # Prompt versioning
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # Router: / + /admin
│   │   ├── components/chat/       # ChatWidget, ChatPanel, MessageBubble
│   │   ├── pages/admin/           # AdminDashboard
│   │   ├── store/chatStore.ts     # Zustand state
│   │   └── api/chat.ts            # SSE streaming client
│   └── vite.config.ts             # Vite + proxy config
├── scripts/
│   ├── run_pipeline.py            # Data pipeline orchestrator
│   ├── crawl.py                   # HTML/PDF/SPA crawler
│   ├── version_manager.py         # Atomic promote/rollback
│   └── ingest/
│       ├── vector_ingest.py       # Qdrant dense ingest
│       ├── sparse_ingest.py       # Qdrant sparse ingest
│       └── postgres_ingest.py     # PostgreSQL ingest
├── tests/                         # Test suite (15 files)
├── Dockerfile                     # Multi-stage production build
├── docker-compose.prod.yml        # Production compose
└── ARCHITECTURE.md                # ← Tài liệu này
```
