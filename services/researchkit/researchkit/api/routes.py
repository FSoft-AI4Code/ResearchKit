import json
import logging
import traceback

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from researchkit.agents.main_agent import MainAgent
from researchkit.api.models import (
    ChatRequest,
    ConfigRequest,
    HealthResponse,
    IndexRequest,
    MemoryResponse,
)
from researchkit.config.loader import ConfigLoader
from researchkit.memory.memory import MemoryManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@router.post("/chat")
async def chat(request: ChatRequest):
    config = await ConfigLoader.load(request.project_id, request.config)
    memory_manager = MemoryManager()

    # Auto-build memory if files provided and memory doesn't exist or is stale
    if request.files:
        needs_index = await memory_manager.needs_reindex(request.project_id, request.files)
        if needs_index:
            await memory_manager.build_memory(request.project_id, request.files, config)

    memory = await memory_manager.get_memory(request.project_id)
    agent = MainAgent(config)

    async def event_generator():
        try:
            async for event in agent.handle(
                project_id=request.project_id,
                message=request.message,
                selected_text=request.selected_text,
                memory=memory,
                file_path=request.file_path,
                selection_from=request.selection_from,
                selection_to=request.selection_to,
                cursor_line=request.cursor_line,
                line_from=request.line_from,
                line_to=request.line_to,
                files=request.files,
            ):
                event_type = event.get("type", "text")
                if event_type == "patch":
                    yield {"event": "patch", "data": json.dumps(event["data"])}
                elif event_type == "action":
                    yield {"event": "action", "data": json.dumps(event["data"])}
                elif event_type == "response":
                    yield {"event": "response", "data": json.dumps(event["data"])}
                else:
                    yield {"event": "message", "data": event["data"]}
        except Exception:
            logger.error("Error in chat stream", exc_info=True)
            yield {"event": "message", "data": f"[Error] {traceback.format_exc()}"}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@router.post("/project/index")
async def index_project(request: IndexRequest):
    config = await ConfigLoader.load(request.project_id)
    memory_manager = MemoryManager()
    memory = await memory_manager.build_memory(request.project_id, request.files, config)
    return {"status": "indexed", "project_id": request.project_id, "summary": memory.paper_summary}


@router.get("/memory/{project_id}", response_model=MemoryResponse)
async def get_memory(project_id: str):
    memory_manager = MemoryManager()
    memory = await memory_manager.get_memory(project_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found. Index the project first.")
    return MemoryResponse(
        project_id=memory.project_id,
        paper_summary=memory.paper_summary,
        structure_map=[s.model_dump() for s in memory.structure_map],
        research_questions=memory.research_questions,
        contributions=memory.contributions,
        venue=memory.venue.model_dump() if memory.venue else None,
        citations=[c.model_dump() for c in memory.citations],
        last_indexed_at=memory.last_indexed_at.isoformat() if memory.last_indexed_at else None,
    )


@router.get("/config/{project_id}")
async def get_config(project_id: str):
    config = await ConfigLoader.load(project_id)
    return {
        "provider_type": config.provider_type,
        "base_url": config.base_url,
        "model": config.model,
        "workspace_path": config.workspace_path,
        "runner_url": config.runner_url,
        "bash_default_timeout_seconds": config.bash_default_timeout_seconds,
        "max_tool_iterations": config.max_tool_iterations,
        "tool_output_max_chars": config.tool_output_max_chars,
        "has_api_key": bool(config.api_key),
    }


@router.post("/config/{project_id}")
async def update_config(project_id: str, request: ConfigRequest):
    await ConfigLoader.save(project_id, request)
    return {"status": "updated", "project_id": project_id}
