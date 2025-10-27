from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from web_agent.ai.llm import DEFAULT_CHAT_MODEL

load_dotenv()

DEFAULT_BASE_URL = os.environ.get("WEB_AGENT_API_URL", "http://127.0.0.1:8000")
DEFAULT_MODEL = DEFAULT_CHAT_MODEL
SYSTEM_PROMPT = os.environ.get(
    "WEB_AGENT_SYSTEM_PROMPT",
    "You are a helpful research assistant. Cite sources when possible.",
)


def build_payload(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"model": DEFAULT_MODEL, "messages": messages, "stream": False}


def extract_text(choice: Dict[str, Any]) -> str:
    message = choice.get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(part.get("text", ""))
        return "\n".join(chunk for chunk in chunks if chunk)
    return ""


def print_tool_metadata(metadata: Optional[Dict[str, Any]]) -> None:
    if not metadata:
        return
    tool_calls = metadata.get("tool_calls", [])
    if not tool_calls:
        return

    print("\n[tool usage]")
    for call in tool_calls:
        name = call.get("name", "unknown")
        args = json.dumps(call.get("arguments", {}))
        preview = call.get("output_preview", "")
        truncated = (preview[:180] + "…") if len(preview) > 180 else preview
        print(f"- {name} {args}")
        if truncated:
            print(f"  ↳ {truncated}")
    print()


def main() -> int:
    base_url = DEFAULT_BASE_URL.rstrip("/")
    endpoint = f"{base_url}/v1/chat"
    print("Interactive chat client. Type '/quit' or Ctrl+C to exit.")
    print(f"Sending requests to: {endpoint}")

    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in {"/quit", "/exit"}:
                print("Exiting chat client.")
                break
            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})
            payload = build_payload(messages)

            try:
                response = requests.post(endpoint, json=payload, timeout=60)
            except requests.RequestException as exc:
                print(f"[error] Failed to reach API: {exc}")
                messages.pop()
                continue

            if response.status_code != 200:
                print(f"[error] API returned {response.status_code}: {response.text}")
                messages.pop()
                continue

            body = response.json()
            choice = body.get("choices", [{}])[0]
            assistant_text = extract_text(choice)
            metadata = choice.get("message", {}).get("metadata")
            print("\nAssistant:", assistant_text or "[no content]")
            print_tool_metadata(metadata)

            messages.append({"role": "assistant", "content": assistant_text})
    except KeyboardInterrupt:
        print("\nExiting chat client.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
