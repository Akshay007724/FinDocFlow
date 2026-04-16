"""THINK → ACT → VERIFY reasoning loop for multi-page financial Q&A."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ollama_client import OllamaClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are FinDocFlow, a financial document reasoning assistant.
You reason step-by-step over multi-page financial filings to answer questions precisely.
Always cite page numbers and quote relevant text. Be concise and factual."""

THINK_TEMPLATE = """
## THINK
You are analyzing a financial document to answer the following question:

**Question:** {question}

**Available pages (with page numbers):**
{page_context}

**Known entities from the document:**
{entities}

First, think through which pages are most relevant and what information you need.
Write your reasoning plan in 3-5 bullet points. Start each bullet with "•".
"""

ACT_TEMPLATE = """
## ACT
Based on your reasoning plan, extract the specific information needed.

**Question:** {question}

**Most relevant pages:**
{relevant_pages}

Extract the key facts, numbers, and quotes needed to answer the question.
Format as: [Page N] "quoted text" → fact
"""

VERIFY_TEMPLATE = """
## VERIFY
Cross-check your extracted facts and formulate the final answer.

**Question:** {question}

**Extracted facts:**
{facts}

**Entity graph context:**
{graph_context}

Now verify consistency and provide a final, precise answer. Include:
1. Direct answer (1-2 sentences)
2. Supporting evidence (page citations)
3. Confidence level: HIGH / MEDIUM / LOW
4. Any caveats or limitations
"""


@dataclass
class ReasoningResult:
    question: str
    think: str
    act: str
    verify: str
    answer: str
    confidence: str
    cited_pages: list[int]
    iterations: int = 1


class ThinkActVerifyAgent:
    """Multi-step reasoning agent implementing the THINK→ACT→VERIFY loop."""

    MAX_PAGES_IN_CONTEXT = 10
    MAX_CHARS_PER_PAGE = 800

    def __init__(self, ollama: OllamaClient) -> None:
        self._ollama = ollama

    def reason(
        self,
        question: str,
        pages: list[dict],
        entities: list[dict],
        graph_context: list[dict],
        relevant_page_indices: list[int],
    ) -> ReasoningResult:
        """Run the full THINK→ACT→VERIFY chain."""

        # Build page context strings
        page_summaries = self._build_page_context(pages)
        entity_summary = self._build_entity_summary(entities)

        # ── THINK ────────────────────────────────────────────────────────
        think_prompt = THINK_TEMPLATE.format(
            question=question,
            page_context=page_summaries,
            entities=entity_summary,
        )
        think_response = self._ollama.generate(think_prompt, system=SYSTEM_PROMPT)
        logger.debug("THINK: %s", think_response[:200])

        # ── ACT ──────────────────────────────────────────────────────────
        # Focus on top relevant pages
        top_indices = (relevant_page_indices or list(range(len(pages))))[:self.MAX_PAGES_IN_CONTEXT]
        top_pages = [pages[i] for i in top_indices if i < len(pages)]
        relevant_pages_text = self._build_page_context(top_pages)
        act_prompt = ACT_TEMPLATE.format(
            question=question,
            relevant_pages=relevant_pages_text,
        )
        # Use vision if any top pages have images
        page_images = [img for p in top_pages for img in p.get("images", [])[:1]]
        if page_images:
            act_response = self._ollama.generate_with_images(
                act_prompt, images=page_images[:5], system=SYSTEM_PROMPT
            )
        else:
            act_response = self._ollama.generate(act_prompt, system=SYSTEM_PROMPT)
        logger.debug("ACT: %s", act_response[:200])

        # ── VERIFY ───────────────────────────────────────────────────────
        graph_str = self._build_graph_context(graph_context)
        verify_prompt = VERIFY_TEMPLATE.format(
            question=question,
            facts=act_response,
            graph_context=graph_str,
        )
        verify_response = self._ollama.generate(verify_prompt, system=SYSTEM_PROMPT)
        logger.debug("VERIFY: %s", verify_response[:200])

        # Extract confidence and cited pages
        confidence = _extract_confidence(verify_response)
        cited_pages = _extract_page_citations(verify_response)
        answer = _extract_direct_answer(verify_response)

        return ReasoningResult(
            question=question,
            think=think_response,
            act=act_response,
            verify=verify_response,
            answer=answer,
            confidence=confidence,
            cited_pages=cited_pages,
        )

    def _build_page_context(self, pages: list[dict]) -> str:
        lines = []
        for page in pages[:self.MAX_PAGES_IN_CONTEXT]:
            text = page.get("text", "")[:self.MAX_CHARS_PER_PAGE]
            lines.append(f"[Page {page.get('page_num', '?')}] {text}")
        return "\n\n".join(lines)

    def _build_entity_summary(self, entities: list[dict]) -> str:
        if not entities:
            return "No entities extracted."
        items = []
        for e in entities[:20]:
            if e["type"] == "metric" and e.get("value"):
                items.append(f"• {e['text']}: {e['value']} ({e.get('period', '?')}) [p.{e['page_num']}]")
        return "\n".join(items) if items else "No financial metrics found."

    def _build_graph_context(self, graph_context: list[dict]) -> str:
        if not graph_context:
            return "No graph context available."
        lines = [f"• {g}" for g in graph_context[:10]]
        return "\n".join(lines)


def _extract_confidence(text: str) -> str:
    text_upper = text.upper()
    if "CONFIDENCE: HIGH" in text_upper or "HIGH CONFIDENCE" in text_upper:
        return "HIGH"
    if "CONFIDENCE: LOW" in text_upper or "LOW CONFIDENCE" in text_upper:
        return "LOW"
    return "MEDIUM"


def _extract_page_citations(text: str) -> list[int]:
    import re
    return list({int(m) for m in re.findall(r"\[Page\s+(\d+)\]", text, re.IGNORECASE)})


def _extract_direct_answer(text: str) -> str:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Return first non-header line after "VERIFY"
    capturing = False
    for line in lines:
        if "VERIFY" in line.upper() or "DIRECT ANSWER" in line.upper():
            capturing = True
            continue
        if capturing and line and not line.startswith("#"):
            return line
    return lines[-1] if lines else text[:200]
