"""Pydantic models for Memory components."""

from pydantic import BaseModel, Field


class SectionInfo(BaseModel):
    name: str
    status: str = "empty"  # "empty" | "draft" | "complete"
    page_estimate: float = 0.0
    subsections: list["SectionInfo"] = Field(default_factory=list)


class PaperStructure(BaseModel):
    sections: list[SectionInfo] = Field(default_factory=list)
    total_pages: float = 0.0


class CitationSummary(BaseModel):
    key: str
    title: str = ""
    authors: str = ""
    year: str = ""
    venue: str = ""
    summary: str = ""
    usage_in_paper: str = ""


class StyleProfile(BaseModel):
    formality: str = "high"
    notation_conventions: dict[str, str] = Field(default_factory=dict)
    terminology: dict[str, str] = Field(default_factory=dict)


class VenueContext(BaseModel):
    name: str = ""
    type: str = "long-paper"
    page_limit: int = 8
    required_sections: list[str] = Field(default_factory=list)
    anonymous: bool = True
