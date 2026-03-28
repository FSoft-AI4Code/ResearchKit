# ResearchKit Service

Agent-powered intelligence layer for academic paper production, built on top of Overleaf.

ResearchKit provides a **Main Agent** that handles inline LaTeX editing (paraphrase, grammar, section drafting) and delegates complex tasks to specialized **Sub-Agents** (Research, Figure, Review -- currently stubs). All agents share a persistent **Memory** system that maintains paper context across interactions.

## Architecture

```
researchkit/
  main.py              FastAPI application entry point
  api/
    routes.py          REST + SSE streaming endpoints
    models.py          Request/response schemas
  agents/
    base.py            SubAgent ABC, Task/Result models
    main_agent.py      Orchestrator: inline editing + delegation
    research_agent.py  Stub -- literature discovery
    figure_agent.py    Stub -- chart/diagram generation
    review_agent.py    Stub -- simulated peer review
  providers/
    base.py            LLMProvider ABC (complete + stream)
    openai_provider.py OpenAI-compatible (GPT, vLLM, LiteLLM, etc.)
    claude_provider.py Anthropic Claude
    registry.py        Model name -> provider factory
  config/
    schema.py          Pydantic models for .researchkit/config.yaml
    loader.py          YAML loader with defaults
  memory/
    memory.py          Paper context: summary, structure, citations, style
    schema.py          Memory component models
  latex/
    parser.py          Regex-based LaTeX project parser
    models.py          Section, Citation, Figure, Table dataclasses
```

## Prerequisites

- Python 3.11+
- An LLM API key (at least one of):
  - `ANTHROPIC_API_KEY` for Claude models
  - `OPENAI_API_KEY` for OpenAI models (or any OpenAI-compatible endpoint)

## Development Setup

### 1. Create a virtual environment

```bash
cd services/researchkit
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

### 3. Set environment variables

```bash
# Required -- at least one provider key
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export OPENAI_API_KEY="sk-..."

# Optional -- for OpenAI-compatible proxies (vLLM, LiteLLM, Together, Groq, etc.)
export OPENAI_BASE_URL="http://localhost:8000/v1"
```

### 4. Run the development server

```bash
uvicorn researchkit.main:app --reload --port 3020
```

The API is available at `http://localhost:3020`. Interactive docs at `http://localhost:3020/docs`.

### 5. Run tests

```bash
pytest
```

### 6. Lint and format

```bash
ruff check .
ruff format .
```

## Production Setup (Docker)

ResearchKit runs as a Docker container alongside the Overleaf stack.

### Standalone

```bash
cd services/researchkit
docker build -t researchkit .
docker run -p 3020:3020 \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  researchkit
```

### With Overleaf (docker-compose)

From the repository root, the `researchkit` service is already defined in `docker-compose.yml`. Set your API keys and start everything:

```bash
# Edit docker-compose.yml to uncomment and set your API keys under the
# researchkit service environment section, then:
docker compose up -d
```

The service listens on port `3020` inside the Docker network. The Overleaf web module at `services/web/modules/researchkit/` proxies requests from the browser to `http://researchkit:3020`.

## API Reference

### `GET /api/health`

Health check.

```json
{"status": "ok", "service": "researchkit"}
```

### `POST /api/chat`

Send a message to the Main Agent. Supports both JSON response and SSE streaming.

**Request:**

```json
{
  "project_id": "abc123",
  "message": "Paraphrase this paragraph to be more concise",
  "selected_text": "\\section{Introduction}\nThis paper presents...",
  "current_file": "",
  "files": {},
  "stream": true,
  "config": null
}
```

- `project_id` (required) -- Overleaf project identifier
- `message` (required) -- User's instruction to the agent
- `selected_text` -- Currently selected LaTeX text in the editor
- `current_file` -- Full content of the active .tex file
- `files` -- Dict of `{relative_path: content}` for the full project
- `stream` -- `true` for SSE streaming (default), `false` for a single JSON response
- `config` -- Optional inline config override (same schema as `.researchkit/config.yaml`)

**Response (non-streaming):**

```json
{
  "status": "completed",
  "content": "The edited LaTeX content...",
  "artifacts": [],
  "confidence": 0.0,
  "needs_human_review": false
}
```

**Response (streaming):** Server-Sent Events where each event is:

```
data: {"content": "partial text...", "finish_reason": null}
```

Final event:

```
data: [DONE]
```

### `POST /api/project/index`

Index a LaTeX project to build/update the Memory system.

**Request:**

```json
{
  "project_id": "abc123",
  "files": {
    "main.tex": "\\documentclass{article}...",
    "sections/intro.tex": "\\section{Introduction}...",
    "refs.bib": "@article{smith2025,..."
  }
}
```

**Response:**

```json
{
  "status": "indexed",
  "paper_summary": "This paper proposes...",
  "sections": [
    {"name": "Introduction", "status": "complete", "page_estimate": 1.2}
  ],
  "citation_count": 15
}
```

### `GET /api/memory?project_id=abc123`

Return the current Memory state for a previously indexed project.

## Configuration

Each Overleaf project can include a `.researchkit/config.yaml` file. Alternatively, configuration can be passed inline via the `config` field in API requests.

```yaml
project:
  name: "My ACL 2026 Paper"
  venue: "acl-2026"
  type: "long-paper"
  page_limit: 8
  anonymous: true

providers:
  main_agent: claude-sonnet-4-20250514    # Fast inline edits
  research_agent: claude-sonnet-4-20250514
  figure_agent: claude-sonnet-4-20250514
  review_agent: claude-sonnet-4-20250514
  # api_key: ""     # Override env var per-project
  # base_url: ""    # For custom OpenAI-compatible endpoints

agents:
  research:
    sources: [semantic_scholar, arxiv]
    search_strategy: survey_first
    read_depth: full
    citation_graph_hops: 2
    max_papers: 50
  figure:
    default_style: matplotlib
    color_palette: colorblind_safe
    output_format: pdf
    save_scripts: true
  review:
    simulate_reviewers: 3
    venue_checklist: auto
    severity_threshold: minor
```

All fields have defaults -- a minimal config (or no config at all) works out of the box.

## LLM Provider Support

The provider registry maps model name prefixes to SDK implementations:

| Prefix        | Provider        | SDK        | Env Var             |
| ------------- | --------------- | ---------- | ------------------- |
| `claude-*`    | ClaudeProvider  | `anthropic`| `ANTHROPIC_API_KEY` |
| `gpt-*`       | OpenAIProvider  | `openai`   | `OPENAI_API_KEY`    |
| `o1*`, `o3*`, `o4*` | OpenAIProvider | `openai` | `OPENAI_API_KEY`  |
| Any + `base_url` | OpenAIProvider | `openai` | `OPENAI_API_KEY`  |

To use a local model or third-party proxy, set `OPENAI_BASE_URL` (or `base_url` in config) to point at your endpoint. Any model name that doesn't match a known prefix is treated as OpenAI-compatible.

## Sub-Agent Status

| Agent           | Status      | Description                                      |
| --------------- | ----------- | ------------------------------------------------ |
| Main Agent      | Implemented | Inline editing, intent classification, delegation|
| Research Agent  | Stub        | Will search papers, read full text, follow citations |
| Figure Agent    | Stub        | Will generate plots and TikZ diagrams via code execution |
| Review Agent    | Stub        | Will simulate peer review and validate checklists |

The Main Agent's delegation logic is fully wired -- when a user request matches a sub-agent domain (e.g. "find related work"), it routes to the stub, which returns a placeholder describing planned capabilities. When sub-agents are implemented, no changes to the Main Agent or API layer are needed.
