"""Layout-aware PDF parser using pdfplumber + PyMuPDF."""
from __future__ import annotations

import base64
import io
from enum import Enum
from typing import Optional

import pdfplumber
import fitz  # PyMuPDF
from pydantic import BaseModel


class LayoutType(str, Enum):
    TEXT_HEAVY = "text_heavy"
    TABLE_HEAVY = "table_heavy"
    CHART_HEAVY = "chart_heavy"
    MIXED = "mixed"
    SCANNED = "scanned"


class BBox(BaseModel):
    x0: float; y0: float; x1: float; y1: float


class PageContent(BaseModel):
    page_num: int
    text: str
    images: list[str]        # base64-encoded PNG
    layout_type: LayoutType
    bbox_map: dict           # {"text_blocks": [...], "tables": [...], "figures": [...]}
    word_count: int
    has_tables: bool
    has_images: bool
    width: float
    height: float


class PDFParser:
    """Parse PDF documents into per-page PageContent objects."""

    IMAGE_COVERAGE_THRESHOLD = 0.3   # >30% image area → chart_heavy
    TABLE_COVERAGE_THRESHOLD = 0.25  # >25% table area → table_heavy
    MIN_WORD_COUNT = 20              # below this → scanned

    def parse(self, raw: bytes) -> list[PageContent]:
        pages: list[PageContent] = []

        # pdfplumber for text + table extraction
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            plumber_pages = pdf.pages

            # PyMuPDF for images
            fitz_doc = fitz.open(stream=raw, filetype="pdf")

            for i, page in enumerate(plumber_pages):
                fitz_page = fitz_doc[i]
                w, h = page.width, page.height

                # ── Text extraction ─────────────────────────────────────
                text = page.extract_text() or ""
                word_count = len(text.split())

                # ── Table detection ──────────────────────────────────────
                tables = page.find_tables()
                table_bboxes = []
                for tbl in tables:
                    if tbl.bbox:
                        x0, top, x1, bottom = tbl.bbox
                        table_bboxes.append({"x0": x0, "y0": top, "x1": x1, "y1": bottom})

                # ── Image extraction ─────────────────────────────────────
                images_b64: list[str] = []
                figure_bboxes = []
                for img_info in fitz_page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        base_image = fitz_doc.extract_image(xref)
                        img_bytes = base_image["image"]
                        images_b64.append(base64.b64encode(img_bytes).decode())
                        # Get image bbox via get_image_rects
                        rects = fitz_page.get_image_rects(xref)
                        for r in rects:
                            figure_bboxes.append({"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1})
                    except Exception:
                        continue

                # ── Text block bboxes ────────────────────────────────────
                words = page.extract_words()
                text_bboxes = []
                if words:
                    # Group into rough blocks by y-position clusters
                    current_block: list[dict] = []
                    prev_top = None
                    for word in words:
                        if prev_top is None or abs(word["top"] - prev_top) < 15:
                            current_block.append(word)
                        else:
                            if current_block:
                                text_bboxes.append(_words_to_bbox(current_block))
                            current_block = [word]
                        prev_top = word["top"]
                    if current_block:
                        text_bboxes.append(_words_to_bbox(current_block))

                # ── Layout classification ────────────────────────────────
                layout = _classify_layout(
                    word_count, table_bboxes, figure_bboxes, w, h
                )

                pages.append(PageContent(
                    page_num=i + 1,
                    text=text,
                    images=images_b64,
                    layout_type=layout,
                    bbox_map={
                        "text_blocks": text_bboxes,
                        "tables": table_bboxes,
                        "figures": figure_bboxes,
                    },
                    word_count=word_count,
                    has_tables=len(table_bboxes) > 0,
                    has_images=len(images_b64) > 0,
                    width=w,
                    height=h,
                ))

            fitz_doc.close()

        return pages


def _words_to_bbox(words: list[dict]) -> dict:
    return {
        "x0": min(w["x0"] for w in words),
        "y0": min(w["top"] for w in words),
        "x1": max(w["x1"] for w in words),
        "y1": max(w["bottom"] for w in words),
        "text_preview": " ".join(w["text"] for w in words[:8]),
    }


def _classify_layout(
    word_count: int,
    table_bboxes: list,
    figure_bboxes: list,
    page_w: float,
    page_h: float,
) -> LayoutType:
    if word_count < PDFParser.MIN_WORD_COUNT and not table_bboxes:
        return LayoutType.SCANNED

    page_area = page_w * page_h
    if page_area == 0:
        return LayoutType.TEXT_HEAVY

    fig_area = sum(
        (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) for b in figure_bboxes
    )
    tbl_area = sum(
        (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) for b in table_bboxes
    )

    fig_ratio = fig_area / page_area
    tbl_ratio = tbl_area / page_area

    if fig_ratio > PDFParser.IMAGE_COVERAGE_THRESHOLD and tbl_ratio > PDFParser.TABLE_COVERAGE_THRESHOLD:
        return LayoutType.MIXED
    if fig_ratio > PDFParser.IMAGE_COVERAGE_THRESHOLD:
        return LayoutType.CHART_HEAVY
    if tbl_ratio > PDFParser.TABLE_COVERAGE_THRESHOLD:
        return LayoutType.TABLE_HEAVY
    return LayoutType.TEXT_HEAVY
