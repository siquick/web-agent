from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from lib.agent import AgentResult, ToolUseAgent
from lib.ai.utils import content_to_text
from lib.api.schemas import ChatMessage, ChatRequest, QueryRequest
from lib.ai.llm import DEFAULT_CHAT_MODEL, is_supported_chat_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Web Agent API",
    description="FastAPI service exposing agentic tooling over the Qwen 3 32B model via Hugging Face Inference.",
    version="0.1.0",
)

agent = ToolUseAgent()


def _format_tool_metadata(result: AgentResult) -> Dict[str, Any]:
    tool_meta = [
        {
            "name": call.name,
            "arguments": call.arguments,
            "output_preview": call.output_preview,
        }
        for call in result.tool_calls
    ]
    reflection_meta = [
        {
            "requires_more_context": reflection.requires_more_context,
            "reason": reflection.reason,
            "follow_up_instruction": reflection.follow_up_instruction,
            "suggested_query": reflection.suggested_query,
        }
        for reflection in result.reflections
    ]
    return {
        "refined_query": result.refined_query,
        "tool_calls": tool_meta,
        "reflections": reflection_meta,
    }


def _build_response(
    result: AgentResult,
    *,
    model: str,
    object_name: str,
) -> Dict[str, Any]:
    created = int(time.time())
    message_metadata = _format_tool_metadata(result)
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


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/query")
def query_endpoint(payload: QueryRequest):
    if payload.stream:
        raise HTTPException(status_code=400, detail="Streaming is not supported yet.")

    if not is_supported_chat_model(payload.model):
        raise HTTPException(
            status_code=400,
            detail=f"This service currently supports only the {DEFAULT_CHAT_MODEL} model.",
        )

    if isinstance(payload.input, str):
        question = payload.input.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Input cannot be empty.")
        history: List[Dict[str, Any]] = []
    else:
        question, history = _extract_question_and_history(payload.input)

    try:
        result = agent.run(question=question, chat_history=history)
    except Exception as exc:  # pragma: no cover - surfaces LLM/tool issues
        logger.exception("Agent execution failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent failed to generate a response.") from exc

    response_payload = _build_response(result, model=payload.model, object_name="response")
    return JSONResponse(content=response_payload)


@app.post("/v1/chat")
def chat_endpoint(payload: ChatRequest):
    if payload.stream:
        raise HTTPException(status_code=400, detail="Streaming is not supported yet.")

    if not is_supported_chat_model(payload.model):
        raise HTTPException(
            status_code=400,
            detail=f"This service currently supports only the {DEFAULT_CHAT_MODEL} model.",
        )

    question, history = _extract_question_and_history(payload.messages)

    try:
        result = agent.run(question=question, chat_history=history)
    except Exception as exc:  # pragma: no cover - surfaces LLM/tool issues
        logger.exception("Agent execution failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent failed to generate a response.") from exc

    response_payload = _build_response(result, model=payload.model, object_name="chat.completion")
    return JSONResponse(content=response_payload)
