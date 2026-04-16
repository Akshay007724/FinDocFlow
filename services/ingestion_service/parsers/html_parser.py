"""HTML/HTM parser for SEC EDGAR filings."""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from .pdf_parser import PageContent, LayoutType


class HTMLParser:
    """Parse HTML documents into page-like PageContent objects."""

    CHUNK_SIZE = 500  # words per synthetic "page"

    def parse(self, raw: bytes, filename: str = "document.html") -> list[PageContent]:
        soup = BeautifulSoup(raw, "lxml")

        # Remove script/style noise
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()

        # Extract tables
        tables = soup.find_all("table")
        table_texts = [t.get_text(" ", strip=True) for t in tables]

        # Extract images
        img_tags = soup.find_all("img")

        # Full text
        full_text = soup.get_text(" ", strip=True)
        full_text = re.sub(r"\s+", " ", full_text).strip()
        words = full_text.split()

        pages: list[PageContent] = []
        chunks = [words[i: i + self.CHUNK_SIZE] for i in range(0, max(len(words), 1), self.CHUNK_SIZE)]
        if not chunks:
            chunks = [[]]

        for idx, chunk in enumerate(chunks):
            chunk_text = " ".join(chunk)
            word_count = len(chunk)

            # Rough layout heuristics per chunk
            has_tbl = any(tt in chunk_text for tt in table_texts[:3]) if table_texts else False
            has_img = len(img_tags) > 0 and idx == 0  # images assumed on first chunk

            if has_tbl and has_img:
                layout = LayoutType.MIXED
            elif has_tbl:
                layout = LayoutType.TABLE_HEAVY
            elif has_img:
                layout = LayoutType.CHART_HEAVY
            elif word_count < 20:
                layout = LayoutType.SCANNED
            else:
                layout = LayoutType.TEXT_HEAVY

            pages.append(PageContent(
                page_num=idx + 1,
                text=chunk_text,
                images=[],
                layout_type=layout,
                bbox_map={"text_blocks": [], "tables": [], "figures": []},
                word_count=word_count,
                has_tables=has_tbl,
                has_images=has_img,
                width=612.0,
                height=792.0,
            ))

        return pages
