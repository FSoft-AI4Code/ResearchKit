from datetime import datetime

from pydantic import BaseModel, Field


class SectionInfo(BaseModel):
    name: str
    level: int = 1  # 1=section, 2=subsection, 3=subsubsection
    status: str = "draft"  # "complete" | "draft" | "empty" | "outline"
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0


class CitationEntry(BaseModel):
    key: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: str = ""
    venue: str = ""


class VenueConfig(BaseModel):
    name: str = ""
    doc_class: str = ""
    page_limit: int | None = None
    anonymous: bool = False


class StyleProfile(BaseModel):
    formality: str = "high"
    notation_conventions: dict[str, str] = Field(default_factory=dict)
    terminology: dict[str, str] = Field(default_factory=dict)


class PaperMemory(BaseModel):
    project_id: str
    paper_summary: str = ""
    structure_map: list[SectionInfo] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    venue: VenueConfig | None = None
    citations: list[CitationEntry] = Field(default_factory=list)
    style_profile: StyleProfile = Field(default_factory=StyleProfile)
    content_hash: str = ""
    last_indexed_at: datetime | None = None
