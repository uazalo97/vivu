#!/usr/bin/env python3
"""
schemas.py — Canonical Document Model for Agentic Document Ingestion Harness.

All extractors (PyMuPDF, Vision, OCR, Docling) normalize into these Pydantic models.
This is the single source of truth contract for downstream consumers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class BBox(BaseModel):
    """Bounding box coordinates with standardized coordinate system and page size."""
    x1: float
    y1: float
    x2: float
    y2: float
    width: Optional[float] = None
    height: Optional[float] = None
    coordinate_system: str = "pdf_points"  # standard 72 DPI PDF point system
    origin: str = "top-left"
    page_size: Optional[Dict[str, float]] = None  # {"width": 842.0, "height": 595.0}

    def __init__(self, **data):
        super().__init__(**data)
        if self.width is None:
            self.width = round(abs(self.x2 - self.x1), 2)
        if self.height is None:
            self.height = round(abs(self.y2 - self.y1), 2)

    def to_list(self) -> List[float]:
        return [round(self.x1, 1), round(self.y1, 1), round(self.x2, 1), round(self.y2, 1)]


class Evidence(BaseModel):
    """Provenance and traceability metadata for an extracted item/block."""
    document_id: str
    page: int
    bbox: Optional[BBox] = None
    source_block: Optional[str] = None
    crop_path: Optional[str] = None
    deep_link: Optional[str] = None  # e.g., "VF6_Brochure_VN.pdf#page=12"


class Provenance(BaseModel):
    """Extraction origin and method."""
    method: Literal["pymupdf_text", "vision_table", "vision_prose", "ocr", "docling", "manual"]
    model: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ValidationResult(BaseModel):
    """Multi-layer validation flags."""
    structural: bool = True
    visual: bool = True
    semantic: bool = True
    schema_valid: bool = True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)


class SpecItem(BaseModel):
    """A single normalized vehicle specification row with evidence."""
    category: str
    attribute: str
    value: Any
    unit: Optional[str] = None
    edition: Optional[str] = None  # e.g., "Eco", "Plus", "PlusCaptain", or None for all
    spec_key: Optional[str] = None  # normalized English key, e.g. "power_kw"
    evidence: Optional[Evidence] = None
    validation: Optional[ValidationResult] = None
    provenance: Optional[Provenance] = None


class TableRow(BaseModel):
    """Raw or structured table row."""
    category: Optional[str] = None
    attribute: str
    values_by_edition: Dict[str, Any] = Field(default_factory=dict)  # {"Eco": "130", "Plus": "150"}
    unit: Optional[str] = None
    raw_cells: Optional[List[str]] = None
    evidence: Optional[Evidence] = None


class CanonicalBlock(BaseModel):
    """A distinct structural block on a page (heading, table, paragraph, footnote, etc.)."""
    block_id: str  # e.g., "p12_b01"
    type: Literal["heading", "paragraph", "table", "footnote", "hero_card", "list", "image_caption"]
    text: Optional[str] = None  # Text representation (for heading/paragraph/footnote)
    section: Optional[str] = None  # Heading/context hierarchy
    items: Optional[List[SpecItem]] = None  # For tables or structured spec blocks
    rows: Optional[List[TableRow]] = None  # For raw/semi-structured tables
    evidence: Optional[Evidence] = None
    extraction: Optional[Provenance] = None


class PageSignals(BaseModel):
    """Inspection signals computed without LLM."""
    page_number: int
    text_blocks_count: int = 0
    words_count: int = 0
    images_count: int = 0
    drawings_count: int = 0  # vector graphics / table borders
    overlap_ratio: float = 0.0
    text_layer_quality: float = 1.0
    is_scanned: bool = False
    has_table_structure: bool = False
    page_type: Literal["cover", "prose", "spec_table", "comparison_table", "pricing", "mixed"] = "prose"
    recommended_strategy: Literal["pymupdf", "vision_table", "vision_prose", "ocr"] = "pymupdf"


class CanonicalPage(BaseModel):
    """A page in the canonical document."""
    page_number: int
    page_size: Dict[str, float]  # {"width": 842.0, "height": 595.0}
    image_path: Optional[str] = None
    signals: Optional[PageSignals] = None
    blocks: List[CanonicalBlock] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    """Document-level metadata."""
    id: str
    source_file: str
    source_url: Optional[str] = None
    model_code: str = "VF 6"
    language: str = "vi"
    total_pages: int
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CanonicalDocument(BaseModel):
    """The master canonical document representation."""
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
