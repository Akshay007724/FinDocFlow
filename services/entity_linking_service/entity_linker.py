"""Named entity recognition + cross-page linking using sentence-transformers."""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer, util
    _st_available = True
except ImportError:
    _st_available = False
    logger.warning("sentence-transformers not available — embedding linking disabled")

# Regex patterns for financial entities
_COMPANY_PATTERNS = [
    r"\b([A-Z][a-zA-Z0-9&\.\s,]+(?:Inc\.|Corp\.|LLC|Ltd\.|Co\.|Group|Holdings))\b",
    r"\b([A-Z]{2,6})\b",   # ticker symbols
]
_METRIC_PATTERNS = {
    "revenue": r"(?:total\s+)?revenue[s]?",
    "net_income": r"net\s+income|net\s+earnings",
    "operating_income": r"operating\s+(?:income|profit)",
    "gross_profit": r"gross\s+(?:profit|margin)",
    "ebitda": r"ebitda",
    "eps": r"(?:basic|diluted)?\s*(?:earnings|loss)\s+per\s+share|eps",
    "total_assets": r"total\s+assets",
    "total_debt": r"total\s+(?:debt|liabilities)",
    "cash": r"cash\s+(?:and\s+cash\s+equivalents)?",
    "capex": r"capital\s+expenditures?|capex",
    "free_cash_flow": r"free\s+cash\s+flow",
}
_PERIOD_PATTERN = r"\b(?:FY|Q[1-4])\s*\d{4}|\b(?:fiscal\s+year\s+)?\d{4}\b"
_VALUE_PATTERN = r"\$\s*[\d,\.]+\s*(?:million|billion|thousand|M|B|K)?"


class EntityLinker:
    """Extract entities from page text and prepare Neo4j graph entries."""

    def __init__(self) -> None:
        self._embedder = None
        if _st_available:
            try:
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("SentenceTransformer loaded for entity linking")
            except Exception as exc:
                logger.warning("Failed to load SentenceTransformer: %s", exc)

    def extract_entities(self, text: str, doc_id: str, page_num: int) -> list[dict]:
        """
        Extract financial entities from page text.

        Returns list of:
            {
                "type": "company|metric|period",
                "text": str,
                "value": str | None,
                "period": str | None,
                "doc_id": str,
                "page_num": int,
                "char_span": [start, end],
            }
        """
        entities = []

        # Extract companies
        for pattern in _COMPANY_PATTERNS:
            for m in re.finditer(pattern, text):
                entities.append({
                    "type": "company",
                    "text": m.group(1).strip(),
                    "value": None,
                    "period": None,
                    "doc_id": doc_id,
                    "page_num": page_num,
                    "char_span": [m.start(), m.end()],
                })

        # Extract metrics with nearby values
        for metric_name, pattern in _METRIC_PATTERNS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                # Look for a value in ±100 chars
                window = text[max(0, m.start() - 50): m.end() + 100]
                val_match = re.search(_VALUE_PATTERN, window, re.IGNORECASE)
                period_match = re.search(_PERIOD_PATTERN, window, re.IGNORECASE)
                entities.append({
                    "type": "metric",
                    "text": metric_name,
                    "value": val_match.group(0).strip() if val_match else None,
                    "period": period_match.group(0).strip() if period_match else None,
                    "doc_id": doc_id,
                    "page_num": page_num,
                    "char_span": [m.start(), m.end()],
                })

        # Extract time periods
        for m in re.finditer(_PERIOD_PATTERN, text):
            entities.append({
                "type": "period",
                "text": m.group(0).strip(),
                "value": None,
                "period": m.group(0).strip(),
                "doc_id": doc_id,
                "page_num": page_num,
                "char_span": [m.start(), m.end()],
            })

        return entities

    def embed_text(self, text: str) -> list[float]:
        """Return sentence embedding for semantic search."""
        if not self._embedder:
            return []
        return self._embedder.encode(text, convert_to_numpy=True).tolist()

    def find_similar_pages(
        self, query: str, page_texts: list[str], top_k: int = 5
    ) -> list[int]:
        """
        Return indices of the top-k most semantically similar pages.
        Falls back to empty list if embedder not available.
        """
        if not self._embedder or not page_texts:
            return []
        query_emb = self._embedder.encode(query, convert_to_tensor=True)
        corpus_emb = self._embedder.encode(page_texts, convert_to_tensor=True)
        scores = util.cos_sim(query_emb, corpus_emb)[0].tolist()
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return ranked[:top_k]
