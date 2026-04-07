import json
import logging
import os
import re
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from researchkit.agents.base import SubAgentContext, Task
from researchkit.agents.figure_agent import FigureAgent
from researchkit.agents.patch_utils import compute_minimal_edit
from researchkit.agents.research_agent import ResearchAgent
from researchkit.agents.review_agent import ReviewAgent
from researchkit.agents.runner_client import RunnerClient
from researchkit.agents.str_replace_editor import WorkspaceStrReplaceEditor
from researchkit.agents.tools import AGENT_TOOLS
from researchkit.agents.workspace_context import build_workspace_context_lines
from researchkit.config.schema import ProviderConfig
from researchkit.db import get_db
from researchkit.memory.memory import MemoryManager
from researchkit.memory.schema import PaperMemory
from researchkit.providers.registry import create_provider

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class EditorRetryState:
    viewed_existing_paths: set[str] = field(default_factory=set)
    must_view_before_edit: dict[str, str] = field(default_factory=dict)
    unresolved_edit_failures: dict[str, str] = field(default_factory=dict)

SYSTEM_PROMPT_TEMPLATE = """\
You are ResearchKit's Main Agent — a AI assistant for academic paper writing.
Treat the paper's files and structure as a codebase.

<IMPORTANT>
This is an iterative workflow:
1) reason briefly
2) use the right tool
3) inspect outputs
4) continue until done.
</IMPORTANT>

For each response:
1. Include concise reasoning about your next step.
2. Include one or more tool calls, or no tool calls only when the task is complete.

Each response should include:
1. **Reasoning text** where you explain your analysis and plan
2. The appropriate tool call(s), or no tool call at all if you have already completed the task.

**CRITICAL REQUIREMENTS:**
- Your response SHOULD include reasoning text explaining what you're doing
- Use `str_replace_editor` for workspace file access:
  - `view` for reading files or directories
  - `create`, `str_replace`, `insert`, and `undo_edit` for file changes
- Prefer `str_replace_editor view` before editing a file unless you
  already have the exact context you need.
- `create` is only for brand-new files. Never use `create` on an existing file.
- If an edit on a file fails, your next editor action on that same file must
  be `view` before any further edit attempt.
- Use `str_replace` only when you have an exact unique match. For large section
  rewrites, re-view the exact current text first and then make a deterministic edit.
- Do not finish the task if the requested file change has not been applied successfully.

## Delegation Policy
- Literature discovery / related work exploration / tasks requiring search capability -> delegate to `research`
- Writing or drafting any paper section (introduction, related work, background, conclusion) where academic literature would strengthen the content -> delegate to `research` first to gather relevant papers, then write using the results
- Any task where the user uses "research" as a verb (e.g. "research and write", "research the topic") and the output is a paper section -> delegate to `research`
- Figure/chart generation workflows beyond shell capability -> delegate to `figure`

## Paper Context
{memory_context}
"""


