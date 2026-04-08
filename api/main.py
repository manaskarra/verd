"""FastAPI wrapper for the verd business debate engine.

Exposes the debate engine as HTTP endpoints with SSE streaming for
real-time status updates during debate execution.
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from verd.engine import run_debate
from verd.templates import build_debate_input, get_templates_metadata


_active_debates: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _active_debates.clear()


app = FastAPI(
    title="Verd Business API",
    description="AI advisory panel for business decisions",
    version="0.1.0",
    lifespan=lifespan,
)

allowed_origins = os.getenv("VERD_CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class DebateRequest(BaseModel):
    template: str = Field(..., description="Template ID (location, pricing, launch, hire, partnership, freeform)")
    fields: dict[str, str] = Field(..., description="Template field values")


class DebateResponse(BaseModel):
    id: str
    status: str
    result: dict | None = None


@app.get("/api/templates")
async def list_templates():
    return get_templates_metadata()


@app.post("/api/debate", response_model=DebateResponse)
async def start_debate(req: DebateRequest):
    try:
        content, claim = build_debate_input(req.template, req.fields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    debate_id = uuid.uuid4().hex[:12]
    status_queue: asyncio.Queue[str] = asyncio.Queue()

    _active_debates[debate_id] = {
        "status": "running",
        "queue": status_queue,
        "result": None,
    }

    async def _run():
        try:
            async def stream_event(payload: dict):
                await status_queue.put(json.dumps(payload, default=str))

            result = await run_debate(
                content, claim, "business",
                stream_callback=stream_event,
            )
            _active_debates[debate_id]["result"] = result
            _active_debates[debate_id]["status"] = "completed"
            await status_queue.put(json.dumps({"type": "complete", "result": result}, default=str))
        except Exception as e:
            _active_debates[debate_id]["status"] = "failed"
            await status_queue.put(json.dumps({"type": "error", "message": str(e)}))

    asyncio.create_task(_run())

    return DebateResponse(id=debate_id, status="running")


@app.get("/api/debate/stream/{debate_id}")
async def stream_debate(debate_id: str):
    if debate_id not in _active_debates:
        raise HTTPException(status_code=404, detail="Debate not found")

    queue = _active_debates[debate_id]["queue"]

    async def event_stream():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=300)
                yield f"data: {data}\n\n"
                parsed = json.loads(data)
                if parsed.get("type") in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/debate/{debate_id}")
async def get_debate(debate_id: str):
    if debate_id not in _active_debates:
        raise HTTPException(status_code=404, detail="Debate not found")

    entry = _active_debates[debate_id]
    return DebateResponse(
        id=debate_id,
        status=entry["status"],
        result=entry.get("result"),
    )
