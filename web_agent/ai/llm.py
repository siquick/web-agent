from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from openai import OpenAI

from web_agent.ai.prompts import (
    answer_generation_prompt_template,
    conversation_summarizer_prompt_template,
    context_relevance_judgment_template,
    query_rewrite_prompt_template,
)
from web_agent.ai.token_utils import count_tokens, trim_to_tokens

load_dotenv()

logger = logging.getLogger(__name__)


def _as_tuple(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item)
    if isinstance(value, str):
        trimmed = value.strip()
        return (trimmed,) if trimmed else ()
    return ()


def _load_json_env(var_name: str) -> Optional[Any]:
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Environment variable {var_name} must contain valid JSON."
        ) from exc


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    label: str
    base_url: str
    api_key: Optional[str] = None
    api_key_envs: Tuple[str, ...] = field(default_factory=tuple)
    supports_streaming: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def resolved_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        for env_name in self.api_key_envs:
            value = os.environ.get(env_name)
            if value:
                return value
        return None


@dataclass(frozen=True)
class ModelConfig:
    id: str
    provider_id: str
    model_name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    supports_streaming: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def resolved_display_name(self) -> str:
        return self.display_name or self.model_name

    def resolved_description(self) -> str:
        return self.description or ""

    def streaming_enabled(self, provider: ProviderConfig) -> bool:
        if self.supports_streaming is None:
            return provider.supports_streaming
        return self.supports_streaming


DEFAULT_PROVIDER_CONFIGS: List[Dict[str, Any]] = [
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_envs": ["OPENROUTER_API_KEY", "OPENAI_API_KEY"],
        "metadata": {"docs": "https://openrouter.ai/docs"},
    },
    {
        "id": "huggingface",
        "label": "Hugging Face Inference Router",
        "base_url": "https://router.huggingface.co/v1",
        "api_key_envs": ["HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN"],
        "metadata": {"docs": "https://huggingface.co/docs/api-inference/"},
    },
]

DEFAULT_MODEL_CONFIGS: List[Dict[str, Any]] = [
    {
        "id": "openrouter/qwen-3-32b",
        "provider_id": "openrouter",
        "model_name": "qwen/qwen3-32b",
        "display_name": "Qwen 3 32B (OpenRouter)",
        "description": "General-purpose 32B model served via OpenRouter.",
    },
    {
        "id": "huggingface/qwen3-32b-groq",
        "provider_id": "huggingface",
        "model_name": "Qwen/Qwen3-32B:groq",
        "display_name": "Qwen 3 32B (HF · Groq)",
        "description": "Qwen 3 32B hosted on Hugging Face via the Groq backend.",
    },
    {
        "id": "huggingface/qwen3-32b-cerebras",
        "provider_id": "huggingface",
        "model_name": "Qwen/Qwen3-32B:cerebras",
        "display_name": "Qwen 3 32B (HF · Cerebras)",
        "description": "Qwen 3 32B hosted on Hugging Face via the Cerebras backend.",
    },
]


def _load_provider_configs() -> Dict[str, ProviderConfig]:
    data = _load_json_env("WEB_AGENT_PROVIDERS") or DEFAULT_PROVIDER_CONFIGS
    providers: Dict[str, ProviderConfig] = {}
    for entry in data:
        try:
            provider = ProviderConfig(
                id=str(entry["id"]),
                label=str(entry.get("label") or entry["id"]),
                base_url=str(entry["base_url"]).rstrip("/"),
                api_key=str(entry["api_key"]) if entry.get("api_key") else None,
                api_key_envs=_as_tuple(entry.get("api_key_envs") or entry.get("api_key_env")),
                supports_streaming=bool(entry.get("supports_streaming", True)),
                metadata=dict(entry.get("metadata") or {}),
            )
        except KeyError as exc:
            raise RuntimeError(f"Invalid provider configuration: missing {exc}") from exc
        providers[provider.id] = provider
    return providers


def _load_model_configs(providers: Dict[str, ProviderConfig]) -> Dict[str, ModelConfig]:
    data = _load_json_env("WEB_AGENT_MODELS") or DEFAULT_MODEL_CONFIGS
    models: Dict[str, ModelConfig] = {}
    for entry in data:
        try:
            provider_id = str(entry["provider_id"])
            if provider_id not in providers:
                raise RuntimeError(f"Model references unknown provider '{provider_id}'.")
            model = ModelConfig(
                id=str(entry["id"]),
                provider_id=provider_id,
                model_name=str(entry["model_name"]),
                display_name=str(entry["display_name"]) if entry.get("display_name") else None,
                description=str(entry["description"]) if entry.get("description") else None,
                supports_streaming=(
                    bool(entry["supports_streaming"]) if entry.get("supports_streaming") is not None else None
                ),
                metadata=dict(entry.get("metadata") or {}),
            )
        except KeyError as exc:
            raise RuntimeError(f"Invalid model configuration: missing {exc}") from exc
        models[model.id] = model
    if not models:
        raise RuntimeError("At least one model must be configured.")
    return models


