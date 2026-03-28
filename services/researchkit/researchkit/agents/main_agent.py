"""Main Agent -- the orchestrator that handles inline editing and delegates to sub-agents."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from researchkit.agents.base import Result, SubAgent, Task, TaskStatus
from researchkit.latex.parser import LaTeXProject
from researchkit.memory.memory import Memory
from researchkit.providers.base import LLMProvider, Message, StreamChunk

logger = logging.getLogger(__name__)

# Intent classification keywords for delegation routing
_RESEARCH_KEYWORDS = {
    "find papers", "related work", "literature", "citation", "cite",
    "evidence for", "search for papers", "survey", "references",
    "who cited", "what papers", "find related", "bibliography",
}
_FIGURE_KEYWORDS = {
    "chart", "plot", "graph", "figure", "diagram", "visualization",
    "bar chart", "line chart", "scatter", "tikz", "architecture diagram",
    "draw", "generate figure", "create figure", "matplotlib",
}
_REVIEW_KEYWORDS = {
    "review", "reviewer", "checklist", "weakness", "strength",
    "peer review", "simulate review", "check paper", "validate",
    "quality check", "rebuttal",
}

_SYSTEM_PROMPT = """\
You are the ResearchKit Main Agent -- an expert academic writing assistant integrated into \
an Overleaf LaTeX editor. You help researchers write, edit, and improve their academic papers.

Your capabilities:
- Inline paraphrase: Rewrite selected text while preserving technical meaning, citations, and notation
- Grammar correction: Academic-specific grammar fixes (hedging, passive voice, vague claims)
- Section drafting: Draft LaTeX sections from outlines or brief descriptions
- BibTeX management: Normalize entries, fix formatting, validate keys
- Format compliance: Check page limits, anonymization, venue requirements
- Coherence analysis: Check logical flow between paragraphs and sections

IMPORTANT RULES:
- Always output valid LaTeX when editing paper content
- Preserve all \\cite{{}} references and their keys exactly
- Maintain the paper's notation conventions and terminology
- Use the paper's style profile for consistency
- When paraphrasing, keep the technical precision -- never simplify meaning
- For grammar fixes, prefer academic register (not conversational)

{memory_context}

{paper_context}
"""

_INLINE_SYSTEM = """\
You are performing an inline edit on a LaTeX paper. Return ONLY the edited text, \
no explanations or markdown wrappers. Preserve all LaTeX commands, citations, and formatting."""

_CLASSIFICATION_PROMPT = """\
Classify the following user request into one of these categories:
- "inline": Can be handled with a direct text edit (paraphrase, grammar, drafting, formatting)
- "research": Requires literature search, citation finding, or evidence gathering
- "figure": Requires generating charts, plots, diagrams, or visual assets
- "review": Requires simulated peer review, quality assessment, or checklist validation

User request: {request}

