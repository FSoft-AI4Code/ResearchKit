import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from researchkit.agents.base import Task
from researchkit.agents.figure_agent import FigureAgent
from researchkit.agents.research_agent import ResearchAgent
from researchkit.agents.review_agent import ReviewAgent
from researchkit.agents.tools import AGENT_TOOLS
from researchkit.config.schema import ProviderConfig
from researchkit.db import get_db
from researchkit.memory.memory import MemoryManager
from researchkit.memory.schema import PaperMemory
from researchkit.providers.registry import create_provider

SYSTEM_PROMPT_TEMPLATE = """\
You are ResearchKit's Main Agent — an AI assistant specialized in academic paper writing.
You work inside Overleaf and help researchers write, edit, and improve their LaTeX papers.

## Your Role
You are the researcher's primary writing companion, like Cursor's inline agent but for academic papers.
You handle inline editing tasks directly and delegate deeper work to specialized sub-agents.

## Direct Capabilities (handle these yourself)
- **Paraphrase**: Rewrite text to improve clarity while preserving technical meaning and citations.
- **Grammar correction**: Fix academic writing issues — hedging, passive voice overuse, vague claims.
- **Section drafting**: Draft LaTeX sections based on outlines and paper context.
- **BibTeX management**: Normalize entries, fix formatting, resolve duplicate keys.
- **Coherence analysis**: Check logical flow between paragraphs and sections.
- **General Q&A**: Answer questions about the paper, LaTeX formatting, academic writing.

## When to Delegate (use the delegate_to_subagent tool)
- **Literature search, finding related work, citation discovery** → delegate to "research" agent
- **Figure generation, chart creation, diagram drawing** → delegate to "figure" agent
- **Paper review, quality checking, checklist validation** → delegate to "review" agent

## Paper Context
{memory_context}

## Instructions
- Always respond in the context of academic paper writing.
- When the user selects text, your edits should be in LaTeX format, ready to paste into the document.
- Use the appropriate tool when performing structured edits (paraphrase, grammar fix, etc.).
- For conversational questions, respond directly without tools.
- When delegating, always use the delegate_to_subagent tool.
- Preserve all LaTeX commands, citations (\\cite{{}}), math notation, and cross-references.
- Match the paper's existing style and terminology from the context above.
"""


