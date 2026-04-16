"""FinDocFlow — BM25 Retrieval Baseline

For each QA pair:
  1. Loads pre-extracted page texts from Redis (key pattern ``pages:{doc_id}:{page_num}``).
  2. Ranks pages with BM25 (rank_bm25) and selects the top-1 page.
  3. Sends the top page + question to Ollama for answer generation.

The document list is discovered by scanning the bucket manifest stored in MinIO
(``findocflow`` bucket, object ``manifest.json``).  If the manifest is absent the
script falls back to iterating Redis keys for the given doc_ids.

Environment variables:
    MINIO_ENDPOINT   MinIO host:port (default: localhost:9000)
    MINIO_ACCESS_KEY (default: minioadmin)
    MINIO_SECRET_KEY (default: minioadmin)
    REDIS_URL        Redis connection URL (default: redis://localhost:6379/0)
    OLLAMA_BASE_URL  Ollama API base (default: http://localhost:11434)
    OLLAMA_MODEL     Model tag (default: llama3.2)

Usage:
    python -m experiments.baselines.bm25_baseline --dataset dataset/sample_qa.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import redis as redis_lib
from minio import Minio
from rank_bm25 import BM25Okapi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("bm25_baseline")

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = "findocflow"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

DEFAULT_DATASET = Path(__file__).parent.parent.parent / "dataset" / "sample_qa.json"
RESULTS_DIR = Path(__file__).parent.parent / "results"

QA_PROMPT_TEMPLATE = """\
You are a financial analyst assistant. Using ONLY the document excerpt below, \
answer the question concisely and precisely. If the answer includes a number, \
state it explicitly.

Document excerpt (page {page_num}):
\"\"\"
{page_text}
\"\"\"

Question: {question}

