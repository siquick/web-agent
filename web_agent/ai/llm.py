from web_agent.ai.prompts import (
    answer_generation_prompt_template,
    conversation_summarizer_prompt_template,
    context_relevance_judgment_template,
    query_rewrite_prompt_template,
)
import logging
from dotenv import load_dotenv
import os
from functools import lru_cache
from openai import OpenAI
from typing import Any, Dict, Optional, Sequence

from web_agent.ai.token_utils import count_tokens, trim_to_tokens

load_dotenv()

HF_ROUTER_BASE_URL = "https://router.huggingface.co/v1"
HF_ROUTER_MODEL = os.environ.get("HF_ROUTER_MODEL", "Qwen/Qwen3-32B:cerebras")
DEFAULT_CHAT_MODEL = HF_ROUTER_MODEL

MAX_CONTEXT_TOKENS = 65536
SUMMARY_TOKEN_RATIO = 0.3
SUMMARY_TOKEN_LIMIT = int(MAX_CONTEXT_TOKENS * SUMMARY_TOKEN_RATIO)


@lru_cache
def get_huggingface_client() -> OpenAI:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN must be set to use the Hugging Face router.")
    return OpenAI(base_url=HF_ROUTER_BASE_URL, api_key=token)


def is_supported_chat_model(model: str) -> bool:
    try:
        canonical_chat_model(model)
        return True
    except ValueError:
        return False


def canonical_chat_model(model: Optional[str]) -> str:
    target = (model or DEFAULT_CHAT_MODEL).strip()
    if not target:
        raise ValueError("Model name cannot be empty.")
    return target


def llm_call(
    system_prompt: str,
    query: str,
    model: str = DEFAULT_CHAT_MODEL,
    stream: bool = False,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]
    response = llm_chat(
        messages,
        model=model,
        stream=stream,
        temperature=0.1,
        top_p=0.95,
        max_tokens=1024,
    )

    if stream:
        assembled = ""
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                assembled += delta.content
        return assembled

    return response.choices[0].message.content


def llm_chat(
    messages: Sequence[Dict[str, Any]],
    *,
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    model: str = DEFAULT_CHAT_MODEL,
    stream: bool = False,
    temperature: float = 0.1,
    top_p: float = 0.95,
    max_tokens: int = 2000,
) -> Any:
    try:
        hf_model = canonical_chat_model(model)
        logging.info(
            "Calling chat completion with model: %s (stream=%s, tools=%s)",
            hf_model,
            stream,
            bool(tools),
        )

        hf_client = get_huggingface_client()
        payload: Dict[str, Any] = {
            "model": hf_model,
            "messages": list(messages),
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = list(tools)

        if stream:
            payload["stream"] = True
            return hf_client.chat.completions.create(**payload)

        return hf_client.chat.completions.create(**payload)
    except Exception as e:
        logging.error(f"Error calling chat completion: {e}")
        raise


def query_rewrite(query: str) -> str:
    system_prompt = query_rewrite_prompt_template()
    return llm_call(system_prompt, query, model=DEFAULT_CHAT_MODEL)


def context_relevance_judgment(context: str, question: str) -> str:
    system_prompt = context_relevance_judgment_template(context, question)
    return llm_call(system_prompt, question, model=DEFAULT_CHAT_MODEL)


def answer_generation(context: str, question: str) -> str:
    system_prompt = answer_generation_prompt_template(context, question)
    return llm_call(system_prompt, question, model=DEFAULT_CHAT_MODEL, stream=False)


def conversation_summary_update(
    existing_summary: Optional[str],
    new_chunk: str,
    *,
    max_tokens: int = SUMMARY_TOKEN_LIMIT,
) -> str:
    has_existing = bool(existing_summary and existing_summary.strip())
    system_prompt = conversation_summarizer_prompt_template(
        has_existing_summary=has_existing, max_tokens=max_tokens
    )

    if has_existing:
        query = (
            "Existing summary:\n"
            f"{existing_summary.strip()}\n\n"
            "New conversation segment:\n"
            f"{new_chunk.strip()}"
        )
    else:
        query = new_chunk.strip()

    updated = llm_call(
        system_prompt=system_prompt,
        query=query,
        model=DEFAULT_CHAT_MODEL,
        stream=False,
    ).strip()

    if count_tokens(updated) > max_tokens:
        updated = trim_to_tokens(updated, max_tokens - 10).rstrip()
        if count_tokens(updated) >= max_tokens:
            updated = trim_to_tokens(updated, max_tokens - 1).rstrip()

    return updated
