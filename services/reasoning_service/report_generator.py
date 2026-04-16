"""Multi-document analyst recommendation report generator."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ollama_client import OllamaClient

logger = logging.getLogger(__name__)

PROMPTS_FILE = Path(__file__).parent / "prompts.json"


def load_prompts() -> dict:
    with open(PROMPTS_FILE) as f:
        return json.load(f)


SYSTEM_PROMPT = """You are FinDocFlow, an expert equity research analyst specializing in SEC financial filings.
You produce precise, evidence-based analysis grounded strictly in the provided document text.
Always cite page numbers using [Page N] notation. Never fabricate data not present in the documents."""


class ReportGenerator:
    """Generates structured analyst recommendation reports from multiple document pages."""

    MAX_PAGES_PER_SECTION = 15
    MAX_CHARS_PER_PAGE = 1000

    def __init__(self, ollama: OllamaClient) -> None:
        self._ollama = ollama
        self._executor = ThreadPoolExecutor(max_workers=4)

    def generate_section(
        self,
        section_id: str,
        section_prompt: str,
        pages: list[dict],
        entities: list[dict],
    ) -> dict:
        """Generate a single report section."""
        page_context = self._build_page_context(pages)
        entity_context = self._build_entity_context(entities)

        full_prompt = (
            f"{section_prompt}\n\n"
            f"## Document Pages\n{page_context}\n\n"
            f"## Known Financial Entities\n{entity_context}"
        )

        # Use vision if pages have images
        page_images = [img for p in pages[:5] for img in p.get("images", [])[:1]]
        if page_images:
            content = self._ollama.generate_with_images(
                full_prompt, images=page_images, system=SYSTEM_PROMPT, temperature=0.1
            )
        else:
            content = self._ollama.generate(full_prompt, system=SYSTEM_PROMPT, temperature=0.1)

        return {"section_id": section_id, "content": content, "error": None}

    def generate_report(
        self,
        pages: list[dict],
        section_ids: list[str],
        entities: list[dict],
    ) -> dict:
        """Generate all requested sections, running up to 4 in parallel."""
        prompts_data = load_prompts()
        section_map = {s["id"]: s for s in prompts_data["sections"]}

        results = {}
        futures = {}

        with ThreadPoolExecutor(max_workers=4) as pool:
            for sid in section_ids:
                if sid not in section_map:
                    continue
                section = section_map[sid]
                future = pool.submit(
                    self.generate_section,
                    sid,
                    section["prompt"],
                    pages[: self.MAX_PAGES_PER_SECTION],
                    entities,
                )
                futures[future] = sid

            for future in as_completed(futures):
                sid = futures[future]
                try:
                    results[sid] = future.result()
                except Exception as exc:
                    logger.exception("Section %s failed: %s", sid, exc)
                    results[sid] = {"section_id": sid, "content": "", "error": str(exc)}

        # Return sections in requested order
        ordered = []
        for sid in section_ids:
            if sid in results:
                meta = section_map.get(sid, {})
                ordered.append({
                    "section_id": sid,
                    "label": meta.get("label", sid),
                    "icon": meta.get("icon", "📄"),
                    "content": results[sid]["content"],
                    "error": results[sid].get("error"),
                })

        return {"sections": ordered, "page_count": len(pages), "entity_count": len(entities)}

    def chat(
        self,
        messages: list[dict],
        pages: list[dict],
        section_prompt: Optional[str] = None,
    ) -> str:
        """Answer a chat message grounded in document pages."""
        page_context = self._build_page_context(pages)

        system = SYSTEM_PROMPT
        if section_prompt:
            system = f"{SYSTEM_PROMPT}\n\nFocus your analysis on the following analytical framework:\n{section_prompt}"

        # Build conversation history as a single prompt
        history = ""
        for msg in messages[:-1]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history += f"\n{role}: {msg['content']}\n"

        current_question = messages[-1]["content"] if messages else ""

        prompt = (
            f"## Document Context\n{page_context}\n\n"
            f"## Conversation History\n{history}\n"
            f"## Current Question\n{current_question}"
        )

        page_images = [img for p in pages[:3] for img in p.get("images", [])[:1]]
        if page_images:
            return self._ollama.generate_with_images(
                prompt, images=page_images, system=system, temperature=0.1
            )
        return self._ollama.generate(prompt, system=system, temperature=0.1)

    def _build_page_context(self, pages: list[dict]) -> str:
        lines = []
        for page in pages[: self.MAX_PAGES_PER_SECTION]:
            text = (page.get("text") or "")[:self.MAX_CHARS_PER_PAGE]
            page_num = page.get("page_num", "?")
            layout = page.get("layout_type", "")
            tags = []
            if page.get("has_tables"):
                tags.append("tables")
            if page.get("has_images"):
                tags.append("images")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"[Page {page_num}]{tag_str}\n{text}")
        return "\n\n---\n\n".join(lines)

    def _build_entity_context(self, entities: list[dict]) -> str:
        if not entities:
            return "No entities extracted."
        items = []
        for e in entities[:30]:
            if e.get("type") == "metric" and e.get("value"):
                items.append(
                    f"• {e['text']}: {e['value']} (period: {e.get('period', '?')}) [p.{e.get('page_num', '?')}]"
                )
        return "\n".join(items) if items else "No financial metrics found."
