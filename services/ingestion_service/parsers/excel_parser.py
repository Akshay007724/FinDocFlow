"""Excel (.xlsx/.xls) parser for financial spreadsheets."""
from __future__ import annotations

import io

import openpyxl

from .pdf_parser import PageContent, LayoutType


class ExcelParser:
    """Parse Excel workbooks — one PageContent per sheet."""

    def parse(self, raw: bytes) -> list[PageContent]:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as exc:
            return [self._empty_page(1, f"Excel parse error: {exc}")]

        pages: list[PageContent] = []
        for idx, ws in enumerate(wb.worksheets):
            rows: list[str] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                if any(c.strip() for c in cells):
                    rows.append("\t".join(cells))

            text = "\n".join(rows)
            word_count = len(text.split())

            # Sheets are inherently tabular
            pages.append(PageContent(
                page_num=idx + 1,
                text=text,
                images=[],
                layout_type=LayoutType.TABLE_HEAVY,
                bbox_map={"text_blocks": [], "tables": [{"x0": 0, "y0": 0, "x1": 612, "y1": 792}], "figures": []},
                word_count=word_count,
                has_tables=True,
                has_images=False,
                width=612.0,
                height=792.0,
            ))

        wb.close()
        return pages if pages else [self._empty_page(1, "Empty workbook")]

    def _empty_page(self, page_num: int, msg: str) -> PageContent:
        return PageContent(
            page_num=page_num,
            text=msg,
            images=[],
            layout_type=LayoutType.TEXT_HEAVY,
            bbox_map={"text_blocks": [], "tables": [], "figures": []},
            word_count=len(msg.split()),
            has_tables=False,
            has_images=False,
            width=612.0,
            height=792.0,
        )
