"""FinDocFlow — LLM-Only (Long-Context) Baseline

No retrieval, no structured extraction.  All pages are concatenated (up to a
configurable token budget) and fed directly to Ollama as a single prompt.

Page texts are loaded from Redis (key pattern ``pages:{doc_id}:{page_num}``).

This baseline tests how well a large-context LLM performs when given the full
document without any graph, chart, or multi-step reasoning scaffolding.

Environment variables:
    REDIS_URL        Redis connection URL (default: redis://localhost:6379/0)
    OLLAMA_BASE_URL  Ollama API base (default: http://localhost:11434)
    OLLAMA_MODEL     Model tag (default: llama3.2)
    MAX_TOKENS       Approximate token budget for context (default: 6000)

Usage:
    python -m experiments.baselines.llm_only_baseline --dataset dataset/sample_qa.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import redis as redis_lib

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("llm_only_baseline")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
# Rough token budget: 1 token ≈ 4 characters
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "6000"))
CHARS_PER_TOKEN = 4

DEFAULT_DATASET = Path(__file__).parent.parent.parent / "dataset" / "sample_qa.json"
RESULTS_DIR = Path(__file__).parent.parent / "results"

SYSTEM_PROMPT = (
    "You are a financial analyst assistant with expertise in SEC filings, "
    "10-K reports, and corporate earnings. Answer questions precisely and concisely "
    "based solely on the provided document context. Always cite relevant numbers and, "
    "when appropriate, mention which section of the document supports your answer."
)

QA_PROMPT_TEMPLATE = """\
The following is an excerpt from a financial document ({doc_id}). \
Read it carefully and answer the question at the end.

--- DOCUMENT CONTEXT ---
{context}
--- END OF DOCUMENT CONTEXT ---

Question: {question}

Provide a direct, factual answer. If the answer involves a specific number, \
state it explicitly (e.g., "$28.1 billion" or "19%"). \
If you cannot determine the answer from the provided context, say so clearly.

