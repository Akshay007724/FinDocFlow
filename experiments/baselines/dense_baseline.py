"""FinDocFlow — Dense Retrieval Baseline

For each QA pair:
  1. Encodes all document pages with sentence-transformers (all-MiniLM-L6-v2).
  2. Retrieves the top-1 page by cosine similarity to the question embedding.
  3. Sends the top page + question to Ollama for answer generation.

Page texts are loaded from Redis (same key pattern as the BM25 baseline):
    pages:{doc_id}:{page_num}

Environment variables:
    REDIS_URL        Redis connection URL (default: redis://localhost:6379/0)
    OLLAMA_BASE_URL  Ollama API base (default: http://localhost:11434)
    OLLAMA_MODEL     Model tag (default: llama3.2)
    EMBEDDING_MODEL  Sentence-transformers model (default: all-MiniLM-L6-v2)
    EMBEDDING_DEVICE cpu | cuda (default: cpu)

Usage:
    python -m experiments.baselines.dense_baseline --dataset dataset/sample_qa.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import redis as redis_lib
from sentence_transformers import SentenceTransformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("dense_baseline")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")

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
# Embedding model (singleton)
# ---------------------------------------------------------------------------


class EmbeddingModel:
    """Wraps sentence-transformers with a simple cache for page embeddings."""

    def __init__(self, model_name: str = EMBEDDING_MODEL, device: str = EMBEDDING_DEVICE) -> None:
        logger.info("Loading sentence-transformer: %s (device=%s)", model_name, device)
        self._model = SentenceTransformer(model_name, device=device)
        self._model_name = model_name
        logger.info("Embedding model loaded.")

    def encode(self, texts: list[str], batch_size: int = 64, show_progress: bool = False) -> np.ndarray:
        """Return L2-normalized embeddings as a float32 numpy array of shape (N, D)."""
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)


# ---------------------------------------------------------------------------
# Redis page loader (same as BM25 baseline — duplicated for independence)
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
# Cosine similarity retrieval
# ---------------------------------------------------------------------------


def cosine_top_page(
    pages: list[dict[str, Any]],
    question: str,
    embed_model: EmbeddingModel,
    page_emb_cache: dict[str, np.ndarray],
    doc_id: str,
) -> dict[str, Any] | None:
    """Return the page most similar to *question* by cosine similarity."""
    if not pages:
        return None

    # Encode pages (cached per doc)
    if doc_id not in page_emb_cache:
        texts = [p.get("text", "") or "" for p in pages]
        logger.debug("Encoding %d pages for doc_id=%s ...", len(texts), doc_id)
        page_emb_cache[doc_id] = embed_model.encode(texts)

    page_embeddings = page_emb_cache[doc_id]  # shape (N, D), L2-normalized

    query_emb = embed_model.encode([question])  # shape (1, D)
    # Cosine similarity = dot product for L2-normalized vectors
    scores = (page_embeddings @ query_emb.T).squeeze(axis=-1)  # shape (N,)

    best_idx = int(np.argmax(scores))
    logger.debug(
        "Dense top page: page_num=%s score=%.4f",
        pages[best_idx].get("page_num"),
        float(scores[best_idx]),
    )
    return pages[best_idx]


# ---------------------------------------------------------------------------
# Ollama generator
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
            return response.json().get("response", "").strip()
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
    embed_model: EmbeddingModel,
    page_cache: dict[str, list[dict[str, Any]]],
    page_emb_cache: dict[str, np.ndarray],
) -> dict[str, Any]:
    qa_id = qa["qa_id"]
    doc_id = qa["doc_id"]
    question = qa["question"]

    result: dict[str, Any] = {
        "qa_id": qa_id,
        "doc_id": doc_id,
        "question_type": qa.get("question_type"),
        "difficulty": qa.get("difficulty"),
        "model": "dense",
        "predicted_answer": None,
        "retrieved_page_num": None,
        "similarity_score": None,
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

    top_page = cosine_top_page(pages, question, embed_model, page_emb_cache, doc_id)
    if top_page is None:
        result["error"] = "Dense retrieval returned no page"
        return result

    page_num = top_page.get("page_num", "?")
    page_text = top_page.get("text", "")[:3000]
    result["retrieved_page_num"] = page_num

    # Compute similarity score for the top page (for logging / analysis)
    query_emb = embed_model.encode([question])
    doc_embs = page_emb_cache.get(doc_id)
    if doc_embs is not None:
        page_idx = next(
            (i for i, p in enumerate(pages) if p.get("page_num") == page_num), None
        )
        if page_idx is not None:
            result["similarity_score"] = round(
                float(doc_embs[page_idx] @ query_emb[0]), 4
            )

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
        "%s | page=%s | sim=%.4f | latency=%.1fs | answer_snippet=%s",
        qa_id,
        page_num,
        result["similarity_score"] or 0.0,
        result["latency_s"],
        answer[:80],
    )
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dense retrieval + Ollama baseline for FinDocFlow.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--redis-url", type=str, default=REDIS_URL)
    parser.add_argument("--ollama-url", type=str, default=OLLAMA_BASE_URL)
    parser.add_argument("--ollama-model", type=str, default=OLLAMA_MODEL)
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=EMBEDDING_MODEL,
        help="Sentence-transformers model name.",
    )
    parser.add_argument(
        "--embedding-device",
        type=str,
        default=EMBEDDING_DEVICE,
        choices=["cpu", "cuda", "mps"],
    )
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
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

    logger.info("Dense baseline: evaluating %d questions", len(qa_pairs))

    # Connect to Redis
    page_store = RedisPageStore(args.redis_url)
    if not page_store.ping():
        logger.error("Cannot connect to Redis at %s", args.redis_url)
        sys.exit(1)
    logger.info("Redis connection OK")

    # Load embedding model once
    embed_model = EmbeddingModel(
        model_name=args.embedding_model,
        device=args.embedding_device,
    )

    page_cache: dict[str, list[dict[str, Any]]] = {}
    page_emb_cache: dict[str, np.ndarray] = {}
    results: list[dict[str, Any]] = []

    for i, qa in enumerate(qa_pairs, start=1):
        logger.info("[%d/%d] %s", i, len(qa_pairs), qa["qa_id"])
        result = evaluate_single(qa, page_store, embed_model, page_cache, page_emb_cache)
        results.append(result)

    # Write output
    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.output_dir / f"dense_{timestamp}.json"
    with out_path.open("w") as fh:
        json.dump(
            {
                "model": "dense",
                "embedding_model": args.embedding_model,
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
    print(f"\nDense baseline complete: {len(valid)}/{len(results)} answered, {errors} errors.")
    if valid:
        avg_latency = sum(r["latency_s"] for r in valid) / len(valid)
        avg_sim = sum(r["similarity_score"] or 0.0 for r in valid) / len(valid)
        print(f"Average latency: {avg_latency:.2f}s | Average top-1 similarity: {avg_sim:.4f}")


if __name__ == "__main__":
    main()
