from __future__ import annotations

from exa_py import Exa
from dotenv import load_dotenv

import os

load_dotenv()
exa = Exa(os.getenv("EXA_API_KEY"))


def web_search(query: str, num_results: int = 3) -> list[str]:
    try:
        response = exa.search_and_contents(
            query, text=True, type="auto", num_results=num_results
        )
        return response
    except Exception:
        raise


def refine_web_search_into_context(results: list) -> str:
    context = ""
    counter = 0
    for result in results.results:
        counter += 1
        context += f"<result {result.url} id={counter}> {result.text}</result>\n"
    return context


def fetch_url_content(
    url: str,
    *,
    max_characters: int = 8000,
) -> str:
    """Retrieve markdown-friendly content for a single URL."""
    response = exa.get_contents(
        urls=[url],
        text=True,
        summary={"query": "Concise summary"},
        livecrawl="fallback",
        livecrawl_timeout=15000,
    )

    if not getattr(response, "results", []):
        statuses = getattr(response, "statuses", []) or []
        status_lines = []
        for entry in statuses:
            if not isinstance(entry, dict):
                continue
            status = entry.get("status", "unknown")
            tag = entry.get("error", {}).get("tag") if entry.get("error") else None
            http_code = (
                entry.get("error", {}).get("httpStatusCode")
                if entry.get("error")
                else None
            )
            parts = [status.upper()]
            if tag:
                parts.append(str(tag))
            if http_code:
                parts.append(f"HTTP {http_code}")
            status_lines.append(f"- {entry.get('id', url)}: {' | '.join(parts)}")

        status_block = "\n".join(status_lines) if status_lines else "- No additional status metadata returned."
        return "\n".join(
            [
                f"# Content Unavailable",
                f"Unable to retrieve content for [{url}]({url}).",
                "",
                "## Retrieval Status",
                status_block,
                "",
                "Consider visiting the page manually or providing an alternative source.",
            ]
        ).strip()

    result = response.results[0]
    title = getattr(result, "title", "") or url
    summary = getattr(result, "summary", "")
    text = getattr(result, "text", "") or ""

    if max_characters and len(text) > max_characters:
        text = text[: max_characters - 3].rstrip() + "..."

    parts = [f"# {title.strip()}"]
    if summary:
        parts.append(f"## Summary\n{summary.strip()}")
    if text:
        parts.append(f"## Content\n{text.strip()}")

    return "\n\n".join(parts).strip()