class MainAgent:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.provider = create_provider(config)
        self.sub_agents = {
            "research": ResearchAgent(config),
            "figure": FigureAgent(),
            "review": ReviewAgent(),
        }
        self.max_tool_iterations = max(config.max_tool_iterations, 1)
        self.default_timeout_seconds = max(config.bash_default_timeout_seconds, 1)
        self.tool_output_max_chars = max(config.tool_output_max_chars, 200)
        self.allowed_workspace_roots = [
            os.path.realpath(root)
            for root in (config.allowed_workspace_roots or [])
            if isinstance(root, str) and root.strip()
        ]
        self._editor_history: dict[str, list[str | None]] = {}
        self._overlay_workspaces: dict[str, tempfile.TemporaryDirectory[str]] = {}

    async def handle(
        self,
        project_id: str,
        message: str,
        conversation_id: str | None,
        selected_text: str | None,
        memory: PaperMemory | None,
        file_path: str | None = None,
        selection_from: int | None = None,
        selection_to: int | None = None,
        cursor_line: int | None = None,
        line_from: int | None = None,
        line_to: int | None = None,
        files: dict[str, str] | None = None,
    ) -> AsyncIterator[dict]:
        """Handle a chat message. Yields typed event dicts:
        - {"type": "text", "data": "chunk"}
        - {"type": "edit", "data": {EditEvent fields}}
        - {"type": "action", "data": {action fields}}
        """
        memory_manager = MemoryManager()
        memory_context = await memory_manager.get_context_for_prompt(project_id)
        logger.info(
            "MainAgent handle start project_id=%s memory_context_chars=%d",
            project_id,
            len(memory_context),
        )
        logger.info(
            "MainAgent memory context project_id=%s context=%s",
            project_id,
            self._truncate(memory_context, 2000),
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(memory_context=memory_context)
        workspace_context = self._build_workspace_prompt_context(
            project_id=project_id,
            files=files,
            file_path=file_path,
        )
        logger.info(
            "MainAgent workspace context project_id=%s context=%s",
            project_id,
            self._truncate(workspace_context, 2000),
        )
        if workspace_context:
            system_prompt += f"\n## Workspace Context\n{workspace_context}"

        normalized_conversation_id = self._normalize_conversation_id(conversation_id)
        persisted_conversation = await self._load_persisted_conversation(
            project_id=project_id,
            conversation_id=normalized_conversation_id,
        )
        conversation = await self._load_conversation(
            project_id=project_id,
            conversation_id=normalized_conversation_id,
        )

        user_content = message
        if selected_text:
            line_info = ""
            if line_from is not None and line_to is not None:
                if line_from == line_to:
                    line_info = f" (line {line_from})"
                else:
                    line_info = f" (lines {line_from}\u2013{line_to})"
            file_info = f" in `{file_path}`" if file_path else ""
            user_content = (
                f"**Selected text{line_info}{file_info}:**\n```latex\n{selected_text}\n```\n\n"
                f"**Request:** {message}"
            )
        elif cursor_line is not None and file_path:
            user_content = (
                f"[Cursor at line {cursor_line} in `{file_path}`]\n\n{message}"
            )

        logger.info(
            "MainAgent user content project_id=%s content=%s",
            project_id,
            self._truncate(user_content, 2000),
        )
        persisted_conversation.append({"role": "user", "content": user_content})
        conversation.append({"role": "user", "content": user_content})
        run_id = f"run-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        response_text = ""
        try:
            try:
                async for event in self._run_tool_loop(
                    system_prompt=system_prompt,
                    conversation=conversation,
                    memory=memory,
                    project_id=project_id,
                    files=files,
                    run_id=run_id,
                    file_path=file_path,
                    selected_text=selected_text,
                    cursor_line=cursor_line,
                    line_from=line_from,
                    line_to=line_to,
                ):
                    if event["type"] == "text":
                        response_text += event["data"]
                    elif event["type"] == "response":
                        if event["data"].get("kind") != "tool_output":
                            response_text += str(event["data"].get("content") or "")
                            self._append_response_to_history(
                                persisted_conversation,
                                event["data"],
                            )
                    elif event["type"] == "action":
                        self._append_action_to_history(
                            persisted_conversation,
                            event["data"],
                        )
                    elif event["type"] == "patch":
                        self._append_patch_to_history(
                            persisted_conversation,
                            event["data"],
                        )
                    yield event
            except Exception:
                logger.exception(
                    "MainAgent tool loop failed; falling back to stream project_id=%s",
                    project_id,
                )
                # Fall back to standard streaming if tool-loop path fails.
                messages_with_system = [{"role": "system", "content": system_prompt}] + conversation
                response_text = ""
                fallback_response_id = f"{run_id}-response-fallback-1"
                async for chunk in self.provider.stream(messages_with_system):
                    response_text += chunk
                    event = self._response_event(
                        response_id=fallback_response_id,
                        content=chunk,
                    )
                    self._append_response_to_history(
                        persisted_conversation,
                        event["data"],
                    )
                    yield event
            await self._save_conversation(
                project_id=project_id,
                conversation_id=normalized_conversation_id,
                messages=persisted_conversation,
            )
            logger.info(
                "MainAgent handle completed project_id=%s response_chars=%d",
                project_id,
                len(response_text),
            )
        finally:
            self._cleanup_overlay_workspace(project_id)

    async def _run_tool_loop(
        self,
        *,
        system_prompt: str,
        conversation: list[dict],
        memory: PaperMemory | None,
        project_id: str,
        files: dict[str, str] | None,
        run_id: str,
        file_path: str | None = None,
        selected_text: str | None = None,
        cursor_line: int | None = None,
        line_from: int | None = None,
        line_to: int | None = None,
    ) -> AsyncIterator[dict]:
        action_sequence = 0
        editor_retry_state = EditorRetryState()
        for iteration in range(self.max_tool_iterations):
            response_id = f"{run_id}-response-{iteration + 1}"
            messages = [{"role": "system", "content": system_prompt}] + conversation
            tool_response = await self.provider.complete_with_tools(messages, AGENT_TOOLS)

            assistant_content = tool_response.get("content") or ""
            if assistant_content:
                yield self._response_event(
                    response_id=response_id,
                    content=assistant_content,
                )

            tool_calls = tool_response.get("tool_calls") or []
            logger.info(
                "Tool loop iteration project_id=%s iteration=%d tool_calls=%d assistant_chars=%d",
                project_id,
                iteration + 1,
                len(tool_calls),
                len(assistant_content),
            )
            if not tool_calls:
                completion_blocker = self._build_editor_completion_blocker(editor_retry_state)
                if completion_blocker:
                    logger.info(
                        (
                            "Tool loop blocked completion due to unresolved editor failure "
                            "project_id=%s iteration=%d blocker=%s"
                        ),
                        project_id,
                        iteration + 1,
                        self._truncate(completion_blocker, 500),
                    )
                    conversation.append({"role": "user", "content": completion_blocker})
                    continue
                logger.info(
                    "Tool loop completed without tool calls project_id=%s iteration=%d",
                    project_id,
                    iteration + 1,
                )
                return

            assistant_record = assistant_content or (
                f"Calling {len(tool_calls)} tool call"
                f"{'' if len(tool_calls) == 1 else 's'}."
            )
            conversation.append({"role": "assistant", "content": assistant_record})

            for index, tool_call in enumerate(tool_calls, start=1):
                action_sequence += 1
                action_id = f"{run_id}-step-{iteration + 1}-{index}-{action_sequence}"
                func_name = tool_call.get("function", {}).get("name", "")
                raw_args = tool_call.get("function", {}).get("arguments", "{}")
                logger.info(
                    "Tool call started project_id=%s iteration=%d call=%d/%d tool=%s args=%s",
                    project_id,
                    iteration + 1,
                    index,
                    len(tool_calls),
                    func_name,
                    self._truncate(str(raw_args), 2000),
                )

                try:
                    if isinstance(raw_args, str):
                        args = json.loads(raw_args)
                    elif isinstance(raw_args, dict):
                        args = raw_args
                    else:
                        raise ValueError(
                            f"Unsupported tool argument type: {type(raw_args).__name__}"
                        )
                except (json.JSONDecodeError, ValueError):
                    error_text = (
                        f"Tool call `{func_name}` has invalid JSON arguments: {raw_args}"
                    )
                    logger.error(
                        (
                            "Tool call failed to parse args project_id=%s iteration=%d "
                            "call=%d/%d tool=%s error=%s"
                        ),
                        project_id,
                        iteration + 1,
                        index,
                        len(tool_calls),
                        func_name,
                        error_text,
                    )
                    yield self._action_event(
                        tool=func_name,
                        status="started",
                        iteration=iteration + 1,
                        detail=f"Starting action {action_sequence}",
                        action_id=action_id,
                        response_id=response_id,
                        sequence=action_sequence,
                    )
                    yield self._response_event(
                        response_id=response_id,
                        content=f"\n\n[Tool Error] {error_text}",
                    )
                    yield self._action_event(
                        tool=func_name,
                        status="error",
                        iteration=iteration + 1,
                        detail=error_text,
                        action_id=action_id,
                        response_id=response_id,
                        sequence=action_sequence,
                    )
                    conversation.append(
                        {
                            "role": "user",
                            "content": f"Tool execution error: {error_text}",
                        }
                    )
                    continue

                started_detail = self._tool_start_detail(
                    func_name=func_name,
                    args=args,
                    call_index=index,
                    call_count=len(tool_calls),
                )
                yield self._action_event(
                    tool=func_name,
                    status="started",
                    iteration=iteration + 1,
                    detail=started_detail,
                    action_id=action_id,
                    response_id=response_id,
                    sequence=action_sequence,
                    command=self._extract_command_summary(func_name, args),
                )

                execution = await self._execute_tool_call(
                    func_name=func_name,
                    args=args,
                    memory=memory,
                    project_id=project_id,
                    files=files,
                    editor_retry_state=editor_retry_state,
                    action_id=action_id,
                    file_path=file_path,
                    selected_text=selected_text,
                    cursor_line=cursor_line,
                    line_from=line_from,
                    line_to=line_to,
                )
                tool_result = execution["tool_result"]
                self._update_editor_retry_state(
                    state=editor_retry_state,
                    func_name=func_name,
                    args=args,
                    tool_result=tool_result,
                    patches=execution["patches"],
                )
                status = "completed" if not tool_result.get("error") else "error"
                detail = self._tool_action_detail(func_name, tool_result)
                logger.info(
                    (
                        "Tool call finished project_id=%s iteration=%d "
                        "call=%d/%d tool=%s status=%s detail=%s"
                    ),
                    project_id,
                    iteration + 1,
                    index,
                    len(tool_calls),
                    func_name,
                    status,
                    detail,
                )
                logger.info(
                    "Tool response project_id=%s iteration=%d call=%d/%d tool=%s result=%s",
                    project_id,
                    iteration + 1,
                    index,
                    len(tool_calls),
                    func_name,
                    self._truncate(
                        self._safe_json_dumps(tool_result),
                        self.tool_output_max_chars,
                    ),
                )
                yield self._action_event(
                    tool=func_name,
                    status=status,
                    iteration=iteration + 1,
                    detail=detail,
                    action_id=action_id,
                    response_id=response_id,
                    sequence=action_sequence,
                    command=tool_result.get("command_summary"),
                    has_patch=bool(execution["patches"]),
                    patch_count=len(execution["patches"]),
                    artifacts=tool_result.get("artifacts"),
                    output=self._action_output(
                        func_name=func_name,
                        tool_result=tool_result,
                        visible_text=execution["visible_text"],
                    ),
                )

                if execution["edit_event"]:
                    edit_data = {
                        **execution["edit_event"],
                        "action_id": action_id,
                        "action_sequence": action_sequence,
                        "response_id": response_id,
                    }
                    yield {"type": "edit", "data": edit_data}

                for patch in execution["patches"]:
                    patch_data = {
                        **patch,
                        "action_id": action_id,
                        "action_sequence": action_sequence,
                        "response_id": response_id,
                    }
                    yield {"type": "patch", "data": patch_data}

                conversation.append(
                    {
                        "role": "user",
                        "content": self._build_tool_result_message(
                            func_name=func_name,
                            args=args,
                            tool_result=tool_result,
                            visible_text=execution["visible_text"],
                        ),
                    }
                )

        yield {
            "type": "response",
            "data": {
                "response_id": f"{run_id}-response-{self.max_tool_iterations}",
                "content": (
                    "\n\n[Warning] Reached tool-iteration limit before finalizing. "
                    "Please continue with another instruction if more steps are needed."
                ),
            },
        }
        yield self._action_event(
            tool="loop",
            status="warning",
            iteration=self.max_tool_iterations,
            detail="Reached max tool iterations",
            response_id=f"{run_id}-response-{self.max_tool_iterations}",
        )

    async def _execute_tool_call(
        self,
        *,
        func_name: str,
        args: dict,
        memory: PaperMemory | None,
        project_id: str,
        files: dict[str, str] | None,
        editor_retry_state: EditorRetryState | None = None,
        action_id: str,
        file_path: str | None = None,
        selected_text: str | None = None,
        cursor_line: int | None = None,
        line_from: int | None = None,
        line_to: int | None = None,
    ) -> dict:
        if func_name == "delegate_to_subagent":
            agent_type = args.get("agent_type", "")
            task_desc = args.get("task_description", "")
            agent = self.sub_agents.get(agent_type)
            if not agent:
                message = f"Unknown sub-agent: {agent_type}"
                return {
                    "tool_result": {"error": message},
                    "edit_event": None,
                    "patches": [],
                    "visible_text": message,
                }

            before_snapshot, workspace_path = self._snapshot_workspace_files(
                project_id=project_id,
                files=files,
            )
            task = Task(type=agent_type, description=task_desc)
            context = SubAgentContext(
                project_id=project_id,
                workspace_path=workspace_path,
                file_path=file_path,
                selected_text=selected_text,
                cursor_line=cursor_line,
                line_from=line_from,
                line_to=line_to,
                tool_output_max_chars=self.tool_output_max_chars,
            )
            result = await agent.execute(task, memory, context)
            after_snapshot, _ = self._snapshot_workspace_files(
                project_id=project_id,
                files=files,
            )
            patches = self._build_snapshot_patches(
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                workspace_path=workspace_path,
                description=f"Apply changes from `{agent_type}` sub-agent output.",
            )
            return {
                "tool_result": {
                    "status": result.status,
                    "content": result.content,
                    "artifacts": result.artifacts,
                },
                "edit_event": None,
                "patches": patches,
                "visible_text": result.content,
            }

        if func_name == "str_replace_editor":
            return self._execute_str_replace_editor_tool(
                args=args,
                project_id=project_id,
                files=files,
                editor_retry_state=editor_retry_state,
            )

        if func_name == "bash":
            return await self._execute_bash_tool(
                args=args,
                project_id=project_id,
                files=files,
                action_id=action_id,
            )

        message = f"Unsupported tool: {func_name}"
        return {
            "tool_result": {"error": message},
            "edit_event": None,
            "patches": [],
            "visible_text": message,
        }

    def _execute_str_replace_editor_tool(
        self,
        *,
        args: dict,
        project_id: str,
        files: dict[str, str] | None,
        editor_retry_state: EditorRetryState | None = None,
    ) -> dict:
        workspace_path, workspace_error, using_overlay = self._resolve_editor_workspace(
            project_id=project_id,
            files=files,
        )
        if workspace_error:
            return {
                "tool_result": {"error": workspace_error},
                "edit_event": None,
                "patches": [],
                "visible_text": workspace_error,
            }

        editor = WorkspaceStrReplaceEditor(
            workspace_path=workspace_path,
            history=self._editor_history,
            max_response_chars=self.tool_output_max_chars,
        )

        command = str(args.get("command", "")).strip()
        path = str(args.get("path", "")).strip()
        normalized_path = self._normalize_editor_tracking_path(path=path, workspace_path=workspace_path)
        preflight_error = self._preflight_editor_operation(
            state=editor_retry_state,
            command=command,
            path=normalized_path,
        )
        if preflight_error:
            return {
                "tool_result": preflight_error,
                "edit_event": None,
                "patches": [],
                "visible_text": self._editor_error_visible_text(preflight_error),
            }

        before_text, before_file_exists = self._read_editor_target_before_change(
            editor=editor,
            command=command,
            path=path,
        )
        try:
            result = editor.execute(
                command=command,
                path=path,
                file_text=args.get("file_text"),
                view_range=args.get("view_range"),
                old_str=args.get("old_str"),
                new_str=args.get("new_str"),
                insert_line=args.get("insert_line"),
            )
        except ValueError as exc:
            message = str(exc)
            error_code, guidance = self._classify_editor_error(command=command, message=message)
            return {
                "tool_result": {
                    "error": message,
                    "error_code": error_code,
                    "command": command or None,
                    "path": normalized_path or None,
                    "guidance": guidance,
                },
                "edit_event": None,
                "patches": [],
                "visible_text": self._editor_error_visible_text(
                    {
                        "error": message,
                        "guidance": guidance,
                    }
                ),
            }

        normalized_path = self._normalize_workspace_path(result.path, workspace_path)
        absolute_path = None if using_overlay else result.path
        patches = self._build_editor_patches(
            command=command,
            normalized_path=normalized_path,
            absolute_path=result.path,
            before_text=before_text,
            before_file_exists=before_file_exists,
            summary=result.summary,
        )
        tool_result = {
            "command": result.command,
            "path": normalized_path,
            "absolute_path": absolute_path,
            "status": result.status,
            "summary": result.summary,
            "metadata": result.metadata,
            "preview": self._truncate(result.output, min(self.tool_output_max_chars, 1200)),
        }
        edit_event = {
            "tool": "str_replace_editor",
            "command": result.command,
            "path": normalized_path,
            "absolute_path": absolute_path,
            "status": result.status,
            "summary": result.summary,
            "metadata": result.metadata,
        }
        return {
            "tool_result": tool_result,
            "edit_event": edit_event,
            "patches": patches,
            "visible_text": result.output,
        }

    async def _execute_bash_tool(
        self,
        *,
        args: dict,
        project_id: str,
        files: dict[str, str] | None,
        action_id: str,
    ) -> dict:
        command = str(args.get("command", "")).strip()
        if not command:
            message = "Bash tool requires a non-empty `command`."
            return {
                "tool_result": {"error": message},
                "edit_event": None,
                "patches": [],
                "visible_text": message,
            }

        effective_files = self._get_active_files(project_id=project_id, files=files)
        workspace_path = self.config.workspace_path
        workspace_error = self._validate_workspace_path(workspace_path)
        if workspace_error:
            if effective_files:
                workspace_path = self._fallback_bash_workspace_path(workspace_path)
            else:
                return {
                    "tool_result": {"error": workspace_error},
                    "edit_event": None,
                    "patches": [],
                    "visible_text": workspace_error,
                }

        if not self.config.runner_url:
            message = "Runner URL is not configured for bash execution."
            return {
                "tool_result": {"error": message},
                "edit_event": None,
                "patches": [],
                "visible_text": message,
            }

        requested_timeout = args.get("timeout_seconds", self.default_timeout_seconds)
        timeout_seconds = self._coerce_timeout_seconds(requested_timeout)
        working_subdir = args.get("working_subdir")
        command_summary = self._summarize_command(command, 120)
        command_intent = self._classify_bash_command(command)
        if command_intent != "execute":
            message = (
                "Bash is reserved for execution-oriented tasks only. "
                "Use `str_replace_editor` for workspace file viewing or editing."
            )
            return {
                "tool_result": {
                    "error": message,
                    "command": command,
                    "command_summary": command_summary,
                    "command_intent": command_intent,
                },
                "edit_event": None,
                "patches": [],
                "visible_text": message,
            }

        runner = RunnerClient(self.config.runner_url)

        try:
            result = await runner.execute(
                project_id=project_id,
                workspace_path=workspace_path,
                command=command,
                timeout_seconds=timeout_seconds,
                working_subdir=working_subdir,
                files=effective_files,
            )
        except Exception as exc:
            message = f"Runner execution failed: {exc}"
            return {
                "tool_result": {"error": message},
                "edit_event": None,
                "patches": [],
                "visible_text": message,
            }

        tool_result = {
            "command": command,
            "command_summary": command_summary,
            "command_intent": command_intent,
            "timeout_seconds": timeout_seconds,
            "exit_code": result.exit_code,
            "stdout": self._truncate(result.stdout, self.tool_output_max_chars),
            "stderr": self._truncate(result.stderr, self.tool_output_max_chars),
            "changed_files": [
                self._normalize_workspace_path(c.path, workspace_path) for c in result.changed_files
            ],
            "changed_file_count": len(result.changed_files),
        }

        visible_text = ""
        if result.changed_files:
            visible_text = (
                "The bash command completed but modified workspace files. "
                "Use `str_replace_editor` for intentional file changes."
            )
        elif result.exit_code != 0:
            visible_text = (
                "A command step failed while working on your request. "
                "I will adjust and try another approach."
            )

        return {
            "tool_result": tool_result,
            "edit_event": None,
            "patches": [
                patch
                for changed_file in result.changed_files
                if (
                    patch := self._build_patch(
                        file_path=self._normalize_workspace_path(changed_file.path, workspace_path),
                        before_text=changed_file.before,
                        after_text=changed_file.after,
                        before_exists=changed_file.before_exists,
                        after_exists=changed_file.after_exists,
                        description=f"Apply changes from `{command_summary}`.",
                    )
                )
            ],
            "visible_text": visible_text,
        }

    def _validate_workspace_path(self, workspace_path: str | None) -> str | None:
        if not workspace_path:
            return "workspace_path is not configured for this project."
        if not os.path.isabs(workspace_path):
            return "workspace_path must be an absolute path."

        real_workspace = os.path.realpath(workspace_path)
        if not os.path.exists(real_workspace):
            return f"workspace_path does not exist: `{workspace_path}`."
        if not os.path.isdir(real_workspace):
            return f"workspace_path is not a directory: `{workspace_path}`."

        if self.allowed_workspace_roots:
            allowed = any(
                real_workspace == root or real_workspace.startswith(f"{root}{os.sep}")
                for root in self.allowed_workspace_roots
            )
            if not allowed:
                return (
                    "workspace_path is outside allowed roots. "
                    "Set RESEARCHKIT_ALLOWED_WORKSPACE_ROOTS to include this path."
                )

        return None

    def _coerce_timeout_seconds(self, value: object) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            timeout = self.default_timeout_seconds
        return min(max(timeout, 1), 300)

    def _resolve_editor_workspace(
        self,
        *,
        project_id: str,
        files: dict[str, str] | None,
    ) -> tuple[str | None, str | None, bool]:
        if files:
            return self._ensure_overlay_workspace(project_id, files), None, True

        workspace_path = self.config.workspace_path
        workspace_error = self._validate_workspace_path(workspace_path)
        if workspace_error:
            return None, workspace_error, False
        return workspace_path, None, False

    def _ensure_overlay_workspace(self, project_id: str, files: dict[str, str]) -> str:
        workspace = self._overlay_workspaces.get(project_id)
        if workspace is None:
            safe_project_id = "".join(
                ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_id
            )[:80] or "project"
            workspace = tempfile.TemporaryDirectory(prefix=f"researchkit-{safe_project_id}-")
            self._overlay_workspaces[project_id] = workspace
            self._write_overlay_files(workspace.name, files)
        return workspace.name

    def _cleanup_overlay_workspace(self, project_id: str) -> None:
        workspace = self._overlay_workspaces.pop(project_id, None)
        if workspace is not None:
            workspace.cleanup()

    def _get_active_files(
        self,
        *,
        project_id: str,
        files: dict[str, str] | None,
    ) -> dict[str, str] | None:
        workspace = self._overlay_workspaces.get(project_id)
        if workspace is not None:
            return self._collect_workspace_files(workspace.name)
        return files

    @staticmethod
    def _fallback_bash_workspace_path(workspace_path: str | None) -> str:
        if isinstance(workspace_path, str) and os.path.isabs(workspace_path):
            return workspace_path
        return "/workspace"

    def _write_overlay_files(self, workspace_path: str, files: dict[str, str]) -> None:
        workspace = Path(workspace_path)
        for rel_path, content in files.items():
            normalized = self._normalize_overlay_rel_path(rel_path)
            target = workspace / normalized
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _collect_workspace_files(self, workspace_path: str) -> dict[str, str]:
        workspace = Path(workspace_path)
        collected: dict[str, str] = {}
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            try:
                collected[path.relative_to(workspace).as_posix()] = path.read_text(
                    encoding="utf-8"
                )
            except (OSError, UnicodeDecodeError):
                continue
        return collected

    @staticmethod
    def _normalize_overlay_rel_path(path: str) -> Path:
        normalized = PurePosixPath(path.lstrip("/"))
        if not normalized.parts:
            raise ValueError("empty file path")
        if any(part in ("", ".", "..") for part in normalized.parts):
            raise ValueError(f"invalid file path: {path}")
        return Path(*normalized.parts)

    def _read_editor_target_before_change(
        self,
        *,
        editor: WorkspaceStrReplaceEditor,
        command: str,
        path: str,
    ) -> tuple[str | None, bool]:
        if command not in {"create", "str_replace", "insert", "undo_edit"}:
            return None, False

        try:
            candidate = editor._resolve_candidate_path(path)
        except Exception:
            return None, False

        resolved = Path(os.path.realpath(str(candidate)))
        if resolved.exists() and resolved.is_file():
            try:
                return resolved.read_text(encoding="utf-8"), True
            except (OSError, UnicodeDecodeError):
                return None, True
        return None, False

    def _build_editor_patches(
        self,
        *,
        command: str,
        normalized_path: str,
        absolute_path: str,
        before_text: str | None,
        before_file_exists: bool,
        summary: str,
    ) -> list[dict]:
        if command not in {"create", "str_replace", "insert", "undo_edit"}:
            return []

        path = Path(absolute_path)
        after_exists = path.exists() and path.is_file()
        try:
            after_text = path.read_text(encoding="utf-8") if after_exists else None
        except (OSError, UnicodeDecodeError):
            after_text = None

        if not before_file_exists and not after_exists:
            return []

        patch = self._build_patch(
            file_path=normalized_path,
            before_text=before_text or "",
            after_text=after_text or "",
            before_exists=before_file_exists,
            after_exists=after_exists,
            description=summary,
        )
        return [patch] if patch else []

    def _snapshot_workspace_files(
        self,
        *,
        project_id: str,
        files: dict[str, str] | None,
    ) -> tuple[dict[str, str] | None, str | None]:
        workspace_path, workspace_error, _ = self._resolve_editor_workspace(
            project_id=project_id,
            files=files,
        )
        if workspace_error or not workspace_path:
            return None, None
        return self._collect_workspace_files(workspace_path), workspace_path

    def _build_snapshot_patches(
        self,
        *,
        before_snapshot: dict[str, str] | None,
        after_snapshot: dict[str, str] | None,
        workspace_path: str | None,
        description: str,
    ) -> list[dict]:
        if before_snapshot is None or after_snapshot is None or not workspace_path:
            return []

        patches: list[dict] = []
        for rel_path in sorted(set(before_snapshot) | set(after_snapshot)):
            before_exists = rel_path in before_snapshot
            after_exists = rel_path in after_snapshot
            before_text = before_snapshot.get(rel_path, "")
            after_text = after_snapshot.get(rel_path, "")
            patch = self._build_patch(
                file_path=self._normalize_workspace_path(rel_path, workspace_path),
                before_text=before_text,
                after_text=after_text,
                before_exists=before_exists,
                after_exists=after_exists,
                description=description,
            )
            if patch:
                patches.append(patch)
        return patches

    def _build_patch(
        self,
        *,
        file_path: str,
        before_text: str,
        after_text: str,
        before_exists: bool = True,
        after_exists: bool = True,
        description: str,
    ) -> dict | None:
        if before_text == after_text and before_exists == after_exists:
            return None

        selection_from, selection_to, original_text, replacement_text = compute_minimal_edit(
            before_text,
            after_text,
        )
        change_type = "edit"
        if not before_exists and after_exists:
            change_type = "create"
        elif before_exists and not after_exists:
            change_type = "delete"
        return {
            "file_path": file_path,
            "selection_from": selection_from,
            "selection_to": selection_to,
            "original_text": original_text,
            "replacement_text": replacement_text,
            "description": description,
            "change_type": change_type,
        }

    @staticmethod
    def _normalize_workspace_path(path: str, workspace_path: str) -> str:
        if not path:
            return path
        if not os.path.isabs(path):
            return path.lstrip("/")

        real_workspace = os.path.realpath(workspace_path)
        real_path = os.path.realpath(path)
        if real_path == real_workspace or real_path.startswith(f"{real_workspace}{os.sep}"):
            return os.path.relpath(real_path, real_workspace).lstrip("./")
        return path

    def _normalize_editor_tracking_path(self, *, path: str, workspace_path: str) -> str:
        normalized = path.strip()
        if not normalized:
            return normalized
        return self._normalize_workspace_path(normalized, workspace_path)

    def _preflight_editor_operation(
        self,
        *,
        state: EditorRetryState | None,
        command: str,
        path: str,
    ) -> dict | None:
        if state is None or not path:
            return None

        prior_failure = state.must_view_before_edit.get(path)
        if prior_failure and command != "view":
            guidance = (
                "A previous edit on this file failed. Re-run `view` on the same path, "
                "copy the exact current text, and only then attempt another edit."
            )
            return {
                "error": (
                    f"Previous edit on `{path}` failed. You must use `view` on this file "
                    "before any further edit attempt."
                ),
                "error_code": "view_required_after_failed_edit",
                "command": command or None,
                "path": path,
                "guidance": f"{guidance} Previous failure: {prior_failure}",
            }

        if command == "create" and path in state.viewed_existing_paths:
            return {
                "error": (
                    f"`create` cannot be used for `{path}` because the file already exists."
                ),
                "error_code": "create_existing_file",
                "command": command,
                "path": path,
                "guidance": (
                    "Use `view` to inspect the file and then edit it with `str_replace` or "
                    "`insert`. `create` is only for brand-new files."
                ),
            }

        return None

    @staticmethod
    def _classify_editor_error(*, command: str, message: str) -> tuple[str, str | None]:
        if command == "create" and "already exists" in message:
            return (
                "create_existing_file",
                (
                    "This file already exists. Do not retry `create`. Use `view` first, "
                    "then edit the existing file with `str_replace` or `insert`."
                ),
            )
        if command == "str_replace" and "`old_str` was not found" in message:
            return (
                "str_replace_no_match",
                (
                    "Your `old_str` did not exactly match the current file. Re-run `view` "
                    "on the exact file or range, copy the current text verbatim, and then "
                    "retry `str_replace`."
                ),
            )
        if command == "str_replace" and "appears multiple times" in message:
            return (
                "str_replace_ambiguous_match",
                (
                    "The target text is not unique. Re-run `view` on a narrower range and "
                    "replace a longer unique substring before retrying."
                ),
            )
        if "does not exist" in message:
            return (
                "path_not_found",
                (
                    "Inspect the workspace with `view .` and then use the full "
                    "workspace-relative path, including any paper subdirectory."
                ),
            )
        return ("editor_error", None)

    @staticmethod
    def _editor_error_visible_text(tool_result: dict) -> str:
        error = str(tool_result.get("error") or "").strip()
        guidance = str(tool_result.get("guidance") or "").strip()
        if error and guidance:
            return f"{error}\n\nNext step: {guidance}"
        return error or guidance

    def _update_editor_retry_state(
        self,
        *,
        state: EditorRetryState,
        func_name: str,
        args: dict,
        tool_result: dict,
        patches: list[dict],
    ) -> None:
        if func_name != "str_replace_editor":
            return

        command = str(tool_result.get("command") or args.get("command") or "").strip()
        path = str(tool_result.get("path") or args.get("path") or "").strip()
        if not path:
            return

        if patches:
            state.unresolved_edit_failures.pop(path, None)
            state.must_view_before_edit.pop(path, None)
            if command != "create":
                state.viewed_existing_paths.add(path)
            return

        error = str(tool_result.get("error") or "").strip()
        if not error:
            metadata = tool_result.get("metadata") or {}
            if command == "view" and metadata.get("kind") == "file":
                state.viewed_existing_paths.add(path)
                state.must_view_before_edit.pop(path, None)
            return

        if command == "create" and "already exists" in error:
            state.viewed_existing_paths.add(path)

        if command in {"create", "str_replace", "insert", "undo_edit"}:
            state.unresolved_edit_failures[path] = error

        if command in {"create", "str_replace", "insert", "undo_edit"}:
            state.must_view_before_edit[path] = error

    def _build_editor_completion_blocker(self, state: EditorRetryState) -> str | None:
        if not state.unresolved_edit_failures:
            return None

        pending = sorted(state.unresolved_edit_failures.items())
        lines = [
            "Do not finalize yet. A requested file edit failed and no successful patch has replaced it.",
            "Re-open the affected file with `view` and apply a deterministic edit before responding as complete.",
        ]
        for path, error in pending[:3]:
            lines.append(f"- `{path}`: {error}")
        return "\n".join(lines)

    def _build_tool_result_message(
        self,
        *,
        func_name: str,
        args: dict,
        tool_result: dict,
        visible_text: str,
    ) -> str:
        lines = [f"Tool result for `{func_name}`:"]

        error = tool_result.get("error")
        if error:
            lines.append(f"Error: {error}")
            guidance = str(tool_result.get("guidance") or "").strip()
            if guidance:
                lines.append(f"Guidance: {guidance}")
        elif func_name == "str_replace_editor":
            command = tool_result.get("command") or args.get("command")
            path = tool_result.get("path") or args.get("path")
            status = tool_result.get("status")
            summary = tool_result.get("summary")
            if command:
                lines.append(f"Command: {command}")
            if path:
                lines.append(f"Path: {path}")
            if status:
                lines.append(f"Status: {status}")
            if summary:
                lines.append(f"Summary: {summary}")
            preview = str(tool_result.get("preview") or "").strip()
            if preview:
                lines.append("Preview:")
                lines.append(f"```text\n{preview}\n```")
        elif func_name == "bash":
            command = tool_result.get("command_summary") or tool_result.get("command")
            if command:
                lines.append(f"Command: {command}")
            if "exit_code" in tool_result:
                lines.append(f"Exit code: {tool_result['exit_code']}")
            changed_files = tool_result.get("changed_files") or []
            if changed_files:
                lines.append("Changed files:")
                lines.extend(f"- {path}" for path in changed_files[:10])
            stdout = str(tool_result.get("stdout") or "").strip()
            stderr = str(tool_result.get("stderr") or "").strip()
            if stdout:
                lines.append("Stdout:")
                lines.append(f"```text\n{stdout}\n```")
            if stderr:
                lines.append("Stderr:")
                lines.append(f"```text\n{stderr}\n```")
        elif func_name == "delegate_to_subagent":
            status = tool_result.get("status")
            content = str(tool_result.get("content") or "").strip()
            artifacts = tool_result.get("artifacts") or []
            if status:
                lines.append(f"Status: {status}")
            if isinstance(artifacts, list) and artifacts:
                lines.append(
                    "Artifacts: "
                    + ", ".join(
                        str(artifact.get("type", "artifact"))
                        for artifact in artifacts
                        if isinstance(artifact, dict)
                    )
                )
            if content:
                lines.append("Output:")
                lines.append(
                    f"```text\n{self._truncate(content, self.tool_output_max_chars)}\n```"
                )
        else:
            serialized = self._safe_json_dumps(tool_result)
            lines.append(f"```json\n{self._truncate(serialized, self.tool_output_max_chars)}\n```")

        if visible_text and func_name != "bash":
            lines.append("Visible output:")
            lines.append(
                f"```text\n{self._truncate(visible_text, self.tool_output_max_chars)}\n```"
            )

        return "\n".join(lines)

    def _build_workspace_prompt_context(
        self,
        *,
        project_id: str,
        files: dict[str, str] | None,
        file_path: str | None,
    ) -> str:
        workspace_path, workspace_error, _ = self._resolve_editor_workspace(
            project_id=project_id,
            files=files,
        )
        if workspace_error:
            return f"- Workspace unavailable: {workspace_error}"
        if not workspace_path:
            return ""
        return "\n".join(build_workspace_context_lines(workspace_path, active_file=file_path))

    @staticmethod
    def _safe_json_dumps(value: object) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _truncate(value: str, max_chars: int) -> str:
        if len(value) <= max_chars:
            return value
        return value[: max_chars - 16] + "\n...[truncated]"

    def _tool_action_detail(self, func_name: str, tool_result: dict) -> str:
        if tool_result.get("error"):
            return str(tool_result["error"])

        if func_name == "str_replace_editor":
            return str(tool_result.get("summary") or "Editor operation completed")

        if func_name == "bash":
            exit_code = tool_result.get("exit_code", "?")
            command = str(tool_result.get("command_summary") or "bash command")
            changed_file_count = int(tool_result.get("changed_file_count", 0) or 0)
            if changed_file_count:
                return (
                    f"`{command}` exited {exit_code}; "
                    f"changed {changed_file_count} workspace file"
                    f"{'' if changed_file_count == 1 else 's'} unexpectedly."
                )
            return f"`{command}` exited {exit_code}."

        if func_name == "delegate_to_subagent":
            status = tool_result.get("status", "unknown")
            artifacts = tool_result.get("artifacts") or []
            if isinstance(artifacts, list) and artifacts:
                return (
                    f"Sub-agent returned status `{status}` "
                    f"with {len(artifacts)} artifact"
                    f"{'' if len(artifacts) == 1 else 's'}."
                )
            return f"Sub-agent returned status `{status}`"

        return "Tool completed"

    def _action_output(
        self,
        *,
        func_name: str,
        tool_result: dict,
        visible_text: str,
    ) -> str | None:
        if func_name == "delegate_to_subagent":
            content = str(tool_result.get("content") or "").strip()
            if content:
                return self._truncate(content, self.tool_output_max_chars)

        text = visible_text.strip()
        if text:
            return self._truncate(text, self.tool_output_max_chars)

        return None

    @staticmethod
    def _summarize_command(command: str, max_chars: int = 120) -> str:
        compact = " ".join(command.strip().split())
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 16] + "...[truncated]"

    @staticmethod
    def _classify_bash_command(command: str) -> str:
        normalized = " ".join(command.lower().split())
        inspect_prefixes = (
            "rg ",
            "grep ",
            "find ",
            "ls ",
            "pwd",
            "cat ",
            "sed -n ",
            "head ",
            "tail ",
            "wc ",
            "git diff",
        )
        edit_markers = (
            "sed -i",
            "perl -i",
            "tee ",
            "apply_patch",
            "mv ",
            "cp ",
            "rm ",
            "mkdir ",
            "touch ",
            ">",
        )
        execute_prefixes = (
            "pytest",
            "python ",
            "python3 ",
            "uv ",
            "pip ",
            "npm ",
            "pnpm ",
            "yarn ",
            "make ",
            "git status",
            "git rev-parse",
            "git branch",
            "git commit",
            "git checkout",
            "git log",
            "git show",
            "git fetch",
            "git pull",
            "bash ",
            "sh ",
        )

        if any(marker in normalized for marker in edit_markers):
            return "edit"
        if normalized.startswith(inspect_prefixes):
            return "inspect"
        if normalized.startswith(execute_prefixes):
            return "execute"
        return "execute"

    @staticmethod
    def _extract_command_summary(func_name: str, args: dict) -> str | None:
        if func_name == "bash":
            command = str(args.get("command", "")).strip()
            if not command:
                return None
            return MainAgent._summarize_command(command, 120)
        if func_name == "str_replace_editor":
            command = str(args.get("command", "")).strip()
            path = str(args.get("path", "")).strip()
            if not command:
                return None
            summary = command
            if path:
                summary += f" {path}"
            return MainAgent._summarize_command(summary, 120)
        return None

    def _tool_start_detail(
        self,
        *,
        func_name: str,
        args: dict,
        call_index: int,
        call_count: int,
    ) -> str:
        if func_name == "str_replace_editor":
            command = str(args.get("command", "editor action"))
            path = str(args.get("path", ""))
            if path:
                return f"Running editor command {call_index}/{call_count}: `{command}` on `{path}`"
            return f"Running editor command {call_index}/{call_count}: `{command}`"
        if func_name == "bash":
            command = self._extract_command_summary(func_name, args)
            if command:
                return f"Running command {call_index}/{call_count}: `{command}`"
        if func_name == "delegate_to_subagent":
            agent_type = str(args.get("agent_type", "sub-agent"))
            return f"Delegating step {call_index}/{call_count} to `{agent_type}`"
        return f"Executing tool call {call_index}/{call_count}"

    @staticmethod
    def _action_event(
        *,
        tool: str,
        status: str,
        iteration: int,
        detail: str,
        action_id: str | None = None,
        response_id: str | None = None,
        sequence: int | None = None,
        command: str | None = None,
        has_patch: bool | None = None,
        patch_count: int | None = None,
        artifacts: list[dict] | None = None,
        output: str | None = None,
    ) -> dict:
        data = {
            "tool": tool,
            "status": status,
            "iteration": iteration,
            "detail": detail,
        }
        if action_id:
            data["action_id"] = action_id
        if response_id:
            data["response_id"] = response_id
        if sequence is not None:
            data["sequence"] = sequence
        if command:
            data["command"] = command
        if has_patch is not None:
            data["has_patch"] = has_patch
        if patch_count is not None:
            data["patch_count"] = patch_count
        if artifacts:
            data["artifacts"] = artifacts
        if output:
            data["output"] = output

        return {
            "type": "action",
            "data": data,
        }

    @staticmethod
    def _response_event(*, response_id: str, content: str, kind: str = "assistant") -> dict:
        return {
            "type": "response",
            "data": {
                "response_id": response_id,
                "content": content,
                "kind": kind,
            },
        }

    @classmethod
    def _normalize_stored_conversation_messages(cls, messages: object) -> list[dict]:
        if not isinstance(messages, list):
            return []
        normalized: list[dict] = []
        for message in messages:
            normalized_message = cls._normalize_stored_conversation_message(message)
            if normalized_message is not None:
                normalized.append(normalized_message)
        return normalized[-20:]

    @classmethod
    def _normalize_stored_conversation_message(cls, message: object) -> dict | None:
        if not isinstance(message, dict):
            return None

        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            return None

        normalized = {
            "role": role,
            "content": content,
        }
        if cls._is_internal_conversation_message(normalized):
            return None

        response_id = message.get("response_id")
        if isinstance(response_id, str) and response_id:
            normalized["response_id"] = response_id

        action_id = message.get("action_id")
        if isinstance(action_id, str) and action_id:
            normalized["action_id"] = action_id

        actions = cls._normalize_stored_actions(message.get("actions"))
        if actions:
            normalized["actions"] = actions

        patches = cls._normalize_stored_patches(message.get("patches"))
        if patches:
            normalized["patches"] = patches

        return normalized

    @staticmethod
    def _normalize_stored_actions(actions: object) -> list[dict]:
        if not isinstance(actions, list):
            return []

        normalized: list[dict] = []
        for action in actions:
            if not isinstance(action, dict):
                continue

            tool = action.get("tool")
            status = action.get("status")
            iteration = action.get("iteration")
            detail = action.get("detail")
            if (
                not isinstance(tool, str)
                or not isinstance(status, str)
                or not isinstance(iteration, int)
                or not isinstance(detail, str)
            ):
                continue

            normalized_action = {
                "tool": tool,
                "status": status,
                "iteration": iteration,
                "detail": detail,
            }
            for key in ("action_id", "response_id", "command", "output"):
                value = action.get(key)
                if isinstance(value, str) and value:
                    normalized_action[key] = value
            for key in ("sequence", "patch_count"):
                value = action.get(key)
                if isinstance(value, int):
                    normalized_action[key] = value
            has_patch = action.get("has_patch")
            if isinstance(has_patch, bool):
                normalized_action["has_patch"] = has_patch
            artifacts = action.get("artifacts")
            if isinstance(artifacts, list):
                normalized_action["artifacts"] = [
                    artifact for artifact in artifacts if isinstance(artifact, dict)
                ]
            normalized.append(normalized_action)

        return normalized

    @staticmethod
    def _normalize_stored_patches(patches: object) -> list[dict]:
        if not isinstance(patches, list):
            return []

        normalized: list[dict] = []
        for patch in patches:
            if not isinstance(patch, dict):
                continue

            required_str_fields = (
                "file_path",
                "original_text",
                "replacement_text",
                "description",
            )
            if any(not isinstance(patch.get(field), str) for field in required_str_fields):
                continue
            if not isinstance(patch.get("selection_from"), int) or not isinstance(
                patch.get("selection_to"), int
            ):
                continue

            normalized_patch = {
                "file_path": patch["file_path"],
                "selection_from": patch["selection_from"],
                "selection_to": patch["selection_to"],
                "original_text": patch["original_text"],
                "replacement_text": patch["replacement_text"],
                "description": patch["description"],
            }
            for key in ("change_type", "action_id", "response_id", "command_summary", "_status"):
                value = patch.get(key)
                if isinstance(value, str) and value:
                    normalized_patch[key] = value
            action_sequence = patch.get("action_sequence")
            if isinstance(action_sequence, int):
                normalized_patch["action_sequence"] = action_sequence
            normalized.append(normalized_patch)

        return normalized

    @classmethod
    def _find_assistant_history_index(
        cls,
        messages: list[dict],
        *,
        response_id: str | None = None,
        action_id: str | None = None,
        fallback_to_last_assistant: bool = False,
    ) -> int:
        if response_id:
            for index in range(len(messages) - 1, -1, -1):
                message = messages[index]
                if (
                    message.get("role") == "assistant"
                    and message.get("response_id") == response_id
                ):
                    return index

        if action_id:
            for index in range(len(messages) - 1, -1, -1):
                message = messages[index]
                if (
                    message.get("role") == "assistant"
                    and message.get("action_id") == action_id
                ):
                    return index

        if fallback_to_last_assistant and messages:
            last = messages[-1]
            if last.get("role") == "assistant":
                return len(messages) - 1

        return -1

    @staticmethod
    def _new_assistant_history_message(
        *,
        response_id: str | None = None,
        action_id: str | None = None,
    ) -> dict:
        message = {
            "role": "assistant",
            "content": "",
        }
        if response_id:
            message["response_id"] = response_id
        if action_id:
            message["action_id"] = action_id
        return message

    @classmethod
    def _append_response_to_history(cls, messages: list[dict], payload: object) -> None:
        if not isinstance(payload, dict):
            return

        if payload.get("kind") == "tool_output":
            return

        content = payload.get("content")
        if not isinstance(content, str):
            return

        response_id = payload.get("response_id")
        normalized_response_id = response_id if isinstance(response_id, str) else None
        target_index = cls._find_assistant_history_index(
            messages,
            response_id=normalized_response_id,
            fallback_to_last_assistant=normalized_response_id is None,
        )

        if target_index >= 0:
            target = messages[target_index]
            target["content"] = f"{target.get('content', '')}{content}"
            if normalized_response_id and not target.get("response_id"):
                target["response_id"] = normalized_response_id
            return

        if not content:
            return

        message = cls._new_assistant_history_message(response_id=normalized_response_id)
        message["content"] = content
        messages.append(message)

    @classmethod
    def _append_action_to_history(cls, messages: list[dict], payload: object) -> None:
        action = cls._normalize_stored_actions([payload])
        if not action:
            return

        normalized_action = action[0]
        response_id = normalized_action.get("response_id")
        action_id = normalized_action.get("action_id")
        target_index = cls._find_assistant_history_index(
            messages,
            response_id=response_id,
            action_id=action_id,
            fallback_to_last_assistant=not response_id and not action_id,
        )
        if target_index < 0:
            messages.append(
                cls._new_assistant_history_message(
                    response_id=response_id if isinstance(response_id, str) else None,
                    action_id=action_id if isinstance(action_id, str) else None,
                )
            )
            target_index = len(messages) - 1

        target = messages[target_index]
        target_actions = list(target.get("actions") or [])
        target_actions.append(normalized_action)
        target["actions"] = target_actions
        if response_id and not target.get("response_id"):
            target["response_id"] = response_id
        if action_id and not target.get("action_id"):
            target["action_id"] = action_id

    @classmethod
    def _append_patch_to_history(cls, messages: list[dict], payload: object) -> None:
        patch = cls._normalize_stored_patches([payload])
        if not patch:
            return

        normalized_patch = patch[0]
        response_id = normalized_patch.get("response_id")
        action_id = normalized_patch.get("action_id")
        target_index = cls._find_assistant_history_index(
            messages,
            response_id=response_id,
            action_id=action_id,
            fallback_to_last_assistant=not response_id and not action_id,
        )
        if target_index < 0:
            messages.append(
                cls._new_assistant_history_message(
                    response_id=response_id if isinstance(response_id, str) else None,
                    action_id=action_id if isinstance(action_id, str) else None,
                )
            )
            target_index = len(messages) - 1

        target = messages[target_index]
        target_patches = list(target.get("patches") or [])
        target_patches.append(normalized_patch)
        target["patches"] = target_patches
        if response_id and not target.get("response_id"):
            target["response_id"] = response_id
        if action_id and not target.get("action_id"):
            target["action_id"] = action_id

    async def _load_persisted_conversation(
        self,
        project_id: str,
        conversation_id: str,
    ) -> list[dict]:
        """Load persisted UI-visible conversation history from MongoDB."""
        db = get_db()
        query = {"project_id": project_id, "conversation_id": conversation_id}
        doc = await db.researchkitConversations.find_one(query)
        if doc is None and conversation_id == "default":
            doc = await db.researchkitConversations.find_one({"project_id": project_id})
        raw_messages = doc.get("messages", []) if isinstance(doc, dict) else []
        return self._normalize_stored_conversation_messages(raw_messages)

    async def _load_conversation(self, project_id: str, conversation_id: str) -> list[dict]:
        """Load prompt-safe conversation history from persisted UI-visible messages."""
        persisted = await self._load_persisted_conversation(project_id, conversation_id)
        return [
            {
                "role": str(message["role"]),
                "content": str(message["content"]),
            }
            for message in persisted
            if str(message["content"]) or str(message["role"]) != "assistant"
        ]

    async def _save_conversation(
        self,
        project_id: str,
        conversation_id: str,
        messages: list[dict],
    ) -> None:
        """Save conversation history to MongoDB."""
        db = get_db()
        await db.researchkitConversations.update_one(
            {"project_id": project_id, "conversation_id": conversation_id},
            {
                "$set": {
                    "project_id": project_id,
                    "conversation_id": conversation_id,
                    "messages": messages[-20:],  # Keep last 20
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    @staticmethod
    def _normalize_conversation_id(conversation_id: str | None) -> str:
        if not conversation_id:
            return "default"
        normalized = str(conversation_id).strip()
        if not normalized:
            return "default"
        return normalized[:128]

    @staticmethod
    def _is_internal_conversation_message(message: dict) -> bool:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            return False

        stripped = content.strip()
        if role == "user" and (
            stripped.startswith("Tool execution result (use this to decide the next step):")
            or stripped.startswith("Tool result for `")
        ):
            return True
        if role == "assistant" and re.fullmatch(r"Calling \d+ tool call(?:s)?\.", stripped):
            return True
        return False
