from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache
def _encoder() -> tiktoken.Encoding:
    """Return a tokenizer suitable for modern chat models."""
    # o200k_base covers GPT-4o and is a reasonable approximation for Qwen.
    return tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoder().encode(text, disallowed_special=()))


def trim_to_tokens(text: str, max_tokens: int) -> str:
    if not text:
        return ""
    if max_tokens <= 0:
        return ""
    encoder = _encoder()
    tokens = encoder.encode(text, disallowed_special=())
    if len(tokens) <= max_tokens:
        return text
    trimmed_tokens = tokens[:max_tokens]
    return encoder.decode(trimmed_tokens)
