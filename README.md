## Web Agent API

FastAPI service that wraps a lightweight agent capable of web-grounded research using models served via Hugging Face’s OpenAI-compatible router. It exposes OpenAI-style `/v1/query` and `/v1/chat` endpoints, plus a CLI for conversational testing.

---

### Features

- **OpenAI-compatible interface** – `/v1/query` and `/v1/chat` mirror the official schema for straightforward client integration.
- **Tool-aware agent** – Orchestrates web search, URL content fetching, time, and future tools via dynamic tool definitions.
- **Reflection loop** – Optional self-check pass to demand more evidence before finalising answers.
- **Conversation summarisation** – Maintains a compact memory using the same LLM to avoid context overflows.
- **Interactive CLI** – `make chat` spins up a local terminal client that mirrors the API behaviour.

---

### Project Layout

```
.
├── main.py                 # FastAPI application entrypoint
├── chat_cli.py             # Terminal chat client (POSTs to /v1/chat)
├── web_agent/
│   ├── __init__.py
│   ├── agent.py            # Reflection-enabled tool-use agent
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── llm.py          # Hugging Face router integration + helpers
│   │   ├── prompts.py      # Prompt templates
│   │   ├── system_prompts.py
│   │   ├── utils.py        # Message content helpers
│   │   └── token_utils.py  # Token counting utilities
│   ├── api/
│   │   └── schemas.py      # OpenAI-compatible request models
│   ├── services/
│   │   └── web_search.py   # Exa clients and helpers
│   └── tools/
│       ├── __init__.py
│       └── registry.py     # Tool definitions and registry
├── pyproject.toml          # uv project definition
└── Makefile
```

---

### Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) for dependency and environment management
- API credentials:
  - `HF_TOKEN` – Hugging Face Inference API token with access to your chosen hosted model
  - `EXA_API_KEY` – Exa search key (for web tool)
  - 'OPENROUTER_API_KEY' - Openrouter API key with access to your chosen modek
  - Any additional tool keys you enable
  - Note you need atleast one of HF_TOKEN or OPENROUTER_API_KEY

Create a `.env` (already gitignored) to populate the tokens, for example:

```
HF_TOKEN=hf_xxx
EXA_API_KEY=exa_xxx
OPENROUTER_API_KEY=
```

---

### Setup

```bash
# Install dependencies into the uv-managed virtualenv
uv sync

# Drop into the environment when needed
uv shell
```

---

### Running the API

```bash
make run
# FastAPI available at http://127.0.0.1:8000
```

Health check:

```
GET /health -> {"status": "ok"}
```

OpenAPI-style requests (example with curl):

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
        "model": "Qwen/Qwen3-32B:groq",
        "messages": [
          {"role": "system", "content": "You are a helpful assistant."},
          {"role": "user", "content": "Summarise the latest MPC news."}
        ]
      }'
```

---

### CLI Chat Client

```bash
make chat
# Connects to http://127.0.0.1:8000/v1/chat by default
```

Configure `WEB_AGENT_API_URL` or `WEB_AGENT_SYSTEM_PROMPT` in `.env` to point the CLI at remote deployments or override the persona.

---

### Web UI (React)

- Requires Node 22.x and [pnpm](https://pnpm.io/) (the project declares both in `web-ui/package.json`).
- The UI expects the FastAPI server to be running and reachable at the URL exposed via `VITE_WEB_AGENT_API_URL` (defaults to `http://127.0.0.1:8000`).

```bash
cd web-ui
pnpm install
pnpm dev
```

Environment overrides (add to `web-ui/.env` or export before running Vite):

- `VITE_WEB_AGENT_API_URL` – Base URL for the FastAPI backend.
- `VITE_WEB_AGENT_MODEL` – Model name sent with chat requests (defaults to the backend’s default).
- `VITE_WEB_AGENT_SYSTEM_PROMPT` – Optional custom system prompt displayed in the first turn.

---

### Model Configuration

- The API speaks the OpenAI `chat/completions` schema end‑to‑end. You can point it at any router or gateway that exposes that surface: Hugging Face Inference, OpenRouter, Ollama, or a self-hosted OpenAI-compatible stack.
- Configure the backend by wiring the environment variables consumed in `web_agent/ai/llm.py`. Examples:
  - **OpenRouter** – set `ROUTER_BASE_URL=https://openrouter.ai/api/v1`, `ROUTER_MODEL=qwen/qwen3-32b`, and `OPENROUTER_API_KEY=<token>`.
  - **Hugging Face Router** – set `ROUTER_BASE_URL=https://router.huggingface.co/v1`, `ROUTER_MODEL=Qwen/Qwen3-32B:groq`, and `ROUTER_KEY=HF_TOKEN`.
  - **Ollama (local)** – set `ROUTER_BASE_URL=http://127.0.0.1:11434/v1`, `ROUTER_MODEL=qwen3:1.7b`, and leave the key blank.
- Whatever router you choose, keep the `model` parameter sent by the CLI/web UI in sync with `ROUTER_MODEL` to avoid validation errors.
- Because the interface is standardised, swapping providers usually means updating `ROUTER_BASE_URL`, `ROUTER_MODEL`, and the token—no code changes required.

---

### Make Targets

| Target       | Description                                               |
|--------------|-----------------------------------------------------------|
| `make run`   | Launch the FastAPI server via uvicorn (hot reload).       |
| `make chat`  | Start the interactive terminal client.                    |
| `make check` | Quick `compileall` sanity check (no network access).      |
| `make deps`  | Refresh dependencies with `uv sync`.                      |

---

### Extending Tools

- Implement a new tool by subclassing `BaseTool` in `web_agent/tools/registry.py`.
- Register it via `default_tooling` or pass a custom `ToolRegistry` when constructing `ToolUseAgent`.
- Built-in tools:
  - `web_search` – Exa-powered multi-result search with context stitching.
  - `fetch_url_content` – Pull full page content for a pasted URL and return markdown.
  - `current_time_utc` – Snapshot of the current UTC time.
- Tool responses are automatically streamed back into the conversation and exposed in the API response metadata.

---

### Notes

- Model traffic routes through Hugging Face’s OpenAI-compatible REST API. Set `ROUTER_MODEL` (defaults to `Qwen/Qwen3-32B:cerebras`) to any model listed in the [Hugging Face Inference catalog](https://huggingface.co/inference/models) that supports the chat completions interface.
- Reflection is constrained to a single additional turn to limit token and cost overhead. Tune `max_reflection_rounds` on `ToolUseAgent` if you need deeper self-critique.
- Summaries are only generated after a minimum conversation length to save tokens on short interactions.
