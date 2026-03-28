import hashlib
from datetime import datetime, timezone

from researchkit.config.schema import ProviderConfig
from researchkit.db import get_db
from researchkit.memory.latex_parser import (
    parse_abstract,
    parse_citations,
    parse_document_class,
    parse_sections,
    resolve_inputs,
)
from researchkit.memory.schema import PaperMemory
from researchkit.providers.registry import create_provider


class MemoryManager:
    def _compute_hash(self, files: dict[str, str]) -> str:
        combined = "".join(f"{k}:{v}" for k, v in sorted(files.items()))
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def needs_reindex(self, project_id: str, files: dict[str, str]) -> bool:
        db = get_db()
        existing = await db.researchkitMemory.find_one(
            {"project_id": project_id}, {"content_hash": 1}
        )
        if existing is None:
            return True
        return existing.get("content_hash") != self._compute_hash(files)

    async def build_memory(
        self, project_id: str, files: dict[str, str], config: ProviderConfig
    ) -> PaperMemory:
        # Find main.tex content
        main_content = files.get("main.tex", "")
        if not main_content:
            for name, content in files.items():
                if name.endswith(".tex") and "\\documentclass" in content:
                    main_content = content
                    break

        # Resolve \input{} to build full document
        full_content = resolve_inputs(main_content, files)

        # Parse LaTeX structure
        sections = parse_sections(full_content)
        venue = parse_document_class(main_content)
        abstract = parse_abstract(full_content)

        # Parse all .bib files for citations
        citations = []
        for name, content in files.items():
            if name.endswith(".bib"):
                citations.extend(parse_citations(content))

        # Generate paper summary via LLM
        paper_summary = await self._generate_summary(full_content, abstract, config)

        memory = PaperMemory(
            project_id=project_id,
            paper_summary=paper_summary,
            structure_map=sections,
            venue=venue,
            citations=citations,
            content_hash=self._compute_hash(files),
            last_indexed_at=datetime.now(timezone.utc),
        )

        # Store in MongoDB
        db = get_db()
        await db.researchkitMemory.update_one(
            {"project_id": project_id},
            {"$set": memory.model_dump(mode="json")},
            upsert=True,
        )

        return memory

    async def get_memory(self, project_id: str) -> PaperMemory | None:
        db = get_db()
        doc = await db.researchkitMemory.find_one({"project_id": project_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return PaperMemory(**doc)

    async def get_context_for_prompt(self, project_id: str) -> str:
        """Format memory as a string for the agent's system prompt."""
        memory = await self.get_memory(project_id)
        if memory is None:
            return "No paper context available. Ask the user to index their project first."

        parts = [f"## Paper Summary\n{memory.paper_summary}"]

        if memory.structure_map:
            section_lines = []
            for s in memory.structure_map:
                indent = "  " * (s.level - 1)
                section_lines.append(f"{indent}- {s.name} ({s.status})")
            parts.append("## Paper Structure\n" + "\n".join(section_lines))

        if memory.research_questions:
            parts.append(
                "## Research Questions\n"
                + "\n".join(f"- {q}" for q in memory.research_questions)
            )

        if memory.contributions:
            parts.append(
                "## Contributions\n"
                + "\n".join(f"- {c}" for c in memory.contributions)
            )

        if memory.venue:
            parts.append(
                f"## Venue\n{memory.venue.name or 'Unknown'} "
                f"(documentclass: {memory.venue.doc_class})"
            )

        if memory.citations:
            cite_lines = [f"- [{c.key}] {c.title} ({c.year})" for c in memory.citations[:20]]
            parts.append("## Citations (top 20)\n" + "\n".join(cite_lines))

        return "\n\n".join(parts)

    async def _generate_summary(
        self, content: str, abstract: str, config: ProviderConfig
    ) -> str:
        """Use LLM to generate a concise paper summary."""
        if abstract:
            # If we have an abstract, use it directly (faster, no LLM call needed)
            return abstract

        # Truncate content to avoid exceeding context limits
        truncated = content[:8000] if len(content) > 8000 else content

        try:
            provider = create_provider(config)
            summary = await provider.complete([
                {
                    "role": "system",
                    "content": "Summarize this academic paper in 3-5 sentences. "
                    "Focus on: what problem it addresses, what method it proposes, "
                    "and what results it achieves.",
                },
                {"role": "user", "content": truncated},
            ])
            return summary
        except Exception:
            return "Paper summary could not be generated. Please check LLM provider config."
