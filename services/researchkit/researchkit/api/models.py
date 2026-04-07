from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    project_id: str
    message: str
    conversation_id: str | None = None
    selected_text: str | None = None
    file_path: str | None = None
    selection_from: int | None = None
    selection_to: int | None = None
    cursor_line: int | None = None
    line_from: int | None = None
    line_to: int | None = None
    files: dict[str, str] | None = None
    config: dict | None = None


class EditPatch(BaseModel):
    """A structured edit to be applied to the editor."""
    file_path: str
    selection_from: int
    selection_to: int
    original_text: str
    replacement_text: str
    description: str


class ConversationPatch(EditPatch):
    change_type: str | None = None
    action_id: str | None = None
    response_id: str | None = None
    action_sequence: int | None = None
    command_summary: str | None = None


class ConversationAction(BaseModel):
    tool: str
    status: str
    iteration: int
    detail: str
    action_id: str | None = None
    response_id: str | None = None
    sequence: int | None = None
    command: str | None = None
    has_patch: bool | None = None
    patch_count: int | None = None
    artifacts: list[dict[str, Any]] | None = None
    output: str | None = None


class EditEvent(BaseModel):
    tool: str = "str_replace_editor"
    command: str
    path: str
    absolute_path: str | None = None
    status: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str
    response_id: str | None = None
    action_id: str | None = None
    patches: list[ConversationPatch] | None = None
    actions: list[ConversationAction] | None = None


class ConversationResponse(BaseModel):
    project_id: str
    conversation_id: str
    messages: list[ChatMessage]


class ConversationSummary(BaseModel):
    conversation_id: str
    updated_at: str | None = None
    message_count: int = 0
    last_message_preview: str | None = None


class ConversationListResponse(BaseModel):
    project_id: str
    conversations: list[ConversationSummary]


class IndexRequest(BaseModel):
    project_id: str
    files: dict[str, str]  # filename -> content


class MemoryResponse(BaseModel):
    project_id: str
    paper_summary: str
    structure_map: list[dict]
    research_questions: list[str]
    contributions: list[str]
    venue: dict | None = None
    citations: list[dict]
    last_indexed_at: str | None = None


class ConfigRequest(BaseModel):
    provider_type: str = "openai"  # "openai" | "anthropic" | "custom"
    api_key: str | None = None
    clear_api_key: bool = False
    asta_api_key: str | None = None
    clear_asta_api_key: bool = False
    base_url: str | None = None
    model: str = "gpt-4o"
    workspace_path: str | None = None
    runner_url: str | None = None
    bash_default_timeout_seconds: int = 60
    max_tool_iterations: int = 8
    tool_output_max_chars: int = 12000


class ModelListRequest(BaseModel):
    provider_type: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class ModelOption(BaseModel):
    id: str
    label: str


class ModelListResponse(BaseModel):
    provider_type: str
    models: list[ModelOption]
    selected_model: str | None = None


class ConfigTestRequest(BaseModel):
    provider_type: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ConfigTestResponse(BaseModel):
    success: bool
    provider_type: str
    model: str
    latency_ms: int
    message: str
    response_preview: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "researchkit"
