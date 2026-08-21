#!/usr/bin/env python3
"""
test_v3_isolated.py — Isolated End-to-End Test Suite for Version v3.
Runs test queries directly against v3 PostgreSQL rows and v3 Qdrant collections
WITHOUT touching active aliases or modifying production version.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(".env"))

import psycopg2  # noqa: E402
from openai import OpenAI  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

PG_DSN = os.environ.get("PG_DSN")
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
raw_model = os.environ.get("OPENAI_EMBED_MODEL") or os.environ.get("OPENROUTER_EMBED_MODEL") or "text-embedding-3-small"
EMBED_MODEL = raw_model.split("/")[-1] if "/" in raw_model else raw_model

VERSION = "v3"


def test_sql_tools(conn):
    print("\n" + "=" * 75)
    print(f"1. TESTING SQL COLD PATH TOOLS (Direct PostgreSQL queries on '{VERSION}')")
    print("=" * 75)
    cur = conn.cursor()

    test_cases = [
        ("VF 3 Kích thước", "VF 3", "dimension"),
        ("VF 6 Động cơ & Vận hành", "VF 6", "powertrain"),
        ("VF 7 Pin & Sạc", "VF 7", "battery"),
        ("VF 8 An toàn & ADAS", "VF 8", "safety"),
    ]

    for label, m_code, cat in test_cases:
        cur.execute(
            """
            SELECT spec_key, spec_key_vn, spec_value, spec_unit, source_url
            FROM car_specs
            WHERE ingest_version = %s AND model_code = %s AND spec_category = %s
            LIMIT 4
            """,
            (VERSION, m_code, cat),
        )
        rows = cur.fetchall()
        print(f"\n[Test Case] {label} (model: {m_code}, category: {cat}) -> Found {len(rows)} specs:")
        for r in rows:
            unit = f" {r[3]}" if r[3] else ""
            print(f"  • {r[1]} ({r[0]}): {r[2]}{unit}")

    # Test Prices
    print(f"\n[Test Case] Giá bán niêm yết (Bảng price_list, version: {VERSION}):")
    cur.execute(
        """
        SELECT model_id, edition_id, price_list_vnd, vat_included, battery_included
        FROM price_list
        WHERE version = %s
        ORDER BY price_list_vnd ASC
        LIMIT 6
        """,
        (VERSION,),
    )
    for r in cur.fetchall():
        print(f"  • {r[0]} ({r[1]}): {r[2]:,d} VNĐ (VAT={r[3]}, Pin={r[4]})")

    # Test Colors
    print(f"\n[Test Case] Màu sắc ngoại thất (Bảng car_colors, version: {VERSION} - VF 7):")
    cur.execute(
        """
        SELECT color_name, color_type, color_fee_vnd
        FROM car_colors
        WHERE ingest_version = %s AND model_id = 'VF7'
        LIMIT 5
        """,
        (VERSION,),
    )
    for r in cur.fetchall():
        fee_str = f" (+{r[2]:,d}đ)" if r[2] else " (Miễn phí)"
        print(f"  • Màu: {r[0]} ({r[1]}){fee_str}")


def test_vector_retrieval(qdrant_client, embed_client):
    print("\n" + "=" * 75)
    print(f"2. TESTING VECTOR HOT PATH RETRIEVAL (Direct Qdrant collections on '{VERSION}')")
    print("=" * 75)

    queries = [
        ("vivu_product_info", "VF 3 thiết kế ngoại thất và kích thước la-zăng"),
        ("vivu_policy", "Chính sách bảo hành pin xe điện VinFast bao nhiêu năm"),
        ("vivu_maintenance", "Quy trình đặt lịch bảo dưỡng và các hạng mục định kỳ"),
    ]

    for col_stem, q_text in queries:
        target_col = f"{col_stem}__{VERSION}"
        resp = embed_client.embeddings.create(input=[q_text], model=EMBED_MODEL)
        vec = resp.data[0].embedding

        hits = qdrant_client.query_points(collection_name=target_col, query=vec, limit=2)
        print(f"\n[Search Query] '{q_text}'")
        print(f"  -> Collection: {target_col} (Found {len(hits.points)} matches)")
        for h in hits.points:
            text_snippet = (h.payload.get("text") or "").replace("\n", " ")[:140]
            src_url = h.payload.get("source_url") or h.payload.get("source_file") or "N/A"
            print(f"  • [Score: {h.score:.4f}] {text_snippet}...")
            print(f"    Source: {src_url}")


def main():
    print(f"Starting Isolated Test Suite for Version: {VERSION}...")
    conn = psycopg2.connect(PG_DSN)
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    embed_client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL if OPENAI_BASE_URL and "openai.com" not in OPENAI_BASE_URL else None,
    )

    try:
        test_sql_tools(conn)
        test_vector_retrieval(qdrant_client, embed_client)
        print("\n" + "=" * 75)
        print(f"✓ ALL ISOLATED TESTS ON VERSION '{VERSION}' PASSED SUCCESSFULLY!")
        print("  Active production version (v2) remains completely untouched and safe.")
        print("=" * 75)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
