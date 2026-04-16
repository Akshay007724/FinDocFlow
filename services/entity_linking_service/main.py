"""FinDocFlow — Entity Linking Service (port 8003)

Consumes extracted_documents from Kafka, runs NER + embedding,
writes entities/relationships to Neo4j, publishes to linked_documents.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from neo4j_client import Neo4jClient
from entity_linker import EntityLinker

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="FinDocFlow Entity Linking Service", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC_EXTRACTED = os.getenv("KAFKA_TOPIC_EXTRACTED", "extracted_documents")
TOPIC_LINKED = os.getenv("KAFKA_TOPIC_LINKED", "linked_documents")
GROUP_ID = "entity-linking-service"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "findocflow")

_neo4j: Optional[Neo4jClient] = None
_linker: Optional[EntityLinker] = None
_consumer: Optional[AIOKafkaConsumer] = None
_producer: Optional[AIOKafkaProducer] = None
_consumer_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def startup():
    global _neo4j, _linker, _consumer, _producer, _consumer_task
    _neo4j = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    _linker = EntityLinker()

    _producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    await _producer.start()

    _consumer = AIOKafkaConsumer(
        TOPIC_EXTRACTED,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset="earliest",
    )
    await _consumer.start()
    _consumer_task = asyncio.create_task(_consume_loop())
    logger.info("Entity linking service started")


@app.on_event("shutdown")
async def shutdown():
    if _consumer_task:
        _consumer_task.cancel()
    if _consumer:
        await _consumer.stop()
    if _producer:
        await _producer.stop()
    if _neo4j:
        _neo4j.close()


@app.get("/health")
async def health():
    neo4j_ok = _neo4j.health_check() if _neo4j else False
    return {"status": "ok", "service": "entity_linking", "neo4j": neo4j_ok}


class GraphQueryRequest(BaseModel):
    company: str


@app.post("/graph/company-metrics")
async def company_metrics(req: GraphQueryRequest):
    if not _neo4j:
        raise HTTPException(503, "Neo4j not connected")
    return {"metrics": _neo4j.get_company_metrics(req.company)}


class SimilarPagesRequest(BaseModel):
    query: str
    page_texts: list[str]
    top_k: int = 5


@app.post("/embed/similar-pages")
async def similar_pages(req: SimilarPagesRequest):
    if not _linker:
        raise HTTPException(503, "Entity linker not ready")
    indices = _linker.find_similar_pages(req.query, req.page_texts, req.top_k)
    return {"indices": indices}


async def _consume_loop():
    async for msg in _consumer:
        doc = msg.value
        try:
            linked = await asyncio.get_event_loop().run_in_executor(
                None, _process_document, doc
            )
            await _producer.send_and_wait(
                TOPIC_LINKED,
                value=linked,
                key=doc.get("doc_id", "").encode(),
            )
            logger.info("Linked doc_id=%s entities=%d", doc.get("doc_id"), linked.get("entity_count", 0))
        except Exception as exc:
            logger.exception("Entity linking failed for doc_id=%s: %s", doc.get("doc_id"), exc)


def _process_document(doc: dict) -> dict:
    doc_id = doc.get("doc_id", "")
    company = doc.get("company") or _infer_company(doc)
    filing_year = doc.get("filing_year")

    all_entities: list[dict] = []
    page_embeddings: list[list[float]] = []

    for page in doc.get("pages", []):
        text = page.get("text", "")
        page_num = page.get("page_num", 0)

        entities = _linker.extract_entities(text, doc_id, page_num)
        all_entities.extend(entities)

        # Write entities to Neo4j
        for ent in entities:
            if ent["type"] == "company":
                _neo4j.upsert_company(ent["text"])
            elif ent["type"] == "metric" and company:
                _neo4j.upsert_metric(ent["text"], unit=None)
                if ent["period"]:
                    _neo4j.upsert_time_period(ent["period"])
                    if ent["value"]:
                        _neo4j.link_company_metric(
                            company_name=company,
                            metric_name=ent["text"],
                            period=ent["period"],
                            value=ent["value"],
                            doc_id=doc_id,
                            page_num=page_num,
                        )
            elif ent["type"] == "period":
                _neo4j.upsert_time_period(ent["text"])

        # Semantic embedding
        emb = _linker.embed_text(text[:512])
        page_embeddings.append(emb)

    return {
        **doc,
        "entities": all_entities,
        "page_embeddings": page_embeddings,
        "entity_count": len(all_entities),
        "linking_complete": True,
    }


def _infer_company(doc: dict) -> str | None:
    """Try to infer company name from filename."""
    filename = doc.get("filename", "")
    # e.g. "AAPL_10K_2023.pdf" → "AAPL"
    parts = filename.replace("-", "_").split("_")
    if parts and len(parts[0]) <= 6:
        return parts[0].upper()
    return None