class MainAgent:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.provider = create_provider(config)
        self.sub_agents = {
            "research": ResearchAgent(),
            "figure": FigureAgent(),
            "review": ReviewAgent(),
        }

    async def handle(
        self,
        project_id: str,
        message: str,
        selected_text: str | None,
        memory: PaperMemory | None,
        file_path: str | None = None,
        selection_from: int | None = None,
        selection_to: int | None = None,
    ) -> AsyncIterator[dict]:
        """Handle a chat message. Yields typed event dicts:
        - {"type": "text", "data": "chunk"}
        - {"type": "patch", "data": {EditPatch fields}}
        """
        # Build system prompt with memory context
        memory_manager = MemoryManager()
        memory_context = await memory_manager.get_context_for_prompt(project_id)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(memory_context=memory_context)

        # Load conversation history
        conversation = await self._load_conversation(project_id)

        # Build user message
        user_content = message
        if selected_text:
            user_content = (
                f"**Selected text from the paper:**\n```latex\n{selected_text}\n```\n\n"
                f"**Request:** {message}"
            )

        conversation.append({"role": "user", "content": user_content})

        # Try tool-calling completion first to check if agent wants to use tools
        messages_with_system = [{"role": "system", "content": system_prompt}] + conversation

        try:
            tool_response = await self.provider.complete_with_tools(
                messages_with_system, AGENT_TOOLS
            )
        except Exception:
            # If tool calling fails, fall back to streaming without tools
            tool_response = None

        if tool_response and tool_response.get("tool_calls"):
            # Handle tool calls — yields text and patch events
            response_text = ""
            async for event in self._handle_tool_calls(
                tool_response, memory, project_id,
                selected_text=selected_text,
                file_path=file_path,
                selection_from=selection_from,
                selection_to=selection_to,
            ):
                if event["type"] == "text":
                    response_text += event["data"]
                yield event
            # Save to conversation
            conversation.append({"role": "assistant", "content": response_text})
            await self._save_conversation(project_id, conversation)
        else:
            # Stream regular response
            full_response = ""
            async for chunk in self.provider.stream(messages_with_system):
                full_response += chunk
                yield {"type": "text", "data": chunk}

            # Save to conversation
            conversation.append({"role": "assistant", "content": full_response})
            await self._save_conversation(project_id, conversation)

    async def _handle_tool_calls(
        self,
        tool_response: dict,
        memory: PaperMemory | None,
        project_id: str,
        selected_text: str | None = None,
        file_path: str | None = None,
        selection_from: int | None = None,
        selection_to: int | None = None,
    ) -> AsyncIterator[dict]:
        """Process tool calls. Yields typed event dicts (text and patch)."""
        has_output = False
        can_patch = (
            selected_text is not None
            and file_path is not None
            and selection_from is not None
            and selection_to is not None
        )

        if tool_response.get("content"):
            has_output = True
            yield {"type": "text", "data": tool_response["content"]}

        for tool_call in tool_response.get("tool_calls", []):
            func_name = tool_call["function"]["name"]
            try:
                args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                has_output = True
                yield {"type": "text", "data": f"Error parsing tool arguments for {func_name}"}
                continue

            if func_name == "delegate_to_subagent":
                agent_type = args.get("agent_type", "")
                task_desc = args.get("task_description", "")
                agent = self.sub_agents.get(agent_type)
                if agent:
                    task = Task(type=agent_type, description=task_desc)
                    result = await agent.execute(task, memory)
                    has_output = True
                    yield {"type": "text", "data": result.content}
                else:
                    has_output = True
                    yield {"type": "text", "data": f"Unknown sub-agent: {agent_type}"}

            elif func_name == "paraphrase_text":
                rewritten = args.get("rewritten_text", "")
                has_output = True
                if can_patch:
                    yield {
                        "type": "patch",
                        "data": {
                            "file_path": file_path,
                            "selection_from": selection_from,
                            "selection_to": selection_to,
                            "original_text": selected_text,
                            "replacement_text": rewritten,
                            "description": "Paraphrased text",
                        },
                    }
                    yield {"type": "text", "data": "**Paraphrased text** — review the diff above to accept or reject."}
                else:
                    yield {"type": "text", "data": f"**Paraphrased text:**\n```latex\n{rewritten}\n```"}

            elif func_name == "fix_grammar":
                corrected = args.get("corrected_text", "")
                changes = args.get("changes_made", [])
                has_output = True
                if can_patch:
                    desc = "Grammar correction"
                    if changes:
                        desc += ": " + "; ".join(changes[:3])
                    yield {
                        "type": "patch",
                        "data": {
                            "file_path": file_path,
                            "selection_from": selection_from,
                            "selection_to": selection_to,
                            "original_text": selected_text,
                            "replacement_text": corrected,
                            "description": desc,
                        },
                    }
                    text = "**Grammar corrected** — review the diff above to accept or reject."
                    if changes:
                        text += "\n\n**Changes made:**\n" + "\n".join(f"- {c}" for c in changes)
                    yield {"type": "text", "data": text}
                else:
                    text = f"**Corrected text:**\n```latex\n{corrected}\n```"
                    if changes:
                        text += "\n\n**Changes made:**\n" + "\n".join(f"- {c}" for c in changes)
                    yield {"type": "text", "data": text}

            elif func_name == "draft_section":
                content = args.get("section_content", "")
                has_output = True
                if can_patch:
                    yield {
                        "type": "patch",
                        "data": {
                            "file_path": file_path,
                            "selection_from": selection_from,
                            "selection_to": selection_to,
                            "original_text": selected_text,
                            "replacement_text": content,
                            "description": "Drafted section",
                        },
                    }
                    yield {"type": "text", "data": "**Section drafted** — review the diff above to accept or reject."}
                else:
                    yield {"type": "text", "data": f"**Drafted section:**\n```latex\n{content}\n```"}

            elif func_name == "format_bibtex":
                formatted = args.get("formatted_bibtex", "")
                has_output = True
                if can_patch:
                    yield {
                        "type": "patch",
                        "data": {
                            "file_path": file_path,
                            "selection_from": selection_from,
                            "selection_to": selection_to,
                            "original_text": selected_text,
                            "replacement_text": formatted,
                            "description": "Formatted BibTeX",
                        },
                    }
                    yield {"type": "text", "data": "**BibTeX formatted** — review the diff above to accept or reject."}
                else:
                    yield {"type": "text", "data": f"**Formatted BibTeX:**\n```bibtex\n{formatted}\n```"}

        if not has_output:
            yield {"type": "text", "data": "I processed your request but had no output."}

    async def _load_conversation(self, project_id: str) -> list[dict]:
        """Load conversation history from MongoDB."""
        db = get_db()
        doc = await db.researchkitConversations.find_one({"project_id": project_id})
        if doc and doc.get("messages"):
            # Keep last 20 messages to avoid context overflow
            return doc["messages"][-20:]
        return []

    async def _save_conversation(self, project_id: str, messages: list[dict]) -> None:
        """Save conversation history to MongoDB."""
        db = get_db()
        await db.researchkitConversations.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "project_id": project_id,
                    "messages": messages[-20:],  # Keep last 20
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
