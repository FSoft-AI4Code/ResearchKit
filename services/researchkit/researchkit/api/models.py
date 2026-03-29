from pydantic import BaseModel


class ChatRequest(BaseModel):
    project_id: str
    message: str
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


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


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
    base_url: str | None = None
    model: str = "gpt-4o"
    workspace_path: str | None = None
    runner_url: str | None = None
    bash_default_timeout_seconds: int = 60
    max_tool_iterations: int = 8
    tool_output_max_chars: int = 12000


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "researchkit"