Respond with ONLY the category name, nothing else."""


class MainAgent:
    """The orchestrator. Handles inline tasks directly, delegates complex tasks to sub-agents."""

    def __init__(
        self,
        provider: LLMProvider,
        sub_agents: dict[str, SubAgent] | None = None,
        memory: Memory | None = None,
    ):
        self.provider = provider
        self.sub_agents = sub_agents or {}
        self.memory = memory or Memory()

    async def handle(
        self,
        user_message: str,
        *,
        selected_text: str = "",
        current_file: str = "",
        project: LaTeXProject | None = None,
    ) -> Result:
        """Handle a user request -- either inline or delegated."""
        intent = await self._classify_intent(user_message)
        logger.info("Classified intent: %s for message: %s", intent, user_message[:80])

        if intent == "inline":
            return await self._handle_inline(
                user_message,
                selected_text=selected_text,
                current_file=current_file,
                project=project,
            )
        else:
            return await self._handle_delegation(
                intent, user_message, project=project
            )

    async def handle_stream(
        self,
        user_message: str,
        *,
        selected_text: str = "",
        current_file: str = "",
        project: LaTeXProject | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Handle a user request with streaming response."""
        intent = await self._classify_intent(user_message)
        logger.info("Classified intent (stream): %s for: %s", intent, user_message[:80])

        if intent == "inline":
            async for chunk in self._stream_inline(
                user_message,
                selected_text=selected_text,
                current_file=current_file,
                project=project,
            ):
                yield chunk
        else:
            result = await self._handle_delegation(
                intent, user_message, project=project
            )
            yield StreamChunk(content=result.content, finish_reason="stop")

    async def _classify_intent(self, user_message: str) -> str:
        """Classify whether a request is inline or needs delegation."""
        msg_lower = user_message.lower()

        for keyword in _RESEARCH_KEYWORDS:
            if keyword in msg_lower:
                return "research"
        for keyword in _FIGURE_KEYWORDS:
            if keyword in msg_lower:
                return "figure"
        for keyword in _REVIEW_KEYWORDS:
            if keyword in msg_lower:
                return "review"

        # If keyword matching is ambiguous, use LLM classification
        try:
            resp = await self.provider.complete(
                [Message(role="user", content=_CLASSIFICATION_PROMPT.format(request=user_message))],
                temperature=0.0,
                max_tokens=20,
            )
            category = resp.content.strip().lower().strip('"').strip("'")
            if category in ("inline", "research", "figure", "review"):
                return category
        except Exception:
            logger.exception("Intent classification failed, defaulting to inline")

        return "inline"

    def _build_system_prompt(
        self,
        selected_text: str = "",
        current_file: str = "",
        project: LaTeXProject | None = None,
    ) -> str:
        memory_section = ""
        if self.memory.paper_summary:
            ctx = self.memory.get_context_for_agent("main_agent")
            memory_section = f"Paper context:\n{json.dumps(ctx, indent=2, default=str)}"

        paper_section = ""
        if selected_text:
            paper_section = f"Currently selected text:\n```latex\n{selected_text}\n```"
        elif current_file:
            truncated = current_file[:8000]
            paper_section = f"Current file content:\n```latex\n{truncated}\n```"

        return _SYSTEM_PROMPT.format(
            memory_context=memory_section,
            paper_context=paper_section,
        )

    async def _handle_inline(
        self,
        user_message: str,
        *,
        selected_text: str = "",
        current_file: str = "",
        project: LaTeXProject | None = None,
    ) -> Result:
        """Handle an inline editing request directly."""
        system = self._build_system_prompt(selected_text, current_file, project)
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user_message),
        ]

        resp = await self.provider.complete(messages, temperature=0.4, max_tokens=4096)

        return Result(
            status=TaskStatus.COMPLETED,
            content=resp.content,
        )

    async def _stream_inline(
        self,
        user_message: str,
        *,
        selected_text: str = "",
        current_file: str = "",
        project: LaTeXProject | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream an inline editing response."""
        system = self._build_system_prompt(selected_text, current_file, project)
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user_message),
        ]

        async for chunk in self.provider.stream(messages, temperature=0.4, max_tokens=4096):
            yield chunk

    async def _handle_delegation(
        self,
        intent: str,
        user_message: str,
        *,
        project: LaTeXProject | None = None,
    ) -> Result:
        """Delegate to the appropriate sub-agent."""
        agent = self.sub_agents.get(f"{intent}_agent")
        if not agent:
            return Result(
                status=TaskStatus.FAILED,
                content=f"No {intent} agent available. The {intent.title()} Agent is a placeholder "
                f"and will be fully implemented in a future update.",
                error=f"missing_{intent}_agent",
            )

        task = self._prepare_task(intent, user_message, project)

        try:
            result = await agent.execute(task, self.memory)
            return await agent.validate(result)
        except Exception as e:
            logger.exception("Sub-agent %s failed", intent)
            return Result(
                status=TaskStatus.FAILED,
                content=f"The {intent.title()} Agent encountered an error: {e}",
                error=str(e),
            )

    def _prepare_task(
        self,
        intent: str,
        user_message: str,
        project: LaTeXProject | None = None,
    ) -> Task:
        """Package context into a structured Task for a sub-agent."""
        memory_context = self.memory.get_context_for_agent(f"{intent}_agent")

        context: dict[str, Any] = {
            "user_message": user_message,
        }

        if project:
            context["project_files"] = {
                name: content[:5000] for name, content in list(project._files.items())[:20]
            }

        if intent == "research":
            context["existing_citations"] = list(self.memory.citation_context.keys())
            return Task(
                action="research_request",
                context=context,
                constraints={
                    "max_papers": 20,
                    "recency_bias": 0.7,
                    "read_depth": "full",
                },
                memory_context=memory_context,
            )
        elif intent == "figure":
            return Task(
                action="figure_request",
                context=context,
                constraints={
                    "output_format": "pdf",
                    "save_scripts": True,
                },
                memory_context=memory_context,
            )
        elif intent == "review":
            return Task(
                action="review_request",
                context=context,
                constraints={
                    "venue_checklist": "auto",
                    "severity_threshold": "minor",
                },
                memory_context=memory_context,
            )

        return Task(action=f"{intent}_request", context=context, memory_context=memory_context)
