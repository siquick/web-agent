from __future__ import annotations

from typing import Any, List


def content_to_text(content: Any) -> str:
    """Normalize OpenAI-style message content into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_chunks: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text_chunks.append(item.get("text", ""))
        return " ".join(chunk for chunk in text_chunks if chunk).strip()
    return ""
