# ResearchKit Service

AI agent service for academic paper production. Built with Python/FastAPI, runs alongside Overleaf as a separate microservice.

## Architecture

```
Overleaf (port 80)  ──proxy──▶  ResearchKit (port 3020)  ──▶  MongoDB
   │                                  │
   │ React sidebar UI                 │ FastAPI + SSE streaming
   │ Express proxy routes             │ Main Agent + Memory + LLM Providers
   └──────────────────────────────────┘
```

The Overleaf module (`services/web/modules/researchkit/`) provides the frontend UI and proxies requests to this Python service. The proxy also injects project files from Overleaf's internal storage so the agent has access to LaTeX content.

## Development Setup

### Prerequisites

- Python 3.11+
- MongoDB running locally (or via docker compose)
- At least one LLM API key (OpenAI or Anthropic)

### Option A: Standalone (Python service only)

```bash
cd services/researchkit

# Create virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Set environment variables
export MONGODB_URL="mongodb://localhost:27017/sharelatex"
export OPENAI_API_KEY="sk-..."
# Optional: export OPENAI_BASE_URL="http://localhost:4000"  # for LiteLLM/vLLM proxy
# Optional: export ANTHROPIC_API_KEY="sk-ant-..."

# Run with hot reload
uvicorn researchkit.main:app --reload --host 0.0.0.0 --port 3020
```

Test it:
```bash
curl http://localhost:3020/api/health
# {"status":"ok","service":"researchkit"}
```

### Option B: Full Stack (Overleaf + ResearchKit)

```bash
# From repo root
cp .env.example .env  # or edit .env directly

# Edit .env with your API keys:
#   OPENAI_API_KEY=sk-...
#   OPENAI_BASE_URL=http://0.0.0.0:4000  (optional, for proxy)
#   ANTHROPIC_API_KEY=sk-ant-...          (optional)

docker compose up --build
```

This starts:
- **sharelatex** on port 80 (Overleaf editor)
- **researchkit** on port 3020 (this service)
- **mongo** on port 27017
- **redis** on port 6379

### Option C: Hybrid (Docker Overleaf + local Python)

Useful for developing the Python service with hot reload while running Overleaf in Docker.

```bash
# Terminal 1: Start Overleaf + MongoDB + Redis
docker compose up sharelatex mongo redis

# Terminal 2: Run ResearchKit locally
cd services/researchkit
source .venv/bin/activate
export MONGODB_URL="mongodb://localhost:27017/sharelatex"
export OPENAI_API_KEY="sk-..."
uvicorn researchkit.main:app --reload --host 0.0.0.0 --port 3020
```

Note: When running locally, set `RESEARCHKIT_URL=http://host.docker.internal:3020` in the Overleaf container's environment so the proxy can reach your local service. Or set `RESEARCHKIT_URL=http://localhost:3020` if not using Docker for Overleaf.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/chat` | Chat with Main Agent (returns SSE stream) |
| POST | `/api/project/index` | Index project files to build Memory |
| GET | `/api/memory/{project_id}` | Get paper Memory state |
| GET | `/api/config/{project_id}` | Get project config |
| POST | `/api/config/{project_id}` | Update project config |

### Chat Request

```bash
curl -N -X POST http://localhost:3020/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test-project",
    "message": "Paraphrase this paragraph",
    "selected_text": "\\section{Introduction}\nThis paper presents...",
    "files": {
      "main.tex": "\\documentclass{article}\n\\begin{document}\n...",
      "refs.bib": "@article{smith2024, ...}"
    }
  }'
```

### Index Project

```bash
curl -X POST http://localhost:3020/api/project/index \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test-project",
    "files": {
      "main.tex": "\\documentclass[acl]{article}\\n...",
      "refs.bib": "@article{..."
    }
  }'
```

## LLM Provider Configuration

The service supports multiple LLM providers via environment variables or per-project config.

### Environment Variables (defaults)

```bash
# OpenAI (default)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=                    # Leave empty for api.openai.com
RESEARCHKIT_MODEL=gpt-4o            # Default model

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Custom OpenAI-compatible endpoint (LiteLLM, vLLM, Ollama, etc.)
OPENAI_BASE_URL=http://localhost:4000
RESEARCHKIT_PROVIDER_TYPE=custom
```

### Per-project Config (via API)

```bash
curl -X POST http://localhost:3020/api/config/my-project \
  -H "Content-Type: application/json" \
  -d '{
    "provider_type": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key": "sk-ant-..."
  }'
```

## Project Structure

```
researchkit/
├── main.py              # FastAPI app entry point
├── db.py                # MongoDB connection (motor async)
├── api/
│   ├── routes.py        # API endpoints
│   └── models.py        # Pydantic request/response schemas
├── agents/
│   ├── base.py          # SubAgent ABC, Task/Result models
│   ├── main_agent.py    # Main Agent orchestrator
│   ├── tools.py         # Tool definitions for function calling
│   ├── research_agent.py  # Stub (coming soon)
│   ├── figure_agent.py    # Stub (coming soon)
│   └── review_agent.py    # Stub (coming soon)
├── memory/
│   ├── memory.py        # MemoryManager (build, get, reindex)
│   ├── schema.py        # PaperMemory, SectionInfo, CitationEntry
│   └── latex_parser.py  # LaTeX structure extraction
├── providers/
│   ├── base.py          # LLMProvider ABC
│   ├── openai_provider.py
│   ├── claude_provider.py
│   └── registry.py      # Provider factory
└── config/
    ├── schema.py        # ProviderConfig model
    └── loader.py        # Config loading (env → MongoDB → request)
```

## Testing

```bash
cd services/researchkit
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check researchkit/
ruff format researchkit/
```

## MongoDB Collections

This service uses three collections in the shared Overleaf MongoDB database:

- `researchkitMemory` — Paper context (summary, structure, citations, etc.)
- `researchkitConversations` — Chat history per project
- `researchkitConfig` — Per-project LLM provider configuration
