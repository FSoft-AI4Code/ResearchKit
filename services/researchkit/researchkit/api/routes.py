"""FastAPI routes for the ResearchKit service."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from researchkit.agents.base import TaskStatus
from researchkit.agents.figure_agent import FigureAgent
from researchkit.agents.main_agent import MainAgent
from researchkit.agents.research_agent import ResearchAgent
from researchkit.agents.review_agent import ReviewAgent
from researchkit.api.models import (
    ChatRequest,
    ChatResponse,
    IndexRequest,
    IndexResponse,
    MemoryResponse,
)
from researchkit.config.loader import load_config_from_dict
from researchkit.config.schema import ResearchKitConfig
from researchkit.latex.parser import LaTeXProject
from researchkit.memory.memory import Memory
from researchkit.providers.registry import create_provider

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory state keyed by project_id. In production this would use a proper store.
_project_state: dict[str, dict[str, Any]] = {}


def _get_or_create_state(project_id: str, config: dict | None = None) -> dict[str, Any]:
    if project_id not in _project_state:
        cfg = load_config_from_dict(config) if config else ResearchKitConfig()
        main_provider = create_provider(cfg.providers.main_agent)

        sub_agents = {
            "research_agent": ResearchAgent(create_provider(cfg.providers.research_agent)),
            "figure_agent": FigureAgent(create_provider(cfg.providers.figure_agent)),
            "review_agent": ReviewAgent(create_provider(cfg.providers.review_agent)),
        }

        memory = Memory()
        if cfg.project.venue:
            from researchkit.memory.schema import VenueContext

            memory.venue = VenueContext(
                name=cfg.project.venue,
                type=cfg.project.type,
                page_limit=cfg.project.page_limit,
                anonymous=cfg.project.anonymous,
            )

        agent = MainAgent(provider=main_provider, sub_agents=sub_agents, memory=memory)

        _project_state[project_id] = {
            "config": cfg,
            "memory": memory,
            "agent": agent,
            "project": None,
        }

    return _project_state[project_id]


@router.get("/health")
async def health():
    return {"status": "ok", "service": "researchkit"}


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to the Main Agent. Supports streaming via SSE."""
    state = _get_or_create_state(req.project_id, req.config)
    agent: MainAgent = state["agent"]

    project = None
    if req.files:
        project = LaTeXProject(files=req.files)
        state["project"] = project
    elif state["project"]:
        project = state["project"]

    if req.stream:
        return StreamingResponse(
            _stream_chat(agent, req, project),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await agent.handle(
        req.message,
        selected_text=req.selected_text,
        current_file=req.current_file,
        project=project,
    )

    return ChatResponse(
        status=result.status.value,
        content=result.content,
        artifacts=[a.__dict__ for a in result.artifacts],
        confidence=result.confidence,
        needs_human_review=result.needs_human_review,
    )


async def _stream_chat(agent: MainAgent, req: ChatRequest, project: LaTeXProject | None):
    """SSE streaming generator for chat responses."""
    try:
        async for chunk in agent.handle_stream(
            req.message,
            selected_text=req.selected_text,
            current_file=req.current_file,
            project=project,
        ):
            data = json.dumps({"content": chunk.content, "finish_reason": chunk.finish_reason})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("Streaming error")
        error_data = json.dumps({"error": str(e)})
        yield f"data: {error_data}\n\n"


@router.post("/project/index", response_model=IndexResponse)
async def index_project(req: IndexRequest):
    """Receive LaTeX project files and build/update Memory."""
    state = _get_or_create_state(req.project_id, req.config)
    memory: Memory = state["memory"]
    agent: MainAgent = state["agent"]

    project = LaTeXProject(files=req.files)
    state["project"] = project

    try:
        await memory.update_from_project(project, provider=agent.provider)
    except Exception:
        logger.exception("Memory indexing failed, continuing with structural data only")
        await memory.update_from_project(project, provider=None)

    return IndexResponse(
        status="indexed",
        paper_summary=memory.paper_summary,
        sections=[s.model_dump() for s in memory.structure.sections],
        citation_count=len(memory.citation_context),
    )


@router.get("/memory", response_model=MemoryResponse)
async def get_memory(project_id: str):
    """Return current Memory state for a project."""
    if project_id not in _project_state:
        raise HTTPException(status_code=404, detail="Project not indexed yet")

    memory: Memory = _project_state[project_id]["memory"]
    return MemoryResponse(
        paper_summary=memory.paper_summary,
        structure=memory.structure.model_dump(),
        research_questions=memory.research_questions,
        contributions=memory.contributions,
        venue=memory.venue.model_dump(),
        citation_count=len(memory.citation_context),
    )
