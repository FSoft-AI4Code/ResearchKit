import json
import logging
import traceback
from datetime import datetime
from time import perf_counter

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from researchkit.agents.main_agent import MainAgent
from researchkit.api.models import (
    ChatMessage,
    ChatRequest,
    ConfigRequest,
    ConfigTestRequest,
    ConfigTestResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationSummary,
    HealthResponse,
    IndexRequest,
    MemoryResponse,
    ModelListRequest,
    ModelListResponse,
)
from researchkit.config.loader import ConfigLoader
from researchkit.db import get_db
from researchkit.memory.memory import MemoryManager
from researchkit.providers.model_discovery import ModelDiscoveryError, list_models_for_config
from researchkit.providers.registry import create_provider

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
                conversation_id=request.conversation_id,
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
                if event_type == "edit":
                    # `edit` is an internal agent event; clients consume `action`,
                    # `patch`, `response`, and `done` SSE events.
                    continue
                elif event_type == "patch":
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


@router.get(
    "/conversation/{project_id}",
    response_model=ConversationResponse,
    response_model_exclude_none=True,
)
async def get_conversation(project_id: str, conversation_id: str | None = Query(default=None)):
    normalized_conversation_id = MainAgent._normalize_conversation_id(conversation_id)
    db = get_db()
    query = {
        "project_id": project_id,
        "conversation_id": normalized_conversation_id,
    }

    doc = await db.researchkitConversations.find_one(query)
    if doc is None and normalized_conversation_id == "default":
        # Backward compatibility with documents written before conversation scoping.
        doc = await db.researchkitConversations.find_one({"project_id": project_id})

    raw_messages = doc.get("messages", []) if isinstance(doc, dict) else []
    messages = [
        ChatMessage.model_validate(message)
        for message in MainAgent._normalize_stored_conversation_messages(raw_messages)
    ]
    return ConversationResponse(
        project_id=project_id,
        conversation_id=normalized_conversation_id,
        messages=messages[-20:],
    )


@router.get("/conversation/{project_id}/list", response_model=ConversationListResponse)
async def list_conversations(project_id: str):
    db = get_db()
    cursor = db.researchkitConversations.find({"project_id": project_id}).sort("updated_at", -1)
    docs = await cursor.to_list(length=100)
    summaries: list[ConversationSummary] = []
    seen_conversation_ids: set[str] = set()

    for doc in docs:
        normalized_conversation_id = MainAgent._normalize_conversation_id(
            doc.get("conversation_id")
        )
        if normalized_conversation_id in seen_conversation_ids:
            continue

        raw_messages = doc.get("messages", []) if isinstance(doc, dict) else []
        messages = MainAgent._normalize_stored_conversation_messages(raw_messages)

        last_message_preview = None
        for message in reversed(messages):
            collapsed = " ".join(str(message.get("content", "")).split())
            if collapsed:
                last_message_preview = collapsed[:160]
                break

        updated_at = doc.get("updated_at")
        if isinstance(updated_at, datetime):
            updated_at_iso = updated_at.isoformat()
        elif isinstance(updated_at, str):
            updated_at_iso = updated_at
        else:
            updated_at_iso = None

        summaries.append(
            ConversationSummary(
                conversation_id=normalized_conversation_id,
                updated_at=updated_at_iso,
                message_count=len(messages),
                last_message_preview=last_message_preview,
            )
        )
        seen_conversation_ids.add(normalized_conversation_id)

    return ConversationListResponse(project_id=project_id, conversations=summaries)


@router.delete("/conversation/{project_id}")
async def clear_conversation(project_id: str, conversation_id: str | None = Query(default=None)):
    normalized_conversation_id = MainAgent._normalize_conversation_id(conversation_id)
    db = get_db()
    await db.researchkitConversations.delete_one(
        {
            "project_id": project_id,
            "conversation_id": normalized_conversation_id,
        }
    )
    if normalized_conversation_id == "default":
        # Backward compatibility with documents written before conversation scoping.
        await db.researchkitConversations.delete_one({"project_id": project_id})
    return {
        "status": "cleared",
        "project_id": project_id,
        "conversation_id": normalized_conversation_id,
    }


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
        "has_asta_api_key": bool(config.asta_api_key),
    }


@router.post("/config/{project_id}")
async def update_config(project_id: str, request: ConfigRequest):
    try:
        await ConfigLoader.save(project_id, request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"status": "updated", "project_id": project_id}


@router.post("/config/{project_id}/test", response_model=ConfigTestResponse)
async def test_config(project_id: str, request: ConfigTestRequest):
    requested_provider = request.provider_type.strip() if request.provider_type else None
    requested_api_key = request.api_key.strip() if request.api_key is not None else None
    requested_base_url = request.base_url.strip() if request.base_url is not None else None
    requested_model = request.model.strip() if request.model is not None else None

    try:
        config = await ConfigLoader.load(project_id)
        if requested_provider:
            config.provider_type = requested_provider
        if request.api_key is not None:
            config.api_key = requested_api_key
        if request.base_url is not None:
            config.base_url = requested_base_url or None
        if request.model is not None:
            if not requested_model:
                raise ValueError("Model is required.")
            config.model = requested_model

        if not config.model:
            raise ValueError("Model is required.")

        provider = create_provider(config)
        started = perf_counter()
        response = await provider.complete(
            [
                {"role": "system", "content": "You are a provider configuration validator."},
                {"role": "user", "content": "Reply with exactly: OK"},
            ]
        )
        latency_ms = int((perf_counter() - started) * 1000)
        preview = response.strip()[:200] if isinstance(response, str) else None
        return ConfigTestResponse(
            success=True,
            provider_type=config.provider_type,
            model=config.model,
            latency_ms=latency_ms,
            message="Configuration test succeeded.",
            response_preview=preview or None,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        logger.warning(
            "Provider configuration test failed",
            exc_info=True,
            extra={"project_id": project_id, "provider_type": requested_provider},
        )
        raise HTTPException(status_code=502, detail=f"Provider test failed: {err}") from err


@router.post("/models/{project_id}", response_model=ModelListResponse)
async def list_models(project_id: str, request: ModelListRequest):
    requested_provider = request.provider_type.strip() if request.provider_type else None
    requested_api_key = request.api_key.strip() if request.api_key is not None else None
    requested_base_url = request.base_url.strip() if request.base_url is not None else None
    try:
        config = await ConfigLoader.load(project_id)
        if requested_provider:
            config.provider_type = requested_provider
        if request.api_key is not None:
            config.api_key = requested_api_key
        if request.base_url is not None:
            config.base_url = requested_base_url or None
        models = await list_models_for_config(config)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except ModelDiscoveryError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except Exception as err:
        logger.warning(
            "Model discovery failed",
            exc_info=True,
            extra={"project_id": project_id, "provider_type": requested_provider},
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch models from provider.",
        ) from err

    selected_model = (
        config.model if any(model["id"] == config.model for model in models) else None
    )
    return ModelListResponse(
        provider_type=config.provider_type,
        models=models,
        selected_model=selected_model,
    )
