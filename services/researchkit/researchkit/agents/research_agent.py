"""Research Agent stub -- placeholder for deep literature discovery.

When fully implemented, this agent will:
- Search Semantic Scholar, ArXiv, Google Scholar for seed papers
- Prioritize survey papers as field maps
- Read FULL papers (not just abstracts) via PDF parsing
- Follow forward/backward citation graphs (configurable depth)
- Match claims to evidence from the literature
- Generate structured related work sections with proper citations
- Validate all BibTeX entries against real sources
"""

from __future__ import annotations

from typing import Any

from researchkit.agents.base import Artifact, Result, SubAgent, Task, TaskStatus
from researchkit.memory.memory import Memory
from researchkit.providers.base import LLMProvider


class ResearchAgent(SubAgent):
    name = "research_agent"
    description = "Deep literature discovery with full-paper reading and citation graph traversal"

    # Tools this agent will use when fully implemented
    REQUIRED_TOOLS = [
        "SemanticScholarTool",
        "ArXivTool",
        "PDFParserTool",
        "WebSearchTool",
        "GoogleScholarTool",
    ]

    def __init__(self, provider: LLMProvider):
        super().__init__(provider)

    async def plan(self, task: Task, memory: Memory) -> dict[str, Any]:
        return {
            "status": "stub",
            "steps": [
                "1. Seed discovery via web search",
                "2. Deep read of seed papers (full text)",
                "3. Forward citation graph traversal",
                "4. Backward citation graph traversal",
                "5. Evidence synthesis and gap analysis",
                "6. BibTeX generation and validation",
            ],
            "note": "Research Agent is not yet implemented. This is a planned execution flow.",
        }

    async def execute(self, task: Task, memory: Memory) -> Result:
        user_msg = task.context.get("user_message", "research request")

        return Result(
            status=TaskStatus.COMPLETED,
            content=(
                f"**Research Agent** received your request: \"{user_msg}\"\n\n"
                "This agent is currently a placeholder. When fully implemented, it will:\n\n"
                "1. **Seed Discovery** -- Search Semantic Scholar, ArXiv, and Google Scholar "
                "to find seed papers, especially survey papers that map the field\n"
                "2. **Deep Reading** -- Download and read FULL papers (not just abstracts) "
                "via PDF parsing, focusing on Related Work, Methodology, and Limitations\n"
                "3. **Citation Graph Traversal** -- Follow forward citations (\"who cited this?\") "
                "and backward citations (\"what did this build on?\") up to configurable depth\n"
                "4. **Evidence Matching** -- For each claim in your paper, find supporting or "
                "contradicting evidence from the literature\n"
                "5. **Synthesis** -- Generate a structured related work section with proper "
                "LaTeX citations, grouped by theme, with transitions\n"
                "6. **Validation** -- Verify all BibTeX entries against real sources to prevent "
                "hallucinated references"
            ),
            artifacts=[
                Artifact(
                    type="placeholder_notice",
                    content="Research Agent tools are defined but not yet connected to external APIs.",
                )
            ],
            confidence=0.0,
            needs_human_review=True,
        )
