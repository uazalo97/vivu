#!/usr/bin/env python3
"""
semantic.py — Semantic Chunker for Canonical Documents.

Splits prose into section-aware chunks (heading + paragraphs) and
synthesizes natural-language retrieval representations for tables.
"""

from typing import Any, Dict, List
from scripts.harness.schemas import CanonicalBlock, CanonicalDocument, CanonicalPage


class SemanticChunker:
    def __init__(self, max_chunk_chars: int = 800):
        self.max_chunk_chars = max_chunk_chars

    def _chunk_table(self, block: CanonicalBlock, page: CanonicalPage, doc: CanonicalDocument) -> Dict[str, Any]:
        """Synthesize natural-language retrieval text for a technical specification table."""
        doc_id = doc.document.id
        model_name = doc.document.model_code
        page_num = page.page_number
        section = block.section or "Thông số kỹ thuật"

        items = block.items or []
        if not items:
            return {}

        # Group by edition (e.g., Eco, Plus, or None)
        by_edition: Dict[str, List[str]] = {}
        for item in items:
            ed_label = item.edition or "Chung"
            unit_str = f" {item.unit}" if item.unit else ""
            by_edition.setdefault(ed_label, []).append(f"{item.attribute}: {item.value}{unit_str}")

        lines = [f"{section} - {model_name}."]
        for ed, specs in by_edition.items():
            ed_prefix = f"Phiên bản {ed}: " if ed != "Chung" else ""
            lines.append(f"{ed_prefix}{'; '.join(specs)}.")

        synthesized_text = " ".join(lines)
        chunk_id = f"{doc_id}_p{page_num:02d}_{block.block_id}_c01"

        return {
            "id": chunk_id,
            "text": synthesized_text,
            "metadata": {
                "document_id": doc_id,
                "model_code": model_name,
                "page": page_num,
                "content_type": "table",
                "source_block": block.block_id,
                "postgres_table": "car_specs",
                "deep_link": block.evidence.deep_link if block.evidence else None,
            },
        }

    def chunk_document(self, doc: CanonicalDocument) -> List[Dict[str, Any]]:
        """Chunk an entire canonical document into retrieval chunks."""
        chunks: List[Dict[str, Any]] = []
        doc_id = doc.document.id

        for page in doc.pages:
            page_num = page.page_number
            current_section = f"{doc.document.model_code} Brochure"
            prose_buffer: List[str] = []
            source_blocks_buffer: List[str] = []

            for block in page.blocks:
                if block.type == "heading":
                    # Flush previous prose buffer
                    if prose_buffer:
                        text = " ".join(prose_buffer).strip()
                        if text:
                            chunks.append(
                                {
                                    "id": f"{doc_id}_p{page_num:02d}_c{len(chunks)+1:02d}",
                                    "text": text,
                                    "metadata": {
                                        "document_id": doc_id,
                                        "model_code": doc.document.model_code,
                                        "page": page_num,
                                        "content_type": "prose",
                                        "source_blocks": list(source_blocks_buffer),
                                        "deep_link": block.evidence.deep_link if block.evidence else None,
                                    },
                                }
                            )
                        prose_buffer = []
                        source_blocks_buffer = []

                    current_section = block.text or current_section
                    prose_buffer.append(f"{current_section}:")
                    source_blocks_buffer.append(block.block_id)

                elif block.type in ("paragraph", "list", "footnote"):
                    if block.text:
                        prose_buffer.append(block.text)
                        source_blocks_buffer.append(block.block_id)

                        # Flush if buffer exceeds max length
                        if sum(len(p) for p in prose_buffer) > self.max_chunk_chars:
                            text = " ".join(prose_buffer).strip()
                            chunks.append(
                                {
                                    "id": f"{doc_id}_p{page_num:02d}_c{len(chunks)+1:02d}",
                                    "text": text,
                                    "metadata": {
                                        "document_id": doc_id,
                                        "model_code": doc.document.model_code,
                                        "page": page_num,
                                        "content_type": "prose",
                                        "source_blocks": list(source_blocks_buffer),
                                        "deep_link": block.evidence.deep_link if block.evidence else None,
                                    },
                                }
                            )
                            prose_buffer = [f"{current_section}:"]
                            source_blocks_buffer = []

                elif block.type == "table":
                    # Chunk the table with specialized synthesis
                    t_chunk = self._chunk_table(block, page, doc)
                    if t_chunk:
                        chunks.append(t_chunk)

            # Flush remaining prose at end of page
            if prose_buffer and len(prose_buffer) > 1:
                text = " ".join(prose_buffer).strip()
                if text:
                    chunks.append(
                        {
                            "id": f"{doc_id}_p{page_num:02d}_c{len(chunks)+1:02d}",
                            "text": text,
                            "metadata": {
                                "document_id": doc_id,
                                "model_code": doc.document.model_code,
                                "page": page_num,
                                "content_type": "prose",
                                "source_blocks": list(source_blocks_buffer),
                                "deep_link": f"{doc.document.source_url}#page={page_num}" if doc.document.source_url else None,
                            },
                        }
                    )

        return chunks
