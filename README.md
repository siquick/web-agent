## Web Agent API

FastAPI service that wraps a lightweight agent capable of web-grounded research using the Qwen/Qwen3-32B model routed through Hugging Face’s OpenAI-compatible APIs. It exposes OpenAI-style `/v1/query` and `/v1/chat` endpoints, plus a CLI for conversational testing.

---

### Features

- **OpenAI-compatible interface** – `/v1/query` and `/v1/chat` mirror the official schema for straightforward client integration.
- **Tool-aware agent** – Orchestrates web search, time, and future tools via dynamic tool definitions.
- **Reflection loop** – Optional self-check pass to demand more evidence before finalising answers.
- **Conversation summarisation** – Maintains a compact memory using the same LLM to avoid context overflows.
- **Interactive CLI** – `make chat` spins up a local terminal client that mirrors the API behaviour.

---

### Project Layout

```
.
├── main.py                 # FastAPI application entrypoint
├── chat_cli.py             # Terminal chat client (POSTs to /v1/chat)
├── lib/
│   ├── agent.py            # Reflection-enabled tool-use agent
│   ├── ai/
│   │   ├── llm.py          # Hugging Face router integration + helpers
│   │   ├── prompts.py      # Prompt templates
│   │   └── system_prompts.py
│   ├── tools.py            # Tool definitions + registry
│   └── web_search.py       # Exa search client and context shaping
├── pyproject.toml          # uv project definition
└── Makefile
```

---

### Requirements

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) for dependency and environment management
- API credentials:
  - `HF_TOKEN` – Hugging Face Inference API token with access to `Qwen/Qwen3-32B:*`
  - `EXA_API_KEY` – Exa search key (for web tool)
  - Any additional tool keys you enable

Create a `.env` (already gitignored) to populate the tokens, for example:

```
HF_TOKEN=hf_xxx
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
        "model": "Qwen/Qwen3-32B:cerebras",
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

### Make Targets

| Target       | Description                                               |
|--------------|-----------------------------------------------------------|
| `make run`   | Launch the FastAPI server via uvicorn (hot reload).       |
| `make chat`  | Start the interactive terminal client.                    |
| `make check` | Quick `compileall` sanity check (no network access).      |
| `make deps`  | Refresh dependencies with `uv sync`.                      |

---

### Extending Tools

- Implement a new tool by subclassing `BaseTool` in `lib/tools.py`.
- Register it via `default_tooling` or pass a custom `ToolRegistry` when constructing `ToolUseAgent`.
- Tool responses are automatically streamed back into the conversation and exposed in the API response metadata.

---

### Notes

- All model traffic routes through Hugging Face’s OpenAI-compatible REST API; adjust `HF_ROUTER_MODEL` in environment variables if you wish to target another deployment (e.g., `Qwen/Qwen3-32B:groq`).
- Reflection is constrained to a single additional turn to limit token and cost overhead. Tune `max_reflection_rounds` on `ToolUseAgent` if you need deeper self-critique.
- Summaries are only generated after a minimum conversation length to save tokens on short interactions.

Enjoy building on top of the agent! Contributions welcome.
