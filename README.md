# B2 (Brain2)

Personal knowledge graph for people and things: linked **nodes**, a central **inbox** (queue → approve), and simple **RAG** query. Phone-friendly **Jinja + htmx** UI. Stable JSON API under `/api/v1` so the backend can stay the same when you swap clients later.

## Quick start (local / Docker)

1. Copy env and add keys:

```bash
cp .env.example .env
```

2. Start Postgres + API:

```bash
docker compose up --build
```

3. Open [http://localhost:8000/inbox](http://localhost:8000/inbox)

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## LLM provider swap (LiteLLM)

Set in `.env`:

| Variable | Purpose |
|----------|---------|
| `LLM_MODEL` | e.g. `openai/gpt-4o-mini`, `anthropic/claude-3-5-sonnet-latest`, `xai/grok-2-latest`, `ollama/llama3.2` |
| `LLM_API_KEY` | Provider key |
| `LLM_API_BASE` | Optional; set for Ollama / proxies |

Same pattern for `EMBEDDING_*`, `STT_*`. TTS uses `TTS_*` (Grok/xAI by default).

## Features

- **Inbox** — text or mic → queued proposal → edit → approve/reject (does not write the graph until approve)
- **Nodes** — edit people/things/facts/links directly (text or mic)
- **Query** — RAG over fact embeddings + 1-hop links; optional speak answer (Grok TTS)

## Hosting later

Same `docker-compose.yml` shape: point `DATABASE_URL` at managed Postgres (with `pgvector`), set `API_KEY`, and put keys in the host env. UI and `/api/v1` both run from the `api` service.

When `API_KEY` is set, send header `X-API-Key` on API calls. For the browser mic/TTS helpers, set it in DevTools:

```js
localStorage.setItem("b2_api_key", "your-key")
```

## Dev without rebuilding images

Code is mounted into the API container with `--reload`. Edit files under `backend/` and refresh.
