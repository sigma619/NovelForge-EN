"""Genspark AI (browser-backed / TLS impersonation route) API endpoints.

Provides:
- OpenAI-compatible chat completion endpoint (/api/genspark/v1/chat/completions)
- Direct prediction endpoint (/api/genspark/predict)
- Model listing endpoint (/api/genspark/models)
- Status and account pool endpoint (/api/genspark/status, /api/genspark/accounts)
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.schemas.response import ApiResponse
from app.services.ai.providers import genspark_auth


router = APIRouter()


class ChatMessagePayload(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str = Field(default=genspark_auth.DEFAULT_MODEL, description="Model identifier, e.g. gpt-5.6-sol or claude-opus-4-6")
    messages: List[ChatMessagePayload]
    temperature: Optional[float] = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=32768, ge=1)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stream: bool = False
    timeout: Optional[int] = None
    connect_timeout: Optional[float] = None
    proxy: Optional[str] = None
    reasoning_enabled: Optional[bool] = None
    reasoning_effort: Optional[str] = None
    enable_search: bool = False


class DirectPredictRequest(BaseModel):
    model: str = Field(default=genspark_auth.DEFAULT_MODEL)
    prompt: str
    system: Optional[str] = None
    temperature: Optional[float] = 0.3
    max_tokens: Optional[int] = 32768
    top_p: Optional[float] = None
    stream: bool = False
    timeout: Optional[int] = None
    proxy: Optional[str] = None
    reasoning_enabled: Optional[bool] = None
    reasoning_effort: Optional[str] = None
    enable_search: bool = False


@router.get("/models", response_model=ApiResponse[List[Dict[str, Any]]], summary="List available Genspark preset models")
def get_genspark_models():
    """Return a list of curated models available via Genspark AI."""
    models_data = [
        {"id": m, "name": m, "publisher": "genspark", "provider": "genspark"}
        for m in genspark_auth.GENSPARK_PRESET_MODELS
    ]
    return ApiResponse(data=models_data)


@router.get("/status", response_model=ApiResponse[Dict[str, Any]], summary="Genspark AI service and account pool status")
def get_genspark_status():
    """Check Genspark configuration, active account, and cookie pool availability."""
    pool = genspark_auth.get_account_pool()
    active_mgr = pool.get_active_account()
    accounts_info = pool.list_accounts()
    return ApiResponse(
        data={
            "status": "ready",
            "provider": "genspark",
            "default_model": genspark_auth.DEFAULT_MODEL,
            "active_account": active_mgr.name if active_mgr else "none",
            "active_email": (active_mgr.email or active_mgr.name) if active_mgr else "none",
            "accounts_pool": accounts_info,
            "models_count": len(genspark_auth.GENSPARK_PRESET_MODELS),
            "preset_models": genspark_auth.GENSPARK_PRESET_MODELS,
        }
    )


@router.get("/accounts", response_model=ApiResponse[List[Dict[str, Any]]], summary="List Genspark account pool")
def list_genspark_accounts():
    """List all accounts in the Genspark rotation pool."""
    pool = genspark_auth.get_account_pool()
    return ApiResponse(data=pool.list_accounts())


@router.post("/predict", summary="Direct prompt prediction via Genspark AI")
async def direct_predict(payload: DirectPredictRequest):
    """Simple prediction endpoint taking a prompt and optional system instructions."""
    messages = []
    if payload.system:
        messages.append({"role": "system", "content": payload.system})
    messages.append({"role": "user", "content": payload.prompt})

    req = ChatCompletionRequest(
        model=payload.model,
        messages=[ChatMessagePayload(**m) for m in messages],
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        top_p=payload.top_p,
        stream=payload.stream,
        timeout=payload.timeout,
        proxy=payload.proxy,
        reasoning_enabled=payload.reasoning_enabled,
        reasoning_effort=payload.reasoning_effort,
        enable_search=payload.enable_search,
    )
    return await chat_completions(req)


@router.post("/v1/chat/completions", summary="OpenAI-compatible Chat Completion endpoint for Genspark AI")
async def chat_completions(payload: ChatCompletionRequest):
    """OpenAI-compatible chat completions route supporting both JSON and SSE streaming."""
    dict_messages = [{"role": m.role, "content": m.content} for m in payload.messages]
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    if not payload.stream:
        try:
            result = await asyncio.to_thread(
                genspark_auth.send_chat_completion,
                messages=dict_messages,
                model=payload.model,
                temperature=payload.temperature if payload.temperature is not None else 0.3,
                max_tokens=payload.max_tokens if payload.max_tokens is not None else 32768,
                top_p=payload.top_p,
                frequency_penalty=payload.frequency_penalty,
                presence_penalty=payload.presence_penalty,
                timeout=payload.timeout,
                connect_timeout=payload.connect_timeout,
                proxy=payload.proxy,
                reasoning_enabled=payload.reasoning_enabled,
                reasoning_effort=payload.reasoning_effort,
                enable_search=payload.enable_search,
                stream=False,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Genspark completion failed: {exc}")

        content = result.get("content") or ""
        reasoning = result.get("reasoning_content")
        finish_reason = result.get("finish_reason") or "stop"
        usage = result.get("usage") or {
            "prompt_tokens": 0,
            "completion_tokens": len(content) // 4,
            "total_tokens": len(content) // 4,
        }

        msg_dict: Dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning:
            msg_dict["reasoning_content"] = reasoning

        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": payload.model,
            "choices": [
                {
                    "index": 0,
                    "message": msg_dict,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage,
        }

    # Streaming mode via SSE
    async def sse_generator():
        chunk_queue = asyncio.Queue()
        done_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _on_chunk(delta_text: str, delta_reasoning: Optional[str] = None):
            loop.call_soon_threadsafe(chunk_queue.put_nowait, (delta_text, delta_reasoning))

        def _run_stream():
            try:
                genspark_auth.send_chat_completion(
                    messages=dict_messages,
                    model=payload.model,
                    temperature=payload.temperature if payload.temperature is not None else 0.3,
                    max_tokens=payload.max_tokens if payload.max_tokens is not None else 32768,
                    top_p=payload.top_p,
                    frequency_penalty=payload.frequency_penalty,
                    presence_penalty=payload.presence_penalty,
                    timeout=payload.timeout,
                    connect_timeout=payload.connect_timeout,
                    proxy=payload.proxy,
                    reasoning_enabled=payload.reasoning_enabled,
                    reasoning_effort=payload.reasoning_effort,
                    enable_search=payload.enable_search,
                    stream=True,
                    chunk_callback=_on_chunk,
                )
            except Exception as e:
                loop.call_soon_threadsafe(chunk_queue.put_nowait, ("__ERROR__", str(e)))
            finally:
                loop.call_soon_threadsafe(done_event.set)

        worker = threading.Thread(target=_run_stream, daemon=True)
        worker.start()

        # Send initial role chunk
        init_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": payload.model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(init_chunk, ensure_ascii=False)}\n\n"

        while True:
            if chunk_queue.empty() and done_event.is_set():
                break

            try:
                chunk_data = await asyncio.wait_for(chunk_queue.get(), timeout=0.1)
                text, reasoning = chunk_data
                if text == "__ERROR__":
                    err_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": payload.model,
                        "choices": [{"index": 0, "delta": {"content": f"\n[Error: {reasoning}]"}, "finish_reason": "error"}],
                    }
                    yield f"data: {json.dumps(err_chunk, ensure_ascii=False)}\n\n"
                    break

                delta_payload: Dict[str, Any] = {}
                if text:
                    delta_payload["content"] = text
                if reasoning:
                    delta_payload["reasoning_content"] = reasoning

                if delta_payload:
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": payload.model,
                        "choices": [{"index": 0, "delta": delta_payload, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                continue

        # Final terminal chunk
        final_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": payload.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