Answer:"""

# ---------------------------------------------------------------------------
# Token-budget context builder
# ---------------------------------------------------------------------------


def build_context(pages: list[dict[str, Any]], max_tokens: int = MAX_TOKENS) -> tuple[str, int]:
    """Concatenate pages up to *max_tokens*, returning (context_text, pages_used)."""
    budget = max_tokens * CHARS_PER_TOKEN
    parts: list[str] = []
    used = 0

    for page in pages:
        page_num = page.get("page_num", "?")
        text = (page.get("text") or "").strip()
        if not text:
            continue

        header = f"[Page {page_num}]"
        segment = f"{header}\n{text}\n"

        if len("".join(parts)) + len(segment) > budget:
            # Try to fit a truncated version of the last page
            remaining = budget - len("".join(parts))
            if remaining > len(header) + 50:
                truncated = segment[: remaining - 3] + "..."
                parts.append(truncated)
                used += 1
            break

        parts.append(segment)
        used += 1

    context = "\n".join(parts)
    logger.debug(
        "Context built: %d pages used, ~%d tokens",
        used,
        len(context) // CHARS_PER_TOKEN,
    )
    return context, used


# ---------------------------------------------------------------------------
# Redis page loader
# ---------------------------------------------------------------------------


class RedisPageStore:
    def __init__(self, redis_url: str) -> None:
        self._client = redis_lib.from_url(redis_url, decode_responses=True)

    def get_pages(self, doc_id: str) -> list[dict[str, Any]]:
        pattern = f"pages:{doc_id}:*"
        pages: list[dict[str, Any]] = []
        try:
            cursor = 0
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=500)
                for key in keys:
                    raw = self._client.get(key)
                    if raw is None:
                        continue
                    try:
                        page_data = json.loads(raw)
                    except json.JSONDecodeError:
                        parts = key.split(":")
                        page_num = int(parts[-1]) if parts[-1].isdigit() else 0
                        page_data = {"page_num": page_num, "text": raw}
                    pages.append(page_data)
                if cursor == 0:
                    break
        except redis_lib.RedisError as exc:
            logger.error("Redis error for %s: %s", doc_id, exc)
            raise
        pages.sort(key=lambda p: p.get("page_num", 0))
        return pages

    def ping(self) -> bool:
        try:
            return self._client.ping()
        except redis_lib.RedisError:
            return False


# ---------------------------------------------------------------------------
# Ollama generator — supports optional system prompt
# ---------------------------------------------------------------------------


def ollama_generate(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.1,
    num_predict: int = 512,
    timeout: float = 180.0,
) -> str:
    """Call Ollama /api/generate and return the response string."""
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    if system:
        payload["system"] = system

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        raise
    except httpx.RequestError as exc:
        logger.error("Ollama request error: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Per-question evaluation
# ---------------------------------------------------------------------------


def evaluate_single(
    qa: dict[str, Any],
    page_store: RedisPageStore,
    page_cache: dict[str, list[dict[str, Any]]],
    max_tokens: int,
) -> dict[str, Any]:
    qa_id = qa["qa_id"]
    doc_id = qa["doc_id"]
    question = qa["question"]

    result: dict[str, Any] = {
        "qa_id": qa_id,
        "doc_id": doc_id,
        "question_type": qa.get("question_type"),
        "difficulty": qa.get("difficulty"),
        "model": "llm_only",
        "predicted_answer": None,
        "pages_in_context": 0,
        "context_tokens_approx": 0,
        "latency_s": None,
        "error": None,
    }

    # Load all pages for this document (cached)
    if doc_id not in page_cache:
        try:
            page_cache[doc_id] = page_store.get_pages(doc_id)
        except Exception as exc:
            result["error"] = f"Redis error: {exc}"
            return result

    pages = page_cache[doc_id]
    if not pages:
        result["error"] = f"No pages found in Redis for doc_id={doc_id}"
        logger.warning(result["error"])
        return result

    t0 = time.perf_counter()

    # Build long context
    context, pages_used = build_context(pages, max_tokens=max_tokens)
    result["pages_in_context"] = pages_used
    result["context_tokens_approx"] = len(context) // CHARS_PER_TOKEN

    if not context.strip():
        result["error"] = "Empty context after building from pages"
        result["latency_s"] = round(time.perf_counter() - t0, 3)
        return result

    prompt = QA_PROMPT_TEMPLATE.format(
        doc_id=doc_id,
        context=context,
        question=question,
    )

    try:
        answer = ollama_generate(prompt, system=SYSTEM_PROMPT)
    except Exception as exc:
        result["error"] = f"Ollama error: {exc}"
        result["latency_s"] = round(time.perf_counter() - t0, 3)
        return result

    result["latency_s"] = round(time.perf_counter() - t0, 3)
    result["predicted_answer"] = answer

    logger.info(
        "%s | pages_in_ctx=%d | ~%d tokens | latency=%.1fs | answer_snippet=%s",
        qa_id,
        pages_used,
        result["context_tokens_approx"],
        result["latency_s"],
        answer[:80],
    )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LLM-only long-context baseline for FinDocFlow.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--redis-url", type=str, default=REDIS_URL)
    parser.add_argument("--ollama-url", type=str, default=OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", type=str, default=OLLAMA_MODEL)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=MAX_TOKENS,
        help="Approximate token budget for the document context.",
    )
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="LLM sampling temperature.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    global OLLAMA_BASE_URL, OLLAMA_MODEL
    OLLAMA_BASE_URL = args.ollama_url
    OLLAMA_MODEL = args.ollama_model

    dataset_path = args.dataset
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", dataset_path)
        sys.exit(1)

    with dataset_path.open() as fh:
        qa_pairs: list[dict[str, Any]] = json.load(fh)

    if args.limit:
        qa_pairs = qa_pairs[: args.limit]

    logger.info(
        "LLM-only baseline: evaluating %d questions (max_tokens=%d)",
        len(qa_pairs),
        args.max_tokens,
    )

    # Connect to Redis
    page_store = RedisPageStore(args.redis_url)
    if not page_store.ping():
        logger.error("Cannot connect to Redis at %s", args.redis_url)
        sys.exit(1)
    logger.info("Redis connection OK")

    page_cache: dict[str, list[dict[str, Any]]] = {}
    results: list[dict[str, Any]] = []

    for i, qa in enumerate(qa_pairs, start=1):
        logger.info("[%d/%d] %s", i, len(qa_pairs), qa["qa_id"])
        result = evaluate_single(qa, page_store, page_cache, args.max_tokens)
        results.append(result)

    # Write output
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.output_dir / f"llm_only_{timestamp}.json"
    with out_path.open("w") as fh:
        json.dump(
            {
                "model": "llm_only",
                "ollama_model": args.ollama_model,
                "max_tokens": args.max_tokens,
                "timestamp": timestamp,
                "dataset": str(dataset_path),
                "results": results,
            },
            fh,
            indent=2,
        )
    logger.info("Results written to %s", out_path)

    valid = [r for r in results if r["error"] is None]
    errors = len(results) - len(valid)
    print(f"\nLLM-only baseline complete: {len(valid)}/{len(results)} answered, {errors} errors.")
    if valid:
        avg_latency = sum(r["latency_s"] for r in valid) / len(valid)
        avg_pages = sum(r["pages_in_context"] for r in valid) / len(valid)
        avg_tokens = sum(r["context_tokens_approx"] for r in valid) / len(valid)
        print(
            f"Average latency: {avg_latency:.2f}s | "
            f"Avg pages in context: {avg_pages:.1f} | "
            f"Avg context tokens: {avg_tokens:.0f}"
        )


if __name__ == "__main__":
    main()
