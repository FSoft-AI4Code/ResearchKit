# ResearchKit Architecture

## Summary

ResearchKit is layered on top of Overleaf Community Edition. It treats Overleaf as the IDE and the LaTeX paper project as the codebase. The Overleaf module owns UI integration and project-file capture, while the Python service owns agent execution, memory, provider configuration, and persistence. A separate runner service executes shell commands against an overlay workspace and returns structured diffs.

![ResearchKit Architecture Overview](../doc/ResearchKit-architecture-overview.jpg)

*Overview image of the current ResearchKit architecture. Overleaf is the IDE surface, and the LaTeX paper workspace is the codebase the agents operate on.*

## Runtime Topology

```text
Browser
  -> Overleaf web app
     -> ResearchKit React panel and rail entry
     -> Express proxy routes in services/web/modules/researchkit
        -> ResearchKit FastAPI service
           -> MainAgent
           -> ResearchAgent / FigureAgent / ReviewAgent
           -> MemoryManager
           -> provider registry
           -> MongoDB
           -> ResearchKit runner
```

## Main Components

### Overleaf module

- The frontend lives in `services/web/modules/researchkit/frontend/`.
- The proxy/controller layer lives in `services/web/modules/researchkit/app/src/`.
- Conceptually, this layer turns Overleaf into the IDE surface for ResearchKit.
- Before sending chat or indexing requests, the controller flushes project documents and builds a file snapshot from Overleaf's internal document storage.
- The controller can override the active file content with unsaved in-editor text so the backend sees the latest user state.

### LaTeX project as codebase

- ResearchKit treats the active paper like a codebase rather than a single document.
- `main.tex`, included section files, `.bib` files, and figure assets form the working project tree the agents reason over.
- This framing drives the tool model:
  - editor context is captured like IDE state
  - file operations are explicit and patch-oriented
  - workspace inspection and command execution are treated similarly to coding-agent workflows

### FastAPI service

- Entry point: `services/researchkit/researchkit/main.py`
- Routes: `services/researchkit/researchkit/api/routes.py`
- Schemas: `services/researchkit/researchkit/api/models.py`
- The service exposes health, chat, memory, conversation, config, config-test, and model-discovery endpoints under `/api`.
- Chat responses are streamed back as SSE events.

### Main Agent

- `MainAgent` is the primary orchestrator for editor-facing requests.
- It loads project memory into the system prompt, appends workspace context, restores the scoped conversation, and runs a tool loop through the configured provider.
- It reasons about the paper workspace the way a coding agent reasons about a project repository.
- Tool surface:
  - `str_replace_editor` for viewing and editing workspace files
  - `bash` for execution-oriented commands only
  - `delegate_to_subagent` for specialized workflows
- Important constraint: file inspection and file mutation are expected to go through `str_replace_editor`, not `bash`.

### Sub-agents

- `research` is implemented and supports literature search, citation verification, BibTeX generation, and read-only workspace inspection.
- `figure` exists as a placeholder.
- `review` exists as a placeholder.

### Memory layer

- `MemoryManager` builds and retrieves `PaperMemory`.
- Current extraction sources:
  - document structure from LaTeX sections
  - venue hints from `\documentclass`
  - abstract extraction
  - citations from `.bib` files
- Memory is rebuilt when the project content hash changes.
- If no abstract is present, summary generation falls back to the configured LLM provider.

### Provider and config layer

- `ProviderConfig` is assembled from three levels:
  - environment defaults
  - per-project MongoDB overrides
  - request-level overrides
- Supported provider types:
  - `openai`
  - `anthropic`
  - `custom` for OpenAI-compatible endpoints
- Project config supports saved encrypted API keys, model selection, runner settings, and workspace configuration.

### Runner service

- Entry point: `services/researchkit/researchkit/runner/main.py`
- The runner creates a temporary workspace, optionally copies a mounted baseline workspace, overlays request files, executes the command, snapshots before/after state, and returns changed files.
- This lets the Main Agent run command-based workflows while still returning explicit patchable file changes to the UI.

## Request Flows

### Chat flow

1. The UI sends the message plus editor context to the Express proxy.
2. The proxy flushes docs to MongoDB, snapshots project files, and forwards the request to `POST /api/chat`.
3. The backend loads config, rebuilds memory if needed, and starts `MainAgent.handle(...)`.
4. The Main Agent emits typed events while tools run.
5. The API converts those internal events to SSE events:
   - `message`
   - `action`
   - `patch`
   - `response`
   - `done`

### Memory indexing flow

1. The UI or proxy calls `POST /api/project/index`.
2. `MemoryManager.build_memory(...)` resolves `\input{}` trees, parses sections and citations, and writes `researchkitMemory`.
3. Subsequent chat requests reuse that memory until the project hash changes.

### Config flow

1. The UI loads config from `GET /api/config/{project_id}`.
2. Updates are saved through `POST /api/config/{project_id}`.
3. Provider health checks use `POST /api/config/{project_id}/test`.
4. Model discovery uses `POST /api/models/{project_id}`.

### Delegation flow

1. The Main Agent calls `delegate_to_subagent`.
2. The selected sub-agent receives `Task`, `PaperMemory`, and `SubAgentContext`.
3. If the delegated work changes files, the Main Agent converts the before/after workspace snapshots into structured patches for the frontend.

## Persistence

ResearchKit currently stores data in three MongoDB collections inside the shared Overleaf database:

- `researchkitMemory`
- `researchkitConversations`
- `researchkitConfig`

## Operational Constraints

- `bash` is for execution-oriented commands such as tests or builds, not repo inspection.
- Workspace editing is gated by configured workspace paths and allowed workspace roots.
- Runner execution happens in a temporary overlay workspace rather than mutating the source tree directly.
- Conversation history is scoped by `project_id` and `conversation_id`, with compatibility logic for older default records.
