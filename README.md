## Web Agent API

FastAPI service that wraps a lightweight agent capable of web-grounded research against any OpenAI-compatible provider. It exposes `/v1/query`, `/v1/chat`, and `/v1/chat/completions` (streaming) endpoints, plus a CLI for conversational testing.

---

### Features

- **OpenAI-compatible interface** – `/v1/query`, `/v1/chat`, and `/v1/chat/completions` mirror the official schema for straightforward client integration.
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
  - `OPENROUTER_API_KEY` – OpenRouter access token (if you enable the OpenRouter provider)
  - `HF_TOKEN` – Hugging Face Inference API token (if you enable the Hugging Face router provider)
  - `EXA_API_KEY` – Exa search key (for the web-search tool)
  - Any additional tool keys you enable
  - At least one OpenAI-compatible provider token (`OPENROUTER_API_KEY`, `HF_TOKEN`, etc.) must be present.

Create a `.env` (already gitignored) to populate the tokens, for example:

```
OPENROUTER_API_KEY=sk-or-...
HF_TOKEN=
EXA_API_KEY=exa_xxx
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

The backend now discovers providers and models from JSON environment variables, making it easy to switch between routers or offer multiple options to the UI:

- `WEB_AGENT_PROVIDERS` – JSON array describing OpenAI-compatible endpoints (defaults include OpenRouter and the Hugging Face router).
- `WEB_AGENT_MODELS` – JSON array mapping models to providers.
- `WEB_AGENT_DEFAULT_MODEL` – Optional model `id` to use when the client omits `model` (defaults to the first configured model).

Example `.env` fragment:

```env
OPENROUTER_API_KEY=sk-or-...

WEB_AGENT_PROVIDERS=[
  {
    "id": "openrouter",
    "label": "OpenRouter",
    "base_url": "https://openrouter.ai/api/v1",
    "api_key_envs": ["OPENROUTER_API_KEY"],
    "supports_streaming": true
  },
  {
    "id": "huggingface",
    "label": "Hugging Face Router",
    "base_url": "https://router.huggingface.co/v1",
    "api_key_envs": ["HF_TOKEN"],
    "supports_streaming": true
  }
]

WEB_AGENT_MODELS=[
  {
    "id": "openrouter/qwen-3-32b",
    "provider_id": "openrouter",
    "model_name": "qwen/qwen3-32b",
    "display_name": "Qwen 3 32B (OpenRouter)"
  },
  {
    "id": "hf/qwen-3-32b",
    "provider_id": "huggingface",
    "model_name": "Qwen/Qwen3-32B:groq",
    "display_name": "Qwen 3 32B (Hugging Face)"
  }
]

WEB_AGENT_DEFAULT_MODEL=openrouter/qwen-3-32b
```

If you omit these variables the API defaults to OpenRouter’s `qwen/qwen3-32b` model (requires `OPENROUTER_API_KEY`). The `/v1/models` endpoint surfaces the active list for clients such as the React UI.

Each provider entry supports:

- `id` / `label` – Identifier and human-readable name.
- `base_url` – OpenAI-compatible REST endpoint.
- `api_key_envs` – One or more environment variables that hold the API key.
- `supports_streaming` – Optional flag (default `true`) to disable streaming for that provider.

Each model entry maps to a provider and controls:

- `id` – Stable identifier returned to clients.
- `provider_id` – Which provider should handle requests.
- `model_name` – The provider-specific model name sent in `chat.completions`.
- `display_name`/`description` – Optional UI labels.
- `supports_streaming` – Overrides the provider-level flag for a single model.

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

- Model traffic routes through whichever provider/model pair you set in `WEB_AGENT_PROVIDERS` / `WEB_AGENT_MODELS`. By default the service targets OpenRouter’s `qwen/qwen3-32b`.
- Reflection is constrained to a single additional turn to limit token and cost overhead. Tune `max_reflection_rounds` on `ToolUseAgent` if you need deeper self-critique.
- Summaries are only generated after a minimum conversation length to save tokens on short interactions.
