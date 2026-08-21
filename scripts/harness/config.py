import os, sys
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / '.env')

DATA_V2_DIR = REPO_ROOT / 'data_v2'
RAW_DIR = DATA_V2_DIR / 'raw'
RAW_PDF_DIR = RAW_DIR / 'pdf'
RAW_POLICIES_DIR = RAW_DIR / 'web_policies'
RAW_DEPOSIT_DIR = RAW_DIR / 'web_deposit'
CONFIGURATOR_DIR = RAW_DIR / 'configurator'

ARTIFACTS_DIR = DATA_V2_DIR / 'artifacts'
CANONICAL_DIR = DATA_V2_DIR / 'canonical'
STRUCTURED_DIR = DATA_V2_DIR / 'structured'
RETRIEVAL_DIR = DATA_V2_DIR / 'retrieval'

PG_DSN = os.environ.get('PG_DSN', 'postgresql://vivu:vivu@localhost:15432/vivu')
QDRANT_URL = os.environ.get('QDRANT_URL', 'http://localhost:16333')
QDRANT_API_KEY = os.environ.get('QDRANT_API_KEY', '')
QDRANT_TIMEOUT = int(os.environ.get('QDRANT_TIMEOUT', '300'))

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '') or os.environ.get('OPENROUTER_API_KEY', '')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')

raw_model = os.environ.get('OPENAI_EMBED_MODEL') or os.environ.get('OPENROUTER_EMBED_MODEL') or 'text-embedding-3-small'
EMBEDDING_MODEL = raw_model.split('/')[-1] if '/' in raw_model else raw_model
EMBEDDING_DIM = 1536

CONSUMER_MODELS = ['VF 2', 'VF 3', 'VF 5', 'VF 6', 'VF 7', 'VF 8', 'VF 8 All New', 'VF 9', 'VF MPV 7']

BROCHURE_CATALOG = [
    {'model_code': 'VF 2', 'doc_id': 'vf2_brochure', 'pdf_name': 'vf2_brochure.pdf', 'url': 'https://static-cms-prod.vinfastauto.com/brochure_vf_2.pdf'},
    {'model_code': 'VF 3', 'doc_id': 'vf3_brochure', 'pdf_name': 'vf3_brochure.pdf', 'url': 'https://storage.googleapis.com/vinfast-data-01/brochure/29012026/VFVN_VF%203_Brochure%20280126.pdf'},
    {'model_code': 'VF 5', 'doc_id': 'vf5_brochure', 'pdf_name': 'vf5_brochure.pdf', 'url': 'https://storage.googleapis.com/vinfast-data-01/brochure/09042026/VFVN_VF%205_Brochure%20B%E1%BA%A3n%20s%E1%BB%ADa%20290126_1333PM.pdf'},
    {'model_code': 'VF 6', 'doc_id': 'vf6_brochure', 'pdf_name': 'vf6_brochure.pdf', 'url': 'https://storage.googleapis.com/vinfast-data-01/brochure/14052026/VF%206_Brochure_Final_130526%20(12AM)_compressed.pdf'},
    {'model_code': 'VF 7', 'doc_id': 'vf7_brochure', 'pdf_name': 'vf7_brochure.pdf', 'url': 'https://vinfastnamtuliem.vn/wp-content/uploads/2025/02/VF7_Brochure_T062025.pdf'},
    {'model_code': 'VF 8', 'doc_id': 'vf8_brochure', 'pdf_name': 'vf8_brochure.pdf', 'url': 'https://storage.googleapis.com/vinfast-data-01/brochure/VF8_Brochure_03022026.pdf'},
    {'model_code': 'VF 8 All New', 'doc_id': 'vf8_all_new_brochure', 'pdf_name': 'vf8_all_new_brochure.pdf', 'url': 'https://static-cms-prod.vinfastauto.com/brochure/26052026/VF%208%20The%20he%20moi_Brochure_final%2020.05.pdf'},
    {'model_code': 'VF 9', 'doc_id': 'vf9_brochure', 'pdf_name': 'vf9_brochure.pdf', 'url': 'https://storage.googleapis.com/vinfast-data-01/brochure/VF%209_%20Brochure.pdf'},
    {'model_code': 'VF MPV 7', 'doc_id': 'vf_mpv7_brochure', 'pdf_name': 'vf_mpv7_brochure.pdf', 'url': 'https://storage.googleapis.com/vinfast-data-01/brochure/VF_MPV%207_Brochure_2026.02.03.pdf'}
]
