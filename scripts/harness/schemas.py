#!/usr/bin/env python3
"""
schemas.py — Canonical Document & Data Models for Agentic Ingestion Harness.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    width: Optional[float] = None
    height: Optional[float] = None
    coordinate_system: str = "pdf_points"
    origin: str = "top-left"
    page_size: Optional[Dict[str, float]] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.width is None:
            self.width = round(abs(self.x2 - self.x1), 2)
        if self.height is None:
            self.height = round(abs(self.y2 - self.y1), 2)

    def to_list(self) -> List[float]:
        return [round(self.x1, 1), round(self.y1, 1), round(self.x2, 1), round(self.y2, 1)]


class Evidence(BaseModel):
    document_id: str
    page: int
    bbox: Optional[BBox] = None
    source_block: Optional[str] = None
    crop_path: Optional[str] = None
    deep_link: Optional[str] = None


class Provenance(BaseModel):
    method: Literal["pymupdf_text", "vision_table", "vision_prose", "ocr", "docling", "manual", "web_crawl", "configurator"]
    model: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ValidationResult(BaseModel):
    structural: bool = True
    visual: bool = True
    semantic: bool = True
    schema_valid: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)


class SpecItem(BaseModel):
    category: str                               # Standard English slug or raw category
    category_vn: Optional[str] = None           # Vietnamese label: Kích thước & trọng lượng, Pin & sạc, etc.
    attribute: str                              # Raw attribute string from table
    spec_key: Optional[str] = None              # Standard snake_case key: length_mm, power_kw, etc.
    spec_key_vn: Optional[str] = None          # Vietnamese label: Chiều dài tổng thể, Công suất tối đa, etc.
    value: Any                                  # Normalized value: "3190", "150", "LED", "Có"
    unit: Optional[str] = None                  # "mm", "kW", "kWh", "km", "triệu", or None
    edition: Optional[str] = None               # "Eco", "Plus", "TieuChuan", or None for all
    evidence: Optional[Evidence] = None
    validation: Optional[ValidationResult] = None
    provenance: Optional[Provenance] = None


class TableRow(BaseModel):
    category: Optional[str] = None
    attribute: str
    values_by_edition: Dict[str, Any] = Field(default_factory=dict)
    unit: Optional[str] = None
    raw_cells: Optional[List[str]] = None
    evidence: Optional[Evidence] = None


class CanonicalBlock(BaseModel):
    block_id: str
    type: Literal["heading", "paragraph", "table", "footnote", "hero_card", "list", "image_caption"]
    text: Optional[str] = None
    section: Optional[str] = None
    items: Optional[List[SpecItem]] = None
    rows: Optional[List[TableRow]] = None
    evidence: Optional[Evidence] = None
    extraction: Optional[Provenance] = None


class PageSignals(BaseModel):
    page_number: int
    text_blocks_count: int = 0
    words_count: int = 0
    images_count: int = 0
    drawings_count: int = 0
    overlap_ratio: float = 0.0
    text_layer_quality: float = 1.0
    is_scanned: bool = False
    has_table_structure: bool = False
    page_type: Literal["cover", "prose", "spec_table", "comparison_table", "pricing", "mixed"] = "prose"
    recommended_strategy: Literal["pymupdf", "vision_table", "vision_prose", "ocr"] = "pymupdf"


class CanonicalPage(BaseModel):
    page_number: int
    page_size: Dict[str, float]
    image_path: Optional[str] = None
    signals: Optional[PageSignals] = None
    blocks: List[CanonicalBlock] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    id: str
    source_file: str
    source_url: Optional[str] = None
    model_code: str = "VF 6"
    language: str = "vi"
    total_pages: int
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CanonicalDocument(BaseModel):
    document: DocumentMetadata
    pages: List[CanonicalPage] = Field(default_factory=list)

    def get_all_blocks(self) -> List[CanonicalBlock]:
        blocks = []
        for p in self.pages:
            blocks.extend(p.blocks)
        return blocks

    def get_all_spec_items(self) -> List[SpecItem]:
        items = []
        for p in self.pages:
            for b in p.blocks:
                if b.items:
                    items.extend(b.items)
        return items


class RetrievalChunk(BaseModel):
    id: str
    text: str
    collection: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