PROVIDERS: Dict[str, ProviderConfig] = _load_provider_configs()
MODELS: Dict[str, ModelConfig] = _load_model_configs(PROVIDERS)

DEFAULT_CHAT_MODEL = os.environ.get("WEB_AGENT_DEFAULT_MODEL")
if DEFAULT_CHAT_MODEL:
    try:
        _ = MODELS[DEFAULT_CHAT_MODEL]
    except KeyError:
        logger.warning(
            "WEB_AGENT_DEFAULT_MODEL='%s' not found; falling back to the first configured model.",
            DEFAULT_CHAT_MODEL,
        )
        DEFAULT_CHAT_MODEL = None
if not DEFAULT_CHAT_MODEL:
    DEFAULT_CHAT_MODEL = next(iter(MODELS.keys()))

MAX_CONTEXT_TOKENS = 65536
SUMMARY_TOKEN_RATIO = 0.3
SUMMARY_TOKEN_LIMIT = int(MAX_CONTEXT_TOKENS * SUMMARY_TOKEN_RATIO)


def available_models() -> List[Tuple[ModelConfig, ProviderConfig]]:
    items: List[Tuple[ModelConfig, ProviderConfig]] = []
    for model in MODELS.values():
        provider = PROVIDERS[model.provider_id]
        items.append((model, provider))
    return items


def supported_model_ids() -> List[str]:
    return list(MODELS.keys())


def get_model_config(model: Optional[str]) -> ModelConfig:
    target = (model or DEFAULT_CHAT_MODEL or "").strip()
    if not target:
        raise ValueError("Model name cannot be empty.")
    if target in MODELS:
        return MODELS[target]
    # Allow lookup by underlying provider model name for compatibility.
    for config in MODELS.values():
        if config.model_name == target:
            return config
    raise ValueError(f"Unknown model: {target}")


def get_provider_config(model: Optional[str]) -> Tuple[ModelConfig, ProviderConfig]:
    model_config = get_model_config(model)
    provider = PROVIDERS[model_config.provider_id]
    return model_config, provider


def is_supported_chat_model(model: str) -> bool:
    try:
        get_model_config(model)
        return True
    except ValueError:
        return False


def canonical_chat_model(model: Optional[str]) -> str:
    return get_model_config(model).id


@lru_cache(maxsize=8)
def _get_openai_client(provider_id: str) -> OpenAI:
    provider = PROVIDERS[provider_id]
    api_key = provider.resolved_api_key()
    if not api_key:
        raise RuntimeError(
            f"No API key available for provider '{provider.label}'. "
            f"Set one of {', '.join(provider.api_key_envs) or 'an API key in config'}."
        )
    logger.info("Creating OpenAI client for provider '%s'.", provider.label)
    return OpenAI(base_url=provider.base_url, api_key=api_key)


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
    model_config, provider = get_provider_config(model)
    if stream and not model_config.streaming_enabled(provider):
        logger.warning(
            "Streaming requested for model '%s' but provider does not support streaming; falling back to non-stream.",
            model_config.id,
        )
        stream = False

    client = _get_openai_client(provider.id)
    payload: Dict[str, Any] = {
        "model": model_config.model_name,
        "messages": list(messages),
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = list(tools)
    if stream:
        payload["stream"] = True
        return client.chat.completions.create(**payload)
    return client.chat.completions.create(**payload)


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


def openai_model_payload() -> Dict[str, Any]:
    data = []
    for model_config, provider in available_models():
        data.append(
            {
                "id": model_config.id,
                "object": "model",
                "created": None,
                "owned_by": provider.id,
                "permission": [],
                "root": model_config.model_name,
                "parent": None,
                "metadata": {
                    "display_name": model_config.resolved_display_name(),
                    "description": model_config.resolved_description(),
                    "provider": {
                        "id": provider.id,
                        "label": provider.label,
                        "base_url": provider.base_url,
                    },
                    "supports_streaming": model_config.streaming_enabled(provider),
                },
            }
        )
    return {"object": "list", "data": data}
