"""Memory system -- persistent paper context, the 'codebase index' for research."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

from researchkit.memory.schema import (
    CitationSummary,
    PaperStructure,
    SectionInfo,
    StyleProfile,
    VenueContext,
)

if TYPE_CHECKING:
    from researchkit.latex.parser import LaTeXProject
    from researchkit.providers.base import LLMProvider

MEMORY_DIR = ".researchkit"
MEMORY_FILE = "memory.yaml"

_SUMMARY_PROMPT = """\
You are a research paper analyst. Given the following LaTeX paper content, produce a concise \
summary (3-5 sentences) describing what the paper is about, its main contributions, and methodology.

Paper content:
{content}

Respond with ONLY the summary, no preamble."""

_STRUCTURE_PROMPT = """\
Analyze the following LaTeX paper and extract its section structure.
For each section, estimate its completion status: "complete" if it has substantial content, \
"draft" if it has some content but appears incomplete, "empty" if it has no content or only TODOs.

Paper content:
{content}

Respond in YAML format:
sections:
  - name: "Section Name"
    status: complete|draft|empty
    page_estimate: 1.5
"""


class Memory(BaseModel):
    """Persistent paper context -- shared across all agents."""

    paper_summary: str = ""
    structure: PaperStructure = Field(default_factory=PaperStructure)
    research_questions: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    venue: VenueContext = Field(default_factory=VenueContext)
    citation_context: dict[str, CitationSummary] = Field(default_factory=dict)
    style_profile: StyleProfile = Field(default_factory=StyleProfile)

    async def update_from_project(
        self,
        project: LaTeXProject,
        provider: LLMProvider | None = None,
    ) -> None:
        """Re-index the paper after edits.

        Extracts structure from the LaTeX project. If an LLM provider is given,
        also generates a paper summary.
        """
        from researchkit.providers.base import Message

        sections = project.get_sections()
        self.structure = PaperStructure(
            sections=[
                SectionInfo(
                    name=s.name,
                    status=self._estimate_status(s.content),
                    page_estimate=round(len(s.content) / 3000, 1),
                )
                for s in sections
            ]
        )

        citations = project.get_citations()
        for cite in citations:
            if cite.key not in self.citation_context:
                self.citation_context[cite.key] = CitationSummary(
                    key=cite.key,
                    title=cite.title,
                    authors=cite.authors,
                    year=cite.year,
                )

        if provider:
            full_text = project.get_full_text()
            truncated = full_text[:15000]
            resp = await provider.complete(
                [Message(role="user", content=_SUMMARY_PROMPT.format(content=truncated))],
                temperature=0.3,
                max_tokens=500,
            )
            self.paper_summary = resp.content.strip()

    @staticmethod
    def _estimate_status(content: str) -> str:
        stripped = content.strip()
        if not stripped or len(stripped) < 50:
            return "empty"
        if len(stripped) < 500 or "TODO" in content or "\\todo" in content:
            return "draft"
        return "complete"

    def get_context_for_agent(self, agent_name: str) -> dict[str, Any]:
        """Return the relevant subset of memory for a specific agent."""
        base = {
            "paper_summary": self.paper_summary,
            "venue": self.venue.model_dump(),
            "style_profile": self.style_profile.model_dump(),
        }

        if agent_name == "main_agent":
            base["structure"] = self.structure.model_dump()
            base["research_questions"] = self.research_questions
            base["contributions"] = self.contributions
        elif agent_name == "research_agent":
            base["research_questions"] = self.research_questions
            base["contributions"] = self.contributions
            base["citation_context"] = {
                k: v.model_dump() for k, v in self.citation_context.items()
            }
        elif agent_name == "figure_agent":
            base["structure"] = self.structure.model_dump()
        elif agent_name == "review_agent":
            base["structure"] = self.structure.model_dump()
            base["research_questions"] = self.research_questions
            base["contributions"] = self.contributions
            base["citation_context"] = {
                k: v.model_dump() for k, v in self.citation_context.items()
            }

        return base

    def to_yaml(self) -> str:
        data = self.model_dump()
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> Memory:
        data = yaml.safe_load(yaml_str) or {}
        return cls.model_validate(data)

    def save(self, project_dir: str | Path) -> Path:
        mem_dir = Path(project_dir) / MEMORY_DIR
        mem_dir.mkdir(parents=True, exist_ok=True)
        mem_path = mem_dir / MEMORY_FILE
        mem_path.write_text(self.to_yaml(), encoding="utf-8")
        return mem_path

    @classmethod
    def load(cls, project_dir: str | Path) -> Memory:
        mem_path = Path(project_dir) / MEMORY_DIR / MEMORY_FILE
        if mem_path.exists():
            return cls.from_yaml(mem_path.read_text(encoding="utf-8"))
        return cls()
