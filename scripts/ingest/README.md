# Ingest Scripts — Local Qdrant + PostgreSQL

Thư mục này chứa script ingest dữ liệu clean vào database local.

## Chuẩn bị

### 1. Cài thư viện

```bash
pip install -r requirements.txt
```

Các thư viện chính:

- `qdrant-client`: kết nối Qdrant
- `psycopg2-binary`: kết nối PostgreSQL
- `sentence-transformers`: embed text cho vector search

### 2. Khởi động DB local (Docker)

```bash
docker compose up -d
```

Lệnh này chạy:

- Qdrant: `http://localhost:6333`
- PostgreSQL: `postgresql://vivu:vivu@localhost:5432/vivu`

### 3. Chạy data pipeline trước

```bash
python scripts/clean_data/clean_to_jsonl.py --version v1
python scripts/clean_data/split_cold_hot.py --version v1 --commit $(git rev-parse --short HEAD)
```

## Ingest

### Vector (Qdrant)

```bash
python scripts/ingest/vector_ingest.py --version v1
```

Tùy chọn:

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Version dữ liệu clean |
| `--url` | `http://localhost:6333` | Qdrant URL |
| `--model` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Model embedding |
| `--recreate` | `false` | Xóa và tạo lại collection |

Mỗi file `data/clean/v1/vector/*.jsonl` sẽ thành một collection Qdrant cùng tên (`vivu_specs`, `vivu_product_info`, ...).

### PostgreSQL

```bash
python scripts/ingest/postgres_ingest.py --version v1
```

Tùy chọn:

| Tham số | Mặc định | Ý nghĩa |
|---------|----------|---------|
| `--version` | `v1` | Version dữ liệu clean |
| `--dsn` | `postgresql://vivu:vivu@localhost:5432/vivu` | Postgres DSN |

Script sẽ:

1. Tạo bảng `edition`, `price_list`, `maintenance_schedule`, `ingest_version` nếu chưa có.
2. Upsert dữ liệu từ CSV.
3. Ghi metadata vào `ingest_version`.

## Kiểm tra sau ingest

### Qdrant

```bash
curl http://localhost:6333/collections
```

Hoặc mở UI: http://localhost:6333/dashboard

### PostgreSQL

```bash
docker exec -it vivu_postgres psql -U vivu -d vivu -c "SELECT * FROM price_list WHERE model_id = 'VF9';"
```

## Ghi chú

- `maintenance_schedule.csv` hiện chỉ có header vì chưa có dữ liệu chi tiết.
- `vector_ingest.py` mặc định dùng model nhẹ 384 chiều. Nếu muốn chất lượng cao hơn, đổi `--model` sang model khác (VD: `BAAI/bge-m3`).
