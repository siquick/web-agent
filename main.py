from __future__ import annotations

import json
import logging
import os
import time
from queue import SimpleQueue
from threading import Thread
from typing import Any, Dict, Iterable, List, Tuple
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from web_agent import AgentResult, ToolUseAgent, build_agent_metadata
from web_agent.ai.llm import (
    DEFAULT_CHAT_MODEL,
    is_supported_chat_model,
    openai_model_payload,
    supported_model_ids,
)
from web_agent.ai.utils import content_to_text
from web_agent.api.schemas import ChatMessage, ChatRequest, QueryRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Web Agent API",
    description="FastAPI service exposing agentic tooling over OpenAI-compatible providers.",
    version="0.1.0",
)

default_origins = "http://127.0.0.1:5173,http://localhost:5173"
cors_origins = [
    origin.strip()
    for origin in os.environ.get("WEB_AGENT_CORS_ORIGINS", default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = ToolUseAgent()


def _build_response(
    result: AgentResult,
    *,
    model: str,
    object_name: str,
) -> Dict[str, Any]:
    created = int(time.time())
    message_metadata = build_agent_metadata(
        result.refined_query,
        result.tool_calls,
        result.reflections,
        provider=result.provider,
    )
    choice = {
        "index": 0,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": result.answer}],
            "metadata": message_metadata,
        },
        "finish_reason": "stop",
    }

    return {
        "id": f"{object_name}-{uuid4()}",
        "object": object_name,
        "created": created,
        "model": model,
        "choices": [choice],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "system_fingerprint": None,
    }


def _extract_question_and_history(
    messages: List[ChatMessage],
) -> Tuple[str, List[Dict[str, Any]]]:
    if not messages:
        raise HTTPException(status_code=400, detail="At least one message is required.")

    last_user_index = None
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "user":
            last_user_index = index
            break

    if last_user_index is None:
        raise HTTPException(status_code=400, detail="Provide at least one user message.")

    question = content_to_text(messages[last_user_index].content).strip()
    if not question:
        raise HTTPException(status_code=400, detail="The final user message cannot be empty.")

    history = [
        messages[index].model_dump()
        for index in range(last_user_index)
    ]
    return question, history


def _require_supported_model(model: str) -> None:
    if is_supported_chat_model(model):
        return
    supported = ", ".join(supported_model_ids())
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported model '{model}'. Choose one of: {supported}.",
    )


def _encode_sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _agent_event_stream(
    *,
    question: str,
    history: List[Dict[str, Any]],
    model: str,
) -> Iterable[str]:
    queue: SimpleQueue[Any] = SimpleQueue()
    sentinel: object = object()

    def handle_event(event: Dict[str, Any]) -> None:
        queue.put(event)

    def run_agent() -> None:
        try:
            result = agent.run(
                question=question,
                chat_history=history,
                model=model,
                event_handler=handle_event,
            )
            response_payload = _build_response(result, model=model, object_name="chat.completion")
            queue.put({"type": "final_response", "response": response_payload})
        except Exception as exc:  # pragma: no cover - surfaces runtime issues
            logger.exception("Agent execution failed during streaming: %s", exc)
            queue.put({"type": "error", "message": "Agent failed to generate a response."})
        finally:
            queue.put(sentinel)

    Thread(target=run_agent, daemon=True).start()

    while True:
        event = queue.get()
        if event is sentinel:
            break
        yield _encode_sse(event)
    yield _encode_sse({"type": "done"})


def _run_agent(
    *,
    question: str,
    history: List[Dict[str, Any]],
    model: str,
) -> AgentResult:
    try:
        return agent.run(question=question, chat_history=history, model=model)
    except Exception as exc:  # pragma: no cover - surfaces LLM/tool issues
        logger.exception("Agent execution failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent failed to generate a response.") from exc


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
def list_models() -> Dict[str, Any]:
    return openai_model_payload()


@app.post("/v1/query")
def query_endpoint(payload: QueryRequest):
    if payload.stream:
        raise HTTPException(status_code=400, detail="Streaming is not supported yet.")

    _require_supported_model(payload.model)

    if isinstance(payload.input, str):
        question = payload.input.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Input cannot be empty.")
        history: List[Dict[str, Any]] = []
    else:
        question, history = _extract_question_and_history(payload.input)

    result = _run_agent(question=question, history=history, model=payload.model)
    response_payload = _build_response(result, model=payload.model, object_name="response")
    return JSONResponse(content=response_payload)


@app.post("/v1/chat")
def chat_endpoint(payload: ChatRequest):
    if payload.stream:
        raise HTTPException(status_code=400, detail="Streaming is not supported yet.")

    _require_supported_model(payload.model)

    question, history = _extract_question_and_history(payload.messages)

    result = _run_agent(question=question, history=history, model=payload.model)
    response_payload = _build_response(result, model=payload.model, object_name="chat.completion")
    return JSONResponse(content=response_payload)


@app.post("/v1/chat/completions")
def chat_completions_endpoint(payload: ChatRequest):
    _require_supported_model(payload.model)
    question, history = _extract_question_and_history(payload.messages)

    if payload.stream:
        event_iterable = _agent_event_stream(question=question, history=history, model=payload.model)
        return StreamingResponse(event_iterable, media_type="text/event-stream")

    result = _run_agent(question=question, history=history, model=payload.model)
    response_payload = _build_response(result, model=payload.model, object_name="chat.completion")
    return JSONResponse(content=response_payload)
