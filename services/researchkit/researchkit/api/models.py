"""Request/response Pydantic models for the API layer."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    project_id: str
    user_id: str = ""
    message: str
    selected_text: str = ""
    current_file: str = ""
    files: dict[str, str] = Field(
        default_factory=dict,
        description="Optional: project files as {relative_path: content}",
    )
    stream: bool = True
    config: dict | None = None


class ChatResponse(BaseModel):
    status: str
    content: str
    artifacts: list[dict] = Field(default_factory=list)
    confidence: float = 0.0
    needs_human_review: bool = False


class IndexRequest(BaseModel):
    project_id: str
    files: dict[str, str] = Field(
        description="Project files as {relative_path: content}"
    )
    config: dict | None = None


class IndexResponse(BaseModel):
    status: str
    paper_summary: str = ""
    sections: list[dict] = Field(default_factory=list)
    citation_count: int = 0


class MemoryResponse(BaseModel):
    paper_summary: str = ""
    structure: dict = Field(default_factory=dict)
    research_questions: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    venue: dict = Field(default_factory=dict)
    citation_count: int = 0
