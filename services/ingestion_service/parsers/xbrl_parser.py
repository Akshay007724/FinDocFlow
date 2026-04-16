"""XBRL/XML parser for SEC financial filings."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict

from .pdf_parser import PageContent, LayoutType


class XBRLParser:
    """Parse XBRL documents into per-context PageContent objects."""

    CHUNK_SIZE = 30  # facts per synthetic page

    def parse(self, raw: bytes) -> list[PageContent]:
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return [self._empty_page(1, "XBRL parse error")]

        # Strip namespace from tags
        def strip_ns(tag: str) -> str:
            return tag.split("}")[-1] if "}" in tag else tag

        # Collect all facts (elements with text content)
        facts: list[dict] = []
        for elem in root.iter():
            tag = strip_ns(elem.tag)
            if elem.text and elem.text.strip():
                context = elem.attrib.get("contextRef", "")
                unit = elem.attrib.get("unitRef", "")
                decimals = elem.attrib.get("decimals", "")
                facts.append({
                    "tag": tag,
                    "value": elem.text.strip(),
                    "context": context,
                    "unit": unit,
                    "decimals": decimals,
                })

        if not facts:
            return [self._empty_page(1, "No XBRL facts found")]

        # Group into pages of CHUNK_SIZE facts
        pages: list[PageContent] = []
        chunks = [facts[i: i + self.CHUNK_SIZE] for i in range(0, len(facts), self.CHUNK_SIZE)]

        for idx, chunk in enumerate(chunks):
            lines = [f"{f['tag']}: {f['value']}" + (f" ({f['unit']})" if f['unit'] else "") for f in chunk]
            text = "\n".join(lines)
            word_count = sum(len(l.split()) for l in lines)

            # Financial data → table heavy
            numeric_count = sum(1 for f in chunk if f["unit"] or f["decimals"])
            layout = LayoutType.TABLE_HEAVY if numeric_count > len(chunk) * 0.5 else LayoutType.TEXT_HEAVY

            pages.append(PageContent(
                page_num=idx + 1,
                text=text,
                images=[],
                layout_type=layout,
                bbox_map={"text_blocks": [], "tables": [], "figures": []},
                word_count=word_count,
                has_tables=(numeric_count > 0),
                has_images=False,
                width=612.0,
                height=792.0,
            ))

        return pages

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
