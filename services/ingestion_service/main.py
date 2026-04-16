"""FinDocFlow — Ingestion Service (port 8001)"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import redis.asyncio as aioredis
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from kafka_producer import DocumentProducer
from parsers.pdf_parser import PDFParser
from parsers.html_parser import HTMLParser
from parsers.xbrl_parser import XBRLParser
from parsers.excel_parser import ExcelParser

import os

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="FinDocFlow Ingestion Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "raw_documents")

_redis: Optional[aioredis.Redis] = None
_producer: Optional[DocumentProducer] = None
_executor = ThreadPoolExecutor(max_workers=10)

SUPPORTED_FORMATS = {".pdf", ".html", ".htm", ".xbrl", ".xml", ".xlsx", ".xls"}


class BatchIngestRequest(BaseModel):
    urls: list[HttpUrl]
    company: Optional[str] = None
    filing_year: Optional[int] = None


class JobStatus(BaseModel):
    job_id: str
    status: str          # pending | processing | done | failed
    progress: int = 0    # 0-100
    message: str = ""
    doc_ids: list[str] = []


@app.on_event("startup")
async def startup():
    global _redis, _producer
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    _producer = DocumentProducer(KAFKA_BOOTSTRAP, TOPIC_RAW)
    await _producer.start()
    logger.info("Ingestion service started")


@app.on_event("shutdown")
async def shutdown():
    if _producer:
        await _producer.stop()
    if _redis:
        await _redis.close()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ingestion"}


@app.post("/ingest/upload", response_model=JobStatus)
async def ingest_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format {suffix}. Supported: {SUPPORTED_FORMATS}")

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    raw_bytes = await file.read()

    await _set_job_status(job_id, "pending", 0, f"Received {file.filename}")
    background_tasks.add_task(
        _process_upload, job_id, doc_id, file.filename, suffix, raw_bytes
    )
    return JobStatus(job_id=job_id, status="pending", doc_ids=[doc_id])


@app.post("/ingest/batch", response_model=JobStatus)
async def ingest_batch(req: BatchIngestRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    await _set_job_status(job_id, "pending", 0, f"Queued {len(req.urls)} URLs")
    background_tasks.add_task(_process_batch, job_id, req)
    return JobStatus(job_id=job_id, status="pending")


@app.get("/ingest/docs")
async def list_docs():
    entries = await _redis.lrange("ingested_docs", 0, 49)
    stale = []
    docs = []
    for entry in entries:
        parts = entry.split("|", 1)
        doc_id = parts[0]
        if not await _redis.exists(f"pages:{doc_id}"):
            stale.append(entry)
            continue
        docs.append({"doc_id": doc_id, "filename": parts[1] if len(parts) > 1 else doc_id})
    for entry in stale:
        await _redis.lrem("ingested_docs", 0, entry)
    return {"docs": docs}


@app.get("/ingest/pages/{doc_id}")
async def get_pages(doc_id: str):
    raw = await _redis.get(f"pages:{doc_id}")
    if not raw:
        raise HTTPException(404, "Pages not found — doc may have expired or not yet ingested")
    return {"doc_id": doc_id, "pages": json.loads(raw)}


@app.get("/ingest/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    data = await _redis.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(404, "Job not found")
    return JobStatus(
        job_id=job_id,
        status=data.get("status", "unknown"),
        progress=int(data.get("progress", 0)),
        message=data.get("message", ""),
        doc_ids=data.get("doc_ids", "").split(",") if data.get("doc_ids") else [],
    )


# ── Background tasks ──────────────────────────────────────────────────────

async def _process_upload(job_id: str, doc_id: str, filename: str, suffix: str, raw: bytes):
    try:
        await _set_job_status(job_id, "processing", 10, "Parsing document")
        pages = await asyncio.get_event_loop().run_in_executor(
            _executor, _parse_document, suffix, raw, filename
        )
        await _set_job_status(job_id, "processing", 60, f"Parsed {len(pages)} pages")

        message = {
            "doc_id": doc_id,
            "filename": filename,
            "format": suffix.lstrip("."),
            "pages": [p.model_dump() for p in pages],
            "total_pages": len(pages),
        }
        await _producer.send(message, key=doc_id)
        # Store page text + images in Redis for frontend retrieval
        # Images capped at 30 pages to limit memory usage
        pages_for_cache = []
        for i, p in enumerate(pages):
            d = p.model_dump()
            if i >= 30:
                d["images"] = []
            pages_for_cache.append(d)
        await _redis.set(f"pages:{doc_id}", json.dumps(pages_for_cache), ex=86400)
        await _redis.lpush("ingested_docs", f"{doc_id}|{filename}")
        await _redis.ltrim("ingested_docs", 0, 49)  # keep last 50
        await _set_job_status(job_id, "done", 100, f"Ingested {len(pages)} pages", [doc_id])
        logger.info("doc_id=%s pages=%d sent to Kafka", doc_id, len(pages))
    except Exception as exc:
        logger.exception("Upload failed for job %s", job_id)
        await _set_job_status(job_id, "failed", 0, str(exc))


async def _process_batch(job_id: str, req: BatchIngestRequest):
    import httpx
    doc_ids = []
    total = len(req.urls)
    async with httpx.AsyncClient(timeout=30) as client:
        for i, url in enumerate(req.urls):
            try:
                resp = await client.get(str(url))
                resp.raise_for_status()
                raw = resp.content
                filename = str(url).split("/")[-1] or "document.html"
                suffix = Path(filename).suffix.lower() or ".html"
                doc_id = str(uuid.uuid4())
                pages = await asyncio.get_event_loop().run_in_executor(
                    None, _parse_document, suffix, raw, filename
                )
                message = {
                    "doc_id": doc_id,
                    "filename": filename,
                    "format": suffix.lstrip("."),
                    "pages": [p.model_dump() for p in pages],
                    "total_pages": len(pages),
                    "source_url": str(url),
                    "company": req.company,
                    "filing_year": req.filing_year,
                }
                await _producer.send(message, key=doc_id)
                doc_ids.append(doc_id)
                progress = int((i + 1) / total * 90)
                await _set_job_status(job_id, "processing", progress, f"{i+1}/{total} ingested")
            except Exception as exc:
                logger.warning("Failed URL %s: %s", url, exc)

    await _set_job_status(job_id, "done", 100, f"Batch complete: {len(doc_ids)}/{total}", doc_ids)


def _parse_document(suffix: str, raw: bytes, filename: str):
    """Synchronous parse — runs in executor."""
    if suffix == ".pdf":
        return PDFParser().parse(raw)
    elif suffix in (".html", ".htm"):
        return HTMLParser().parse(raw, filename)
    elif suffix in (".xbrl", ".xml"):
        return XBRLParser().parse(raw)
    elif suffix in (".xlsx", ".xls"):
        return ExcelParser().parse(raw)
    raise ValueError(f"No parser for {suffix}")


async def _set_job_status(job_id: str, status: str, progress: int, message: str, doc_ids: list = None):
    data = {"status": status, "progress": progress, "message": message}
    if doc_ids:
        data["doc_ids"] = ",".join(doc_ids)
    await _redis.hset(f"job:{job_id}", mapping=data)
    await _redis.expire(f"job:{job_id}", 86400)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", 8001)))