Answer:"""

# ---------------------------------------------------------------------------
# Redis page loader
# ---------------------------------------------------------------------------


class RedisPageStore:
    """Fetches page texts stored in Redis under ``pages:{doc_id}:{page_num}``."""

    def __init__(self, redis_url: str) -> None:
        self._client = redis_lib.from_url(redis_url, decode_responses=True)

    def get_pages(self, doc_id: str) -> list[dict[str, Any]]:
        """Return all pages for *doc_id* sorted by page number."""
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
                        # Stored as plain text
                        parts = key.split(":")
                        page_num = int(parts[-1]) if parts[-1].isdigit() else 0
                        page_data = {"page_num": page_num, "text": raw}
                    pages.append(page_data)
                if cursor == 0:
                    break
        except redis_lib.RedisError as exc:
            logger.error("Redis error fetching pages for %s: %s", doc_id, exc)
            raise

        pages.sort(key=lambda p: p.get("page_num", 0))
        logger.debug("Loaded %d pages for doc_id=%s from Redis", len(pages), doc_id)
        return pages

    def ping(self) -> bool:
        try:
            return self._client.ping()
        except redis_lib.RedisError:
            return False


# ---------------------------------------------------------------------------
# MinIO manifest loader
# ---------------------------------------------------------------------------


def load_manifest_from_minio() -> list[str]:
    """Return list of doc_ids from MinIO bucket manifest, or empty list on error."""
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        response = client.get_object(MINIO_BUCKET, "manifest.json")
        manifest = json.loads(response.read().decode("utf-8"))
        doc_ids = [entry["doc_id"] for entry in manifest if "doc_id" in entry]
        logger.info("Loaded manifest from MinIO: %d documents", len(doc_ids))
        return doc_ids
    except Exception as exc:
        logger.warning("Could not load manifest from MinIO: %s", exc)
        return []


# ---------------------------------------------------------------------------
# BM25 retriever
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()


def bm25_top_page(pages: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    """Return the top-ranked page for *query* using BM25Okapi."""
    if not pages:
        return None

    corpus = [tokenize(p.get("text", "")) for p in pages]
    # Filter out empty pages (would cause BM25 to divide by zero)
    non_empty = [(i, toks) for i, toks in enumerate(corpus) if toks]
    if not non_empty:
        logger.warning("All pages are empty — returning first page as fallback.")
        return pages[0]

    indices, tokenized_corpus = zip(*non_empty)
    bm25 = BM25Okapi(list(tokenized_corpus))
    query_tokens = tokenize(query)
    scores = bm25.get_scores(query_tokens)
    best_local_idx = int(scores.argmax())
    best_global_idx = indices[best_local_idx]

    logger.debug(
        "BM25 top page: page_num=%s score=%.3f",
        pages[best_global_idx].get("page_num"),
        scores[best_local_idx],
    )
    return pages[best_global_idx]


# ---------------------------------------------------------------------------
# Ollama answer generator
# ---------------------------------------------------------------------------


def ollama_generate(prompt: str, timeout: float = 90.0) -> str:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 256},
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama HTTP error %s: %s", exc.response.status_code, exc.response.text[:200])
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
) -> dict[str, Any]:
    qa_id = qa["qa_id"]
    doc_id = qa["doc_id"]
    question = qa["question"]

    result: dict[str, Any] = {
        "qa_id": qa_id,
        "doc_id": doc_id,
        "question_type": qa.get("question_type"),
        "difficulty": qa.get("difficulty"),
        "model": "bm25",
        "predicted_answer": None,
        "retrieved_page_num": None,
        "latency_s": None,
        "error": None,
    }

    # Load pages (cached per doc)
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

    # BM25 retrieval
    top_page = bm25_top_page(pages, question)
    if top_page is None:
        result["error"] = "BM25 returned no page"
        return result

    page_num = top_page.get("page_num", "?")
    page_text = top_page.get("text", "")[:3000]  # cap context length
    result["retrieved_page_num"] = page_num

    # LLM generation
    prompt = QA_PROMPT_TEMPLATE.format(
        page_num=page_num,
        page_text=page_text,
        question=question,
    )
    try:
        answer = ollama_generate(prompt)
    except Exception as exc:
        result["error"] = f"Ollama error: {exc}"
        result["latency_s"] = round(time.perf_counter() - t0, 3)
        return result

    result["latency_s"] = round(time.perf_counter() - t0, 3)
    result["predicted_answer"] = answer

    logger.info(
        "%s | page=%s | latency=%.1fs | answer_snippet=%s",
        qa_id,
        page_num,
        result["latency_s"],
        answer[:80],
    )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BM25 + Ollama retrieval baseline for FinDocFlow.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=None, help="Max QA pairs to evaluate.")
    parser.add_argument("--redis-url", type=str, default=REDIS_URL)
    parser.add_argument("--ollama-url", type=str, default=OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", type=str, default=OLLAMA_MODEL)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    # Allow CLI overrides of env-derived globals
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

    logger.info("BM25 baseline: evaluating %d questions", len(qa_pairs))

    # Health-check Redis
    page_store = RedisPageStore(args.redis_url)
    if not page_store.ping():
        logger.error("Cannot connect to Redis at %s", args.redis_url)
        sys.exit(1)
    logger.info("Redis connection OK")

    page_cache: dict[str, list[dict[str, Any]]] = {}
    results: list[dict[str, Any]] = []

    for i, qa in enumerate(qa_pairs, start=1):
        logger.info("[%d/%d] %s", i, len(qa_pairs), qa["qa_id"])
        result = evaluate_single(qa, page_store, page_cache)
        results.append(result)

    # Write output
    args.output_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.output_dir / f"bm25_{timestamp}.json"
    with out_path.open("w") as fh:
        json.dump(
            {
                "model": "bm25",
                "timestamp": timestamp,
                "dataset": str(dataset_path),
                "results": results,
            },
            fh,
            indent=2,
        )
    logger.info("Results written to %s", out_path)

    # Quick summary
    valid = [r for r in results if r["error"] is None]
    errors = len(results) - len(valid)
    print(f"\nBM25 baseline complete: {len(valid)}/{len(results)} answered, {errors} errors.")
    if valid:
        avg_latency = sum(r["latency_s"] for r in valid) / len(valid)
        print(f"Average latency: {avg_latency:.2f}s")


if __name__ == "__main__":
    main()
