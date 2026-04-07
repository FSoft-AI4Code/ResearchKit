# ResearchKit Service

Backend service for ResearchKit's agent, memory, provider, and runner workflows. This service runs alongside Overleaf and is exposed to the web module through proxied project-scoped routes. In the overall product model, Overleaf is the IDE and the LaTeX paper project is the codebase the backend reasons over.

Project-level documentation lives in the root [README](../../README.md). Architecture details live in [docs/architecture.md](../../docs/architecture.md).

## Responsibilities

- Expose the HTTP API used by the Overleaf module
- Run the Main Agent tool loop
- Persist project memory, conversations, and provider config
- Manage provider selection and model discovery
- Execute literature-search workflows through the Research Agent
- Run execution-oriented shell commands through the runner service

## Service Layout

```text
services/researchkit/
  researchkit/
    main.py              FastAPI entrypoint
    api/                 routes and Pydantic models
    agents/              MainAgent, sub-agents, tools, editor helpers
    memory/              LaTeX parsing and PaperMemory management
    providers/           LLM provider adapters and model discovery
    config/              config schema, loading, and secret encryption
    literature/          ASTA MCP and citation tooling
    runner/              separate FastAPI app for command execution
  tests/                 backend test suite
```

## Development

### Local service

```bash
cd services/researchkit
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export MONGODB_URL="mongodb://localhost:27017/sharelatex"
export OPENAI_API_KEY="sk-..."
uvicorn researchkit.main:app --reload --host 0.0.0.0 --port 3020
```

Health check:

```bash
curl http://localhost:3020/api/health
```

### Full stack from repo root

```bash
docker compose up --build
```

### Runner service

The same image also serves the runner:

```bash
uvicorn researchkit.runner.main:app --host 0.0.0.0 --port 3030
```

## API Surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | health check |
| `POST` | `/api/chat` | SSE chat stream |
| `GET` | `/api/conversation/{project_id}` | get conversation history |
| `GET` | `/api/conversation/{project_id}/list` | list conversations |
| `DELETE` | `/api/conversation/{project_id}` | clear conversation |
| `POST` | `/api/project/index` | build project memory |
| `GET` | `/api/memory/{project_id}` | fetch memory |
| `GET` | `/api/config/{project_id}` | fetch saved project config |
| `POST` | `/api/config/{project_id}` | save project config |
| `POST` | `/api/config/{project_id}/test` | validate provider config |
| `POST` | `/api/models/{project_id}` | discover available models |

### Chat stream events

`POST /api/chat` emits SSE events with these event names:

- `message`
- `action`
- `patch`
- `response`
- `done`

## Configuration

ResearchKit merges configuration in this order:

1. environment defaults
2. per-project MongoDB settings
3. request-level overrides

Key environment variables:

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=
ANTHROPIC_API_KEY=
RESEARCHKIT_PROVIDER_TYPE=openai
RESEARCHKIT_MODEL=gpt-4o
RESEARCHKIT_ASTA_API_KEY=
RESEARCHKIT_ASTA_MCP_URL=https://asta-tools.allen.ai/mcp/v1
RESEARCHKIT_RUNNER_URL=http://researchkit-runner:3030
RESEARCHKIT_WORKSPACE_PATH=
RESEARCHKIT_ALLOWED_WORKSPACE_ROOTS=
RESEARCHKIT_BASH_TIMEOUT_SECONDS=60
RESEARCHKIT_MAX_TOOL_ITERATIONS=8
RESEARCHKIT_TOOL_OUTPUT_MAX_CHARS=12000
RESEARCHKIT_CONFIG_ENCRYPTION_KEY=
```

## Storage

The service writes to three MongoDB collections in the shared Overleaf database:

- `researchkitMemory`
- `researchkitConversations`
- `researchkitConfig`

## Notes on Current Implementation

- `MainAgent` is the primary editor-facing orchestrator.
- `ResearchAgent` is implemented and handles literature workflows.
- `FigureAgent` and `ReviewAgent` are placeholders.
- `bash` is intentionally restricted to execution-oriented commands.
- File inspection and file changes are expected to go through `str_replace_editor`.

## Testing

```bash
cd services/researchkit
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q tests
ruff check researchkit/
```
