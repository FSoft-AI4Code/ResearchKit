# ResearchKit Feature Status

## Summary

This page reflects the current implementation in the repository and the tested backend behavior. It is intentionally narrower than the long-term product vision.

## Implemented Now

### Core product framing

- Overleaf is used as the IDE surface for the writing workflow
- The LaTeX project is treated as a codebase the agents can inspect, summarize, patch, and reason about file-by-file

### Editor integration

- ResearchKit rail entry and right-side panel inside the Overleaf editor
- Message list and message input components
- Capture of active file, selected text, selection range, and cursor line
- Streaming UI fed by SSE responses from the backend

### Conversation workflow

- Per-project conversation persistence
- Resume an existing conversation from the panel
- Start a new conversation
- Clear a conversation
- Conversation list summaries with last-message preview

### Project memory

- Manual project indexing from the UI
- Automatic reindex checks during chat when files are provided
- LaTeX structure extraction
- Abstract extraction
- Venue hint extraction from `\documentclass`
- BibTeX citation extraction
- Stored project summary and structure map in MongoDB

### Provider configuration

- OpenAI provider support
- Anthropic provider support
- Custom OpenAI-compatible provider support
- Per-project provider settings
- Encrypted saved API keys at rest
- Provider connectivity test endpoint
- Model discovery endpoint and UI

### Main Agent workflow

- Workspace-aware prompting with memory and file context
- Scoped conversation restore and save
- File viewing and editing through `str_replace_editor`
- Patch generation for frontend review
- Execution-only bash commands through the runner service
- Sub-agent delegation interface

### Research Agent

- Implemented research sub-agent
- Literature search through ASTA MCP
- Citation verification flow
- BibTeX generation from discovered papers
- Read-only workspace inspection for context-aware research tasks
- ReAct-style tool loop with iteration limits

### Runner service

- Temporary overlay workspace creation
- Optional baseline workspace copy
- File overlay injection from request payload
- Command execution with timeout limits
- Before/after text snapshot diffing
- Structured changed-file response for patch conversion

## Partially Implemented or Configuration-Dependent

- Research workflows are strongest when `RESEARCHKIT_ASTA_API_KEY` is configured.
- Bash-backed workflows require runner configuration and a valid workspace path.
- Memory summaries fall back to the LLM provider when no abstract is available.
- Request-level config overrides exist, but most users will interact through the saved project config UI.

## Present but Still Placeholder

- Figure Agent
  - class exists
  - returns placeholder content only

- Review Agent
  - class exists
  - returns placeholder content only

## Verified Backend Coverage

The backend test suite currently covers:

- API routes
- config loading and encrypted secret handling
- main-agent tool behavior
- research-agent tool loop behavior
- runner client parsing
- read/edit guardrails in `str_replace_editor`

Current observed baseline: `67 passed`.
