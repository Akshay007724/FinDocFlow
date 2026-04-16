"""FinDocFlow — Reasoning Service (port 8004)"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ollama_client import OllamaClient
from report_generator import ReportGenerator, load_prompts
from think_act_verify import ThinkActVerifyAgent, ReasoningResult

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="FinDocFlow Reasoning Service", version="1.0.0")

_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llava")

_ollama: Optional[OllamaClient] = None
_agent: Optional[ThinkActVerifyAgent] = None
_report_gen: Optional[ReportGenerator] = None


@app.on_event("startup")
async def startup():
    global _ollama, _agent, _report_gen
    _ollama = OllamaClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)
    _agent = ThinkActVerifyAgent(_ollama)
    _report_gen = ReportGenerator(_ollama)
    logger.info("Reasoning service started with model=%s", OLLAMA_MODEL)


@app.get("/health")
async def health():
    ollama_ok = _ollama.health_check() if _ollama else False
    return {"status": "ok", "service": "reasoning", "ollama": ollama_ok, "model": OLLAMA_MODEL}


@app.get("/prompts")
async def get_prompts():
    """Return available report section prompts."""
    return load_prompts()


# ── Shared models ─────────────────────────────────────────────────────────────

class PageIn(BaseModel):
    page_num: int
    text: str
    layout_type: str = "text_heavy"
    has_tables: bool = False
    has_images: bool = False
    images: list[str] = []


# ── Original Q&A endpoint ─────────────────────────────────────────────────────

class ReasonRequest(BaseModel):
    question: str
    pages: list[PageIn]
    entities: list[dict] = []
    graph_context: list[dict] = []
    relevant_page_indices: list[int] = []


class ReasonResponse(BaseModel):
    question: str
    answer: str
    confidence: str
    cited_pages: list[int]
    think: str
    act: str
    verify: str
    iterations: int


@app.post("/reason", response_model=ReasonResponse)
async def reason(req: ReasonRequest):
    if not _agent:
        raise HTTPException(503, "Reasoning agent not ready")
    if not req.pages:
        raise HTTPException(400, "At least one page required")

    pages_dicts = [p.model_dump() for p in req.pages]
    result: ReasoningResult = await asyncio.get_event_loop().run_in_executor(
        None, _agent.reason, req.question, pages_dicts,
        req.entities, req.graph_context, req.relevant_page_indices,
    )
    return ReasonResponse(
        question=result.question, answer=result.answer, confidence=result.confidence,
        cited_pages=result.cited_pages, think=result.think, act=result.act,
        verify=result.verify, iterations=result.iterations,
    )


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


@app.post("/reason/stream")
async def reason_stream(req: ReasonRequest):
    """Server-Sent Events stream of THINK → ACT → VERIFY phases."""
    if not _agent:
        raise HTTPException(503, "Reasoning agent not ready")
    if not req.pages:
        raise HTTPException(400, "At least one page required")
    pages_dicts = [p.model_dump() for p in req.pages]

    async def gen() -> AsyncIterator[bytes]:
        loop = asyncio.get_event_loop()
        try:
            # Run the full reason in a worker, then chunk-emit the phases in order.
            result: ReasoningResult = await loop.run_in_executor(
                None,
                _agent.reason,
                req.question,
                pages_dicts,
                req.entities,
                req.graph_context,
                req.relevant_page_indices,
            )
            # Emit phases as discrete events for the UI to display progress
            yield _sse("think", {"content": result.think})
            await asyncio.sleep(0)
            yield _sse("act", {"content": result.act})
            await asyncio.sleep(0)
            yield _sse("verify", {"content": result.verify})
            await asyncio.sleep(0)
            yield _sse(
                "done",
                {
                    "question": result.question,
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "cited_pages": result.cited_pages,
                    "think": result.think,
                    "act": result.act,
                    "verify": result.verify,
                    "iterations": result.iterations,
                },
            )
        except Exception as exc:
            logger.exception("SSE /reason/stream failed")
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Report generation endpoint ────────────────────────────────────────────────

class ReportRequest(BaseModel):
    pages: list[PageIn]
    section_ids: list[str]
    entities: list[dict] = []


@app.post("/report")
async def generate_report(req: ReportRequest):
    if not _report_gen:
        raise HTTPException(503, "Report generator not ready")
    if not req.pages:
        raise HTTPException(400, "At least one page required")
    if not req.section_ids:
        raise HTTPException(400, "At least one section required")

    pages_dicts = [p.model_dump() for p in req.pages]
    result = await asyncio.get_event_loop().run_in_executor(
        None, _report_gen.generate_report, pages_dicts, req.section_ids, req.entities
    )
    return result


@app.post("/report/stream")
async def generate_report_stream(req: ReportRequest):
    """SSE: section_start → section_done per requested section, up to 4 in parallel."""
    if not _report_gen:
        raise HTTPException(503, "Report generator not ready")
    if not req.pages:
        raise HTTPException(400, "At least one page required")
    if not req.section_ids:
        raise HTTPException(400, "At least one section required")

    pages_dicts = [p.model_dump() for p in req.pages]
    prompts_data = load_prompts()
    section_map = {s["id"]: s for s in prompts_data.get("sections", [])}

    async def gen() -> AsyncIterator[bytes]:
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[dict] = asyncio.Queue()
        remaining = 0

        async def worker(sid: str):
            nonlocal remaining
            section = section_map.get(sid)
            if not section:
                await queue.put({"kind": "error", "message": f"Unknown section: {sid}"})
                remaining -= 1
                return
            await queue.put({"kind": "section_start", "id": sid, "label": section.get("label", sid)})
            try:
                result = await loop.run_in_executor(
                    None,
                    _report_gen.generate_section,
                    sid,
                    section.get("prompt", ""),
                    pages_dicts,
                    req.entities,
                )
                markdown = result.get("content") or ""
                await queue.put({"kind": "section_done", "id": sid, "markdown": markdown})
            except Exception as exc:
                logger.exception("section %s failed", sid)
                await queue.put({"kind": "error", "message": f"{sid}: {exc}"})
            finally:
                remaining -= 1

        # Fan out — concurrency cap handled by executor thread pool
        tasks = []
        for sid in req.section_ids:
            remaining += 1
            tasks.append(asyncio.create_task(worker(sid)))

        try:
            while remaining > 0 or not queue.empty():
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                kind = ev.pop("kind")
                yield _sse(kind, ev)
            yield _sse("report_done", {})
        except Exception as exc:
            logger.exception("SSE /report/stream failed")
            yield _sse("error", {"message": str(exc)})
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Chat endpoint ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    pages: list[PageIn]
    section_id: str = ""
    entities: list[dict] = []


@app.post("/chat")
async def chat(req: ChatRequest):
    if not _report_gen:
        raise HTTPException(503, "Report generator not ready")
    if not req.messages:
        raise HTTPException(400, "At least one message required")

    # Load section prompt if specified
    section_prompt = None
    if req.section_id:
        prompts_data = load_prompts()
        section_map = {s["id"]: s for s in prompts_data["sections"]}
        if req.section_id in section_map:
            section_prompt = section_map[req.section_id]["prompt"]

    pages_dicts = [p.model_dump() for p in req.pages]
    messages_dicts = [m.model_dump() for m in req.messages]

    response = await asyncio.get_event_loop().run_in_executor(
        None, _report_gen.chat, messages_dicts, pages_dicts, section_prompt
    )
    return {"response": response}


# ── Summarize endpoint ────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    pages: list[PageIn]
    focus: str = "key financial metrics and business highlights"


@app.post("/summarize")
async def summarize(req: SummarizeRequest):
    if not _ollama:
        raise HTTPException(503, "Ollama not ready")
    combined_text = "\n\n".join(
        f"[Page {p.page_num}] {p.text[:600]}" for p in req.pages[:15]
    )
    prompt = (
        f"Summarize the following financial document pages focusing on: {req.focus}\n\n"
        f"{combined_text}\n\n"
        "Provide:\n1. Executive Summary (3-5 sentences)\n"
        "2. Key Financial Metrics (bullet list)\n"
        "3. Notable Risk Factors (bullet list)\n"
        "4. Business Highlights (bullet list)"
    )
    summary = await asyncio.get_event_loop().run_in_executor(
        None, _ollama.generate, prompt, None, 0.2
    )
    return {"summary": summary, "pages_analyzed": len(req.pages)}
