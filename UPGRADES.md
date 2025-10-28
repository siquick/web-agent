# Upgrade Plan

## Goals
- Support dynamic provider/model selection and expose `/v1/models` for Chat UI compatibility.
- Stream assistant responses (tokens, `<thinking>` segments, tool-call events) from the API.
- Surface real-time thinking and tool activity in the React `web-ui`, including a model/router selector.

## Phases

### 1. API Foundation
- [x] Refactor `web_agent/ai/llm.py` to source router configs from env, manage multiple providers, and allow per-request model selection.
- [x] Add `/v1/models` endpoint in `main.py` returning OpenAI-compatible model listings with provider metadata.
- [x] Implement streaming `/v1/chat/completions` (SSE) with token, thinking, and tool-call deltas; keep `/v1/chat` as non-stream fallback.
- [x] Emit tool-call progress events during agent runs (start/update/finish) and propagate via streaming responses.
- [x] Update validation/helpers so `ToolUseAgent.run(...)` respects requested models and streams tool reflections as metadata.

### 2. UI Enhancements (`web-ui`)
- [x] Introduce model/router selector fed by `/v1/models`; persist choice in local storage.
- [x] Switch chat client to a streaming SSE handler, handling incremental answer chunks and aborts.
- [x] Parse and render `<thinking>` sections with a collapsible panel that updates live.
- [x] Display in-progress tool calls with incremental output; collapse into metadata summaries on completion.
- [x] Provide graceful fallbacks when streaming is unavailable (retry with `/v1/chat`).

### 3. Tooling & Docs
- [ ] Add necessary dependencies via `uv add ...` (API) and `pnpm add ...` (web UI). *(Not required so far; existing deps cover the new work.)*
- [x] Document new environment variables (provider keys, router toggles) in `README.md` / `.env`.
- [x] Expand manual test checklist covering model selection, streaming, tool-call visualization, and error cases (compileall + TypeScript checks).

## Acceptance Criteria
- Users can pick among configured providers/models in the UI; selection drives API requests.
- Streaming responses deliver visible token-by-token output, with `<thinking>` displayed distinctly.
- Tool usage appears in real time while the assistant responds, with final summaries matching existing metadata.
- `/v1/models` and `/v1/chat/completions` conform to OpenAI schema so Chat UI can connect without patches.
