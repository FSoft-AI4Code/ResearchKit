# ResearchKit

**Cursor for researchers. Open-source. Agent-powered. Built on Overleaf.**

ResearchKit is an agent-powered platform for academic paper production. It layers an intelligent agent system on top of [Overleaf](https://www.overleaf.com) -- the LaTeX editor researchers already use -- to provide AI-augmented writing, literature discovery, figure generation, and simulated peer review.

## How It Works

```
Overleaf (the IDE)         ResearchKit (the intelligence layer)
 +-----------------+        +----------------------------------+
 | LaTeX editor    |        |  Main Agent (orchestrator)       |
 | PDF preview     | <----> |    - Inline editing              |
 | Git sync        |        |    - Grammar & paraphrase        |
 | Collaboration   |        |    - Section drafting            |
 +-----------------+        |                                  |
                            |  Sub-Agents (delegated tasks)    |
                            |    - Research Agent (stub)       |
                            |    - Figure Agent   (stub)       |
                            |    - Review Agent   (stub)       |
                            |                                  |
                            |  Memory (paper context)          |
                            |    - Paper summary & structure   |
                            |    - Citations & venue config    |
                            |    - Style profile               |
                            +----------------------------------+
```

The system has four Docker containers:

| Service        | Port | Description                                       |
| -------------- | ---- | ------------------------------------------------- |
| `sharelatex`   | 80   | Overleaf Community Edition (editor, compiler, collaboration) |
| `researchkit`  | 3020 | Python/FastAPI agent service (Main Agent + sub-agent stubs) |
| `mongo`        | 27017| MongoDB (Overleaf data store)                     |
| `redis`        | 6379 | Redis (Overleaf session/queue store)               |

The Overleaf web module (`services/web/modules/researchkit/`) provides a React sidebar panel in the editor that proxies requests to the ResearchKit Python service.

---

## Quick Start (Production)

### Prerequisites

- Docker and Docker Compose
- An LLM API key (at least one of):
  - `ANTHROPIC_API_KEY` for Claude models
  - `OPENAI_API_KEY` for OpenAI models (or any OpenAI-compatible endpoint)

### 1. Configure API keys

Edit `docker-compose.yml` and uncomment/set your keys under the `researchkit` service:

```yaml
researchkit:
  environment:
    RESEARCHKIT_PORT: "3020"
    OPENAI_API_KEY: "sk-..."           # For GPT models
    # OPENAI_BASE_URL: ""              # For custom OpenAI-compatible endpoints
    ANTHROPIC_API_KEY: "sk-ant-..."    # For Claude models
```

### 2. Start the stack

```bash
docker compose up -d
```

This builds and starts all four services. First launch may take several minutes while Docker builds the Overleaf and ResearchKit images.

### 3. Create an admin account

Open http://localhost/launchpad and create the first admin user.

### 4. Use ResearchKit

Open any Overleaf project. The ResearchKit sidebar panel is available in the editor. You can:

- Ask the agent to paraphrase, fix grammar, or draft sections
- Send your project files for indexing to build the Memory context
- Requests that match research/figure/review domains are routed to sub-agent stubs (which describe planned capabilities)

### Managing the stack

```bash
docker compose up -d          # Start all services
docker compose down            # Stop all services
docker compose logs researchkit # View ResearchKit logs
docker compose build researchkit # Rebuild after code changes
docker compose restart researchkit # Restart the agent service
```

---

## Development Setup

There are two development workflows: the **Overleaf dev environment** (for frontend/module work) and the **ResearchKit service** (for agent/backend work). You can run them independently or together.

### Option A: Full stack development (Overleaf + ResearchKit)

This starts all Overleaf services in dev mode with hot-reloading, plus the ResearchKit Python service.

```bash
# 1. Build the Overleaf dev environment
cd develop
bin/build

# 2. Add ResearchKit environment variables to develop/dev.env
echo 'RESEARCHKIT_URL=http://researchkit:3020' >> dev.env

# 3. Start the Overleaf dev stack
bin/dev

# 4. In a separate terminal, start the ResearchKit service
cd ../services/researchkit
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export ANTHROPIC_API_KEY="sk-ant-..."  # or OPENAI_API_KEY
uvicorn researchkit.main:app --reload --port 3020
```

Open http://localhost/launchpad to create an admin account, then open a project.

### Option B: ResearchKit backend only (standalone)

For working on the agent logic, providers, or API without the full Overleaf stack:

```bash
cd services/researchkit

# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
export ANTHROPIC_API_KEY="sk-ant-..."  # or OPENAI_API_KEY

# Run
uvicorn researchkit.main:app --reload --port 3020
```

The API is available at http://localhost:3020. Interactive docs at http://localhost:3020/docs.

You can test directly with curl:

```bash
# Health check
curl http://localhost:3020/api/health

# Chat (non-streaming)
curl -X POST http://localhost:3020/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test",
    "message": "Paraphrase this: The experiment results demonstrate significant improvement.",
    "stream": false
  }'

# Index a project
curl -X POST http://localhost:3020/api/project/index \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "test",
    "files": {
      "main.tex": "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nThis paper presents a novel approach.\n\\end{document}"
    }
  }'
```

### Running tests

```bash
cd services/researchkit
pytest
```

### Linting and formatting

```bash
cd services/researchkit
ruff check .
ruff format .
```

---

## Project Structure

```
ResearchKit/
  docker-compose.yml                  # Production stack (Overleaf + ResearchKit + Mongo + Redis)
  develop/                            # Overleaf dev environment (bin/build, bin/dev)
  services/
    researchkit/                      # Python agent service
      Dockerfile
      pyproject.toml
      README.md                       # Detailed backend docs + API reference
      researchkit/
        main.py                       # FastAPI entry point
        api/                          # REST routes + SSE streaming
        agents/                       # Main Agent + sub-agent stubs
        providers/                    # LLM provider abstraction (OpenAI, Claude)
        config/                       # .researchkit/config.yaml schema + loader
        memory/                       # Paper context system
        latex/                        # LaTeX project parser
    web/
      modules/
        researchkit/                  # Overleaf web module
          index.mjs                   # Module registration
          app/src/
            ResearchKitRouter.mjs     # Express proxy to Python service
          frontend/components/
            researchkit-panel.tsx      # Sidebar panel
            message-input.tsx         # Chat input
            message-list.tsx          # Message history
            agent-response.tsx        # Response renderer
            researchkit-panel.css     # Styles
    chat/                             # Overleaf chat service (existing)
    clsi/                             # Overleaf compile service (existing)
    ...                               # Other Overleaf services
```

---

## Configuration

Each Overleaf project can have a `.researchkit/config.yaml` for project-specific settings. Config can also be passed inline via the API.

```yaml
project:
  name: "My ACL 2026 Paper"
  venue: "acl-2026"
  page_limit: 8
  anonymous: true

providers:
  main_agent: claude-sonnet-4-20250514
  research_agent: claude-sonnet-4-20250514
  figure_agent: claude-sonnet-4-20250514
  review_agent: claude-sonnet-4-20250514
```

All fields have defaults -- no config file is required to get started.

See [`services/researchkit/README.md`](services/researchkit/README.md) for the full configuration reference, API documentation, and LLM provider details.

---

## Environment Variables

### ResearchKit service

| Variable            | Required | Description                                     |
| ------------------- | -------- | ----------------------------------------------- |
| `ANTHROPIC_API_KEY` | *        | API key for Claude models                       |
| `OPENAI_API_KEY`    | *        | API key for OpenAI / compatible models          |
| `OPENAI_BASE_URL`   | No       | Custom endpoint for OpenAI-compatible APIs      |
| `RESEARCHKIT_PORT`  | No       | Service port (default: 3020)                    |

\* At least one provider key is required.

### Overleaf web module

| Variable            | Required | Description                                     |
| ------------------- | -------- | ----------------------------------------------- |
| `RESEARCHKIT_URL`   | No       | ResearchKit service URL (default: `http://researchkit:3020`) |

---

## Current Status

This is the **MVP** implementation covering the Main Agent and core infrastructure:

| Component           | Status       | Description                                          |
| ------------------- | ------------ | ---------------------------------------------------- |
| LLM Providers       | Implemented  | OpenAI + Claude, model-agnostic registry             |
| Configuration       | Implemented  | YAML config with Pydantic validation                 |
| Memory System       | Implemented  | Paper summary, structure, citations, style profile   |
| LaTeX Parser        | Implemented  | Section/citation/figure extraction, input resolution |
| Main Agent          | Implemented  | Inline editing, intent classification, delegation    |
| API + Streaming     | Implemented  | REST + SSE endpoints                                 |
| Overleaf Module     | Implemented  | Sidebar panel with chat UI                           |
| Research Agent      | Stub         | Placeholder -- will search/read papers               |
| Figure Agent        | Stub         | Placeholder -- will generate plots/diagrams          |
| Review Agent        | Stub         | Placeholder -- will simulate peer review             |

---

## License

The Overleaf code in this repository is released under the GNU AFFERO GENERAL PUBLIC LICENSE, version 3. See the [`LICENSE`](LICENSE) file.

ResearchKit additions are released under the Apache License 2.0.
