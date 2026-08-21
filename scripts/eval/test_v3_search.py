import os, sys
from pathlib import Path
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(Path('.env'))
from qdrant_client import QdrantClient
from openai import OpenAI

client = QdrantClient(url=os.environ.get('QDRANT_URL'), api_key=os.environ.get('QDRANT_API_KEY'))
embed_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

print("=== 1. QDRANT COLLECTIONS OVERVIEW ===")
for col in sorted([c.name for c in client.get_collections().collections]):
    if 'v3' in col or 'v2' in col:
        info = client.get_collection(col)
        print(f"  {col:<30}: {info.points_count} points")

print("\n=== 2. VECTOR SEARCH TEST (VF 3 Dimensions on vivu_product_info__v3) ===")
q_vec = embed_client.embeddings.create(input=['VF 3 kích thước chiều dài'], model='text-embedding-3-small').data[0].embedding
hits = client.query_points(collection_name='vivu_product_info__v3', query=q_vec, limit=2)
for h in hits.points:
    print(f"  Score: {h.score:.4f} | Chunk: {h.id}")
    print(f"    Text: {h.payload.get('text', '')[:120]}...")

print("\n=== 3. VECTOR SEARCH TEST (Chính sách bảo hành pin on vivu_policy__v3) ===")
q_vec2 = embed_client.embeddings.create(input=['chính sách bảo hành pin xe điện'], model='text-embedding-3-small').data[0].embedding
hits2 = client.query_points(collection_name='vivu_policy__v3', query=q_vec2, limit=2)
for h in hits2.points:
    print(f"  Score: {h.score:.4f} | Chunk: {h.id}")
    print(f"    Text: {h.payload.get('text', '')[:120]}...")
