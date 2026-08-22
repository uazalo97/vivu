#!/usr/bin/env python3
"""
postgres.py — Structured PostgreSQL Sink for Unified Ingestion Harness.
Exports normalized specs to data_v2/structured/ and performs versioned UPSERT into PostgreSQL:
- edition (parent)
- price_list (child)
- car_specs
- car_colors
- car_options
- ingest_version (with is_current=false during test)
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import psycopg2
from psycopg2.extras import execute_values

from scripts.harness.config import INGEST_PREV_VERSION, INGEST_VALID_FROM, INGEST_YEAR_RANGE, PG_DSN, STRUCTURED_DIR
from scripts.harness.normalizers.table import TableNormalizer
from scripts.harness.schemas import CanonicalDocument


class PostgresSink:
    def __init__(self, output_dir: Path = STRUCTURED_DIR, dsn: str = PG_DSN):
        self.output_dir = Path(output_dir)
        self.dsn = dsn
        self.normalizer = TableNormalizer()

    def export_preview(self, doc: CanonicalDocument) -> Tuple[Path, Path]:
        """Extract all SpecItems from CanonicalDocument and save structured preview."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        doc_id = doc.document.id
        model_code = doc.document.model_code
        source_url = doc.document.source_url or doc.document.source_file

        rows: List[Dict[str, Any]] = []

        for item in doc.get_all_spec_items():
            ev = item.evidence
            page_num = ev.page if ev else None
            bbox_list = ev.bbox.to_list() if ev and ev.bbox else None
            block_id = ev.source_block if ev else None
            conf = item.validation.confidence if item.validation else 1.0

            # C1 fix: reuse already-normalized fields from orchestrator to avoid redundant
            # map_attribute call (which re-parses Vietnamese aliases and is costly).
            # Only fall back to mapping when normalized fields are missing.
            if item.spec_key and item.category and item.category_vn:
                cat_slug = item.category
                cat_vn = item.category_vn
                s_key = item.spec_key
                s_key_vn = item.spec_key_vn or item.attribute
                unit = item.unit or ""
            else:
                s_key, s_key_vn, unit, cat_slug, cat_vn = self.normalizer.map_attribute(item.attribute, item.category)

            rows.append(
                {
                    "model_code": model_code,
                    "version_name": item.edition,
                    "version_code": None,
                    "spec_category": cat_slug,
                    "spec_category_vn": cat_vn,
                    "spec_key": item.spec_key or s_key,
                    "spec_key_vn": item.spec_key_vn or s_key_vn,
                    "spec_value": str(item.value),
                    "spec_unit": item.unit or unit or "",
                    "source_document": doc_id,
                    "source_url": source_url,
                    "source_page": page_num,
                    "source_bbox": bbox_list,
                    "source_block_id": block_id,
                    "confidence": conf,
                }
            )

        json_path = self.output_dir / f"{doc_id}_specs.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

        csv_path = self.output_dir / f"{doc_id}_specs.csv"
        fieldnames = [
            "model_code",
            "version_name",
            "version_code",
            "spec_category",
            "spec_category_vn",
            "spec_key",
            "spec_key_vn",
            "spec_value",
            "spec_unit",
            "source_document",
            "source_url",
            "source_page",
            "source_bbox",
            "source_block_id",
            "confidence",
        ]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="|")
            writer.writeheader()
            for r in rows:
                writer.writerow(
                    {
                        k: (
                            json.dumps(r.get(k))
                            if isinstance(r.get(k), list)
                            else ("" if r.get(k) is None else r.get(k))
                        )
                        for k in fieldnames
                    }
                )

        return json_path, csv_path

    def consolidate_all_specs(self) -> Tuple[Path, Path]:
        """Consolidate all individual brochure specs into master files."""
        all_rows: List[Dict[str, Any]] = []

        candidate_files = list(self.output_dir.glob("*_specs.json")) + list(
            (self.output_dir / "specs").glob("*_specs.json")
        )

        VALID_CATEGORIES = [
            "dimension",
            "powertrain",
            "battery",
            "chassis",
            "exterior",
            "interior",
            "infotainment",
            "convenience",
            "safety",
            "security",
            "adas",
            "connected",
        ]
        seen_files = set()
        for f in candidate_files:
            if f.name != "all_models_specs.json" and f.resolve() not in seen_files:
                seen_files.add(f.resolve())
                with open(f, "r", encoding="utf-8") as fp:
                    items = json.load(fp)
                    for it in items:
                        cat = it.get("spec_category")
                        # C1 fix: only call map_attribute when category is invalid/missing.
                        # Previously called for every row (even valid) and fed English spec_key
                        # into Vietnamese matcher, causing fallback mis-categorization.
                        if cat not in VALID_CATEGORIES:
                            attr_for_map = it.get("spec_key_vn") or it.get("spec_key") or ""
                            _, mapped_s_key_vn, _, cat_slug, mapped_cat_vn = self.normalizer.map_attribute(
                                attr_for_map, cat
                            )
                            it["spec_category"] = cat_slug
                            if not it.get("spec_category_vn"):
                                it["spec_category_vn"] = mapped_cat_vn
                            if not it.get("spec_key_vn") and mapped_s_key_vn:
                                it["spec_key_vn"] = mapped_s_key_vn
                        else:
                            # Category valid but missing VN label -> fill from CATEGORY map without full remap
                            if not it.get("spec_category_vn"):
                                from scripts.harness.normalizers.table import CATEGORY_VN_MAP

                                it["spec_category_vn"] = CATEGORY_VN_MAP.get(cat, cat.title())
                        all_rows.append(it)

        master_json = self.output_dir / "all_models_specs.json"
        with open(master_json, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, ensure_ascii=False, indent=2)

        master_csv = self.output_dir / "all_models_specs.csv"
        fieldnames = [
            "model_code",
            "version_name",
            "version_code",
            "spec_category",
            "spec_category_vn",
            "spec_key",
            "spec_key_vn",
            "spec_value",
            "spec_unit",
            "source_document",
            "source_url",
            "source_page",
            "source_bbox",
            "source_block_id",
            "confidence",
        ]
        with open(master_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="|")
            writer.writeheader()
            for r in all_rows:
                writer.writerow(
                    {
                        k: (
                            json.dumps(r.get(k))
                            if isinstance(r.get(k), list)
                            else ("" if r.get(k) is None else r.get(k))
                        )
                        for k in fieldnames
                    }
                )

        return master_json, master_csv

    def ingest_to_postgres(self, version: str = "v3") -> Dict[str, int]:
        """
        Active PostgreSQL Ingestion: UPSERT all structured datasets for the given version.
        Deletes in child-first order (price_list -> edition) to respect foreign keys.
        Inserts in parent-first order (edition -> price_list).
        """
        conn = psycopg2.connect(self.dsn)
        counts = {}

        try:
            cur = conn.cursor()

            # ── 1. Clean old version data (Child-first to respect FKs) ──────
            cur.execute("DELETE FROM price_list WHERE version = %s", (version,))
            cur.execute("DELETE FROM edition WHERE version = %s", (version,))
            cur.execute("DELETE FROM car_specs WHERE ingest_version = %s", (version,))
            cur.execute("DELETE FROM car_colors WHERE ingest_version = %s", (version,))
            cur.execute("DELETE FROM car_options WHERE ingest_version = %s", (version,))

            # ── 2. Ingest edition (Parent Table) ───────────────────────────
            ed_values: list = []  # C4 fix: init outside to avoid locals() check
            ed_file = self.output_dir / "edition.csv"
            if ed_file.exists():
                ed_rows = self._read_csv(ed_file)
                seen_ed = set()
                for r in ed_rows:
                    m_id = r["model_id"]
                    e_id = r["edition_id"]
                    if (m_id, e_id) not in seen_ed:
                        seen_ed.add((m_id, e_id))
                        ed_values.append(
                            (
                                version,
                                m_id,
                                e_id,
                                r["model_label"],
                                r["edition_label"],
                                r.get("year_range") or INGEST_YEAR_RANGE,
                                r.get("is_active", "True").lower() in ("true", "1", "yes"),
                            )
                        )

                if ed_values:
                    sql_ed = """
                    INSERT INTO edition (version, model_id, edition_id, model_label, edition_label, year_range, is_active)
                    VALUES %s
                    """
                    execute_values(cur, sql_ed, ed_values)
                counts["edition"] = len(ed_values)

            # ── 3. Ingest price_list (Child Table referencing edition) ─────
            price_file = self.output_dir / "price_list.csv"
            if price_file.exists():
                price_rows = self._read_csv(price_file)
                seen_prices = set()
                price_values = []
                # Only insert if (model_id, edition_id) exists in edition
                valid_ed_keys = set((r[1], r[2]) for r in ed_values) if ed_values else set()

                for r in price_rows:
                    m_id = r["model_id"]
                    e_id = r["edition_id"]
                    if (m_id, e_id) not in valid_ed_keys:
                        continue
                    v_from = r.get("valid_from") or INGEST_VALID_FROM
                    pk = (m_id, e_id, v_from)
                    if pk not in seen_prices:
                        seen_prices.add(pk)
                        price_values.append(
                            (
                                version,
                                m_id,
                                e_id,
                                int(r["price_list_vnd"]) if r.get("price_list_vnd") else None,
                                int(r["price_promo_vnd"]) if r.get("price_promo_vnd") else None,
                                r.get("promo_label") or None,
                                r.get("vat_included", "True").lower() in ("true", "1", "yes"),
                                r.get("battery_included", "True").lower() in ("true", "1", "yes"),
                                v_from,
                                r.get("valid_to") or None,
                                r.get("source_url") or None,
                            )
                        )

                if price_values:
                    sql_price = """
                    INSERT INTO price_list (version, model_id, edition_id, price_list_vnd, price_promo_vnd,
                                            promo_label, vat_included, battery_included, valid_from, valid_to, source_url)
                    VALUES %s
                    """
                    execute_values(cur, sql_price, price_values)
                counts["price_list"] = len(price_values)

            # ── 4. Ingest car_specs ────────────────────────────────────────
            specs_file = self.output_dir / "all_models_specs.json"
            if specs_file.exists():
                with open(specs_file, "r", encoding="utf-8") as f:
                    specs_data = json.load(f)

                from scripts.harness.config import BROCHURE_CATALOG

                url_map = {b["pdf_name"]: b["url"] for b in BROCHURE_CATALOG}
                url_map.update({b["doc_id"]: b["url"] for b in BROCHURE_CATALOG})
                url_map.update({b["model_code"]: b["url"] for b in BROCHURE_CATALOG})

                seen_specs = set()
                specs_values = []
                for r in specs_data:
                    m_code = r["model_code"]
                    v_name = r.get("version_name") or None
                    v_code = r.get("version_code") or None
                    s_cat = r.get("spec_category") or "convenience"
                    s_key = r.get("spec_key") or "custom_spec"

                    p_num = r.get("source_page") or r.get("page")
                    p_int = int(p_num) if p_num is not None and str(p_num).isdigit() else None
                    s_url = r.get("source_url") or None
                    if s_url and not s_url.startswith("http"):
                        s_url = (
                            url_map.get(s_url)
                            or url_map.get(r.get("source_document", ""))
                            or url_map.get(m_code)
                            or s_url
                        )
                    elif not s_url:
                        s_url = url_map.get(r.get("source_document", "")) or url_map.get(m_code)

                    if s_url and p_int and "#page=" not in s_url and (".pdf" in s_url.lower()):
                        s_url = f"{s_url}#page={p_int}"

                    # R3: dedup by key only to satisfy DB unique constraint
                    # (ingest_version, model_code, version_code, version_name, spec_category, spec_key).
                    # File has 1559 rows, DB can only store ~1429 distinct keys; extra values (e.g. duplicate length_mm with different value) are correctly deduped to first occurrence.
                    uniq_k = (version, m_code, v_code or "", v_name or "", s_cat, s_key)
                    if uniq_k not in seen_specs:
                        seen_specs.add(uniq_k)
                        specs_values.append(
                            (
                                version,
                                m_code,
                                v_name,
                                v_code,
                                s_cat,
                                r.get("spec_category_vn") or "",
                                s_key,
                                r.get("spec_key_vn") or "",
                                str(r.get("spec_value", "")),
                                r.get("spec_unit") or None,
                                s_url,
                                p_int,
                                p_int,
                            )
                        )

                if specs_values:
                    sql_specs = """
                    INSERT INTO car_specs (ingest_version, model_code, version_name, version_code,
                                           spec_category, spec_category_vn, spec_key, spec_key_vn,
                                           spec_value, spec_unit, source_url, source_page, page)
                    VALUES %s
                    """
                    execute_values(cur, sql_specs, specs_values)
                counts["car_specs"] = len(specs_values)

            # ── 5. Ingest car_colors ───────────────────────────────────────
            color_file = self.output_dir / "car_colors.csv"
            if color_file.exists():
                color_rows = self._read_csv(color_file)
                seen_colors = set()
                color_values = []
                for r in color_rows:
                    m_id = r["model_id"]
                    v_code = r.get("version_code") or ""
                    c_code = r.get("color_code") or ""
                    i_code = r.get("interior_code") or ""
                    uniq_c = (m_id, v_code, c_code, i_code)
                    if uniq_c not in seen_colors:
                        seen_colors.add(uniq_c)
                        color_values.append(
                            (
                                version,
                                m_id,
                                r.get("version_code") or None,
                                r.get("version_name") or None,
                                r.get("color_code") or None,
                                r.get("color_name") or None,
                                r.get("color_type") or None,
                                int(r.get("color_fee_vnd") or 0),
                                r.get("interior_code") or None,
                                r.get("interior_name") or None,
                                r.get("source_url") or None,
                            )
                        )

                if color_values:
                    sql_color = """
                    INSERT INTO car_colors (ingest_version, model_id, version_code, version_name,
                                            color_code, color_name, color_type, color_fee_vnd,
                                            interior_code, interior_name, source_url)
                    VALUES %s
                    """
                    execute_values(cur, sql_color, color_values)
                counts["car_colors"] = len(color_values)

            # ── 6. Ingest car_options ──────────────────────────────────────
            option_file = self.output_dir / "car_options.csv"
            if option_file.exists():
                option_rows = self._read_csv(option_file)
                seen_opts = set()
                opt_values = []
                for r in option_rows:
                    m_id = r["model_id"]
                    v_code = r.get("version_code") or ""
                    o_grp = r.get("option_group") or "options"
                    v_id = r.get("value_id") or ""
                    uniq_o = (m_id, v_code, o_grp, v_id)
                    if uniq_o not in seen_opts:
                        seen_opts.add(uniq_o)
                        opt_values.append(
                            (
                                version,
                                m_id,
                                r.get("version_code") or None,
                                r.get("version_name") or None,
                                o_grp,
                                r.get("option_name") or "Tùy Chọn",
                                v_id or None,
                                r.get("value_name") or None,
                                int(r.get("price_extra_vnd") or 0),
                                r.get("source_url") or None,
                            )
                        )

                if opt_values:
                    sql_opt = """
                    INSERT INTO car_options (ingest_version, model_id, version_code, version_name,
                                             option_group, option_name, value_id, value_name,
                                             price_extra_vnd, source_url)
                    VALUES %s
                    """
                    execute_values(cur, sql_opt, opt_values)
                counts["car_options"] = len(opt_values)

            # ── 7. Record ingest_version (with is_current=false) ────────────
            total_pg_rows = sum(counts.values())
            cur.execute(
                """
                INSERT INTO ingest_version (version, created_at, prev_version, is_current, pg_rows_upserted, notes)
                VALUES (%s, %s, %s, false, %s, %s)
                ON CONFLICT (version) DO UPDATE SET
                    created_at = EXCLUDED.created_at,
                    pg_rows_upserted = EXCLUDED.pg_rows_upserted,
                    notes = EXCLUDED.notes
            """,
                (
                    version,
                    datetime.now(timezone.utc),
                    INGEST_PREV_VERSION,
                    total_pg_rows,
                    "Ingested by scripts.harness.sinks.postgres",
                ),
            )

            conn.commit()
        finally:
            conn.close()

        return counts

    def _read_csv(self, path: Path) -> List[Dict[str, str]]:
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f, delimiter="|"))
