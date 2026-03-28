# ResearchKit

**Cursor for researchers. Open-source. Agent-powered. Built on Overleaf.**

ResearchKit is an AI agent layer built on top of [Overleaf Community Edition](https://github.com/overleaf/overleaf). It gives researchers the same kind of AI-augmented workflow that software engineers get with Cursor — inline editing, paper-aware context, and specialized agents — while keeping the Overleaf IDE they already know.

## Quick Start (Production)

### Prerequisites

- Docker and Docker Compose
- An LLM API key (OpenAI, Anthropic, or any OpenAI-compatible endpoint)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
```bash
RESEARCHKIT_PORT=3020

# Option A: OpenAI
OPENAI_API_KEY=sk-...

# Option B: OpenAI-compatible proxy (LiteLLM, vLLM, Ollama, etc.)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=http://your-proxy:4000

# Option C: Anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Build and start all services

```bash
docker compose up -d --build
```

The first build takes a few minutes — it extends the official Overleaf image with the ResearchKit module and rebuilds the frontend bundle.

This starts:

| Service | Port | Description |
|---------|------|-------------|
| sharelatex | 80 | Overleaf editor |
| researchkit | 3020 | AI agent service (Python/FastAPI) |
| mongo | 27017 | MongoDB |
| redis | 6379 | Redis |

### 3. Create admin account

```bash
docker exec sharelatex /bin/bash -c "cd /overleaf/services/web && node modules/server-ce-scripts/scripts/create-user --admin --email=admin@example.com"
```

### 4. Use ResearchKit

1. Open http://localhost in your browser
2. Log in and open a LaTeX project
3. Click the **ResearchKit** icon (robot) in the sidebar rail
4. Start chatting: "Paraphrase this paragraph", "Draft an introduction", etc.

## Development Setup

### Option A: Full stack with Docker

```bash
docker compose up --build
```

### Option B: Python service only (with hot reload)

Best for developing the agent/memory/provider code.

```bash
# Terminal 1: Start Overleaf + databases
docker compose up sharelatex mongo redis

# Terminal 2: Run ResearchKit with hot reload
cd services/researchkit
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export MONGODB_URL="mongodb://localhost:27017/sharelatex"
export OPENAI_API_KEY="sk-..."
uvicorn researchkit.main:app --reload --host 0.0.0.0 --port 3020
```

### Option C: Frontend only

For working on the Overleaf sidebar UI:

```bash
# From repo root — follow standard Overleaf dev setup
cd develop && bin/build && bin/dev
```

The ResearchKit module lives at `services/web/modules/researchkit/`. Restart webpack after changing `settings.defaults.js`.

## Architecture

```
┌─────────────────────────────────────────┐
│  Overleaf (port 80)                     │
│  ├── React sidebar panel (thin UI)      │
│  └── Express proxy → injects project    │
│       files and forwards to Python      │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  ResearchKit Service (port 3020)        │
│  ├── Main Agent (inline editing)        │
│  ├── Memory (paper context)             │
│  ├── LLM Providers (OpenAI/Claude/...)  │
│  ├── Research Agent (stub)              │
│  ├── Figure Agent (stub)                │
│  └── Review Agent (stub)                │
└──────────────┬──────────────────────────┘
               │
          MongoDB (shared)
```

### Key directories

```
services/
├── researchkit/              # Python AI service (FastAPI)
│   └── researchkit/
│       ├── agents/           # Main Agent + sub-agent stubs
│       ├── memory/           # Paper context (LaTeX parser, Memory)
│       ├── providers/        # LLM abstraction (OpenAI, Claude, custom)
│       ├── api/              # REST endpoints
│       └── config/           # Configuration management
└── web/
    └── modules/researchkit/  # Overleaf frontend module
        ├── app/src/          # Express proxy routes
        └── frontend/         # React sidebar components
```

## What Works Now (MVP)

- Sidebar chat panel in the Overleaf editor
- Streaming responses via SSE
- Main Agent with inline editing (paraphrase, grammar, section drafting, BibTeX)
- Paper Memory system (auto-indexes LaTeX project structure, citations, abstract)
- Multi-provider LLM support (OpenAI, Anthropic, any OpenAI-compatible endpoint)
- Per-project configuration

## What's Coming (Sub-Agents)

- **Research Agent** — literature search, full-paper reading, citation graph traversal, related work generation
- **Figure Agent** — data-to-plots via Python execution, TikZ generation, diagram creation
- **Review Agent** — simulated peer review, claim strength analysis, venue checklist validation

See [ResearchKit-PRD.md](ResearchKit-PRD.md) for the full product specification.

## Testing

```bash
cd services/researchkit
pip install -e ".[dev]"
pytest
ruff check researchkit/
```

## Based on Overleaf

This project is built on top of [Overleaf Community Edition](https://github.com/overleaf/overleaf). See the original [CONTRIBUTING.md](CONTRIBUTING.md) for Overleaf contribution guidelines.

## License

The code in this repository is released under the GNU AFFERO GENERAL PUBLIC LICENSE, version 3. A copy can be found in the [`LICENSE`](LICENSE) file.
