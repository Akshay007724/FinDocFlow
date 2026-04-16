"""FinDocFlow — Extraction Service (port 8002)

Consumes raw_documents from Kafka, runs OCR/table-detection/chart-parsing,
then publishes enriched documents to extracted_documents topic.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from paddleocr_engine import PaddleOCREngine
from detr_table_detector import DETRTableDetector
from chart_parser import ChartParser

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="FinDocFlow Extraction Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "raw_documents")
TOPIC_EXTRACTED = os.getenv("KAFKA_TOPIC_EXTRACTED", "extracted_documents")
GROUP_ID = "extraction-service"

_ocr = PaddleOCREngine()
_table_detector = DETRTableDetector()
_chart_parser = ChartParser()

_executor = ThreadPoolExecutor(max_workers=10)

_consumer: Optional[AIOKafkaConsumer] = None
_producer: Optional[AIOKafkaProducer] = None
_consumer_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def startup():
    global _consumer, _producer, _consumer_task
    _producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await _producer.start()

    _consumer = AIOKafkaConsumer(
        TOPIC_RAW,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset="earliest",
    )
    await _consumer.start()
    _consumer_task = asyncio.create_task(_consume_loop())
    logger.info("Extraction service started")


@app.on_event("shutdown")
async def shutdown():
    if _consumer_task:
        _consumer_task.cancel()
    if _consumer:
        await _consumer.stop()
    if _producer:
        await _producer.stop()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "extraction"}


@app.get("/models")
async def models():
    return {
        "ocr": "paddleocr-en",
        "table_detection": "microsoft/table-transformer-detection",
        "chart_classification": "openai/clip-vit-base-patch32",
    }


async def _consume_loop():
    async for msg in _consumer:
        doc = msg.value
        try:
            enriched = await asyncio.get_event_loop().run_in_executor(
                _executor, _process_document, doc
            )
            await _producer.send_and_wait(
                TOPIC_EXTRACTED,
                value=enriched,
                key=doc.get("doc_id", "").encode(),
            )
            logger.info("Extracted doc_id=%s pages=%d", doc.get("doc_id"), len(doc.get("pages", [])))
        except Exception as exc:
            logger.exception("Extraction failed for doc_id=%s: %s", doc.get("doc_id"), exc)


def _process_page(page: dict) -> dict:
    """Enrich a single page — runs in thread pool worker."""
    page_out = dict(page)
    images = page.get("images", [])
    ocr_results, table_detections, chart_classifications = [], [], []

    for img_b64 in images:
        if page.get("layout_type") == "scanned":
            ocr_result = _ocr.extract(img_b64)
            ocr_results.append(ocr_result)
            if ocr_result["text"] and not page_out.get("text"):
                page_out["text"] = ocr_result["text"]
        tables = _table_detector.detect(img_b64)
        table_detections.extend(tables)
        if page.get("layout_type") in ("chart_heavy", "mixed"):
            chart_classifications.append(_chart_parser.classify(img_b64))

    page_out["ocr_results"] = ocr_results
    page_out["detected_tables"] = table_detections
    page_out["chart_classifications"] = chart_classifications
    return page_out


def _process_document(doc: dict) -> dict:
    """Enrich all pages in parallel using the thread pool."""
    pages = doc.get("pages", [])
    enriched_pages = list(_executor.map(_process_page, pages))
    return {**doc, "pages": enriched_pages, "extraction_complete": True}
