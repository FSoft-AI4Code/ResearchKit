import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from researchkit.agents.base import Task
from researchkit.agents.figure_agent import FigureAgent
from researchkit.agents.patch_utils import compute_minimal_edit
from researchkit.agents.research_agent import ResearchAgent
from researchkit.agents.review_agent import ReviewAgent
from researchkit.agents.runner_client import RunnerClient
from researchkit.agents.tools import AGENT_TOOLS
from researchkit.config.schema import ProviderConfig
from researchkit.db import get_db
from researchkit.memory.memory import MemoryManager
from researchkit.memory.schema import PaperMemory
from researchkit.providers.registry import create_provider

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SYSTEM_PROMPT_TEMPLATE = """\
You are ResearchKit's Main Agent — a terminal-first AI assistant for academic paper writing.
Treat the paper's files and structure as a codebase.

<IMPORTANT>
This is an iterative terminal workflow:
1) reason briefly
2) run command(s)
3) inspect outputs
4) continue until done.
</IMPORTANT>

For each response:
1. Include concise reasoning about your next step.
2. Include one or more tool calls, or no tool calls only when the task is complete.


## Command Execution Rules

You are operating in an environment where:
1. Every bash action runs in a new subshell.
2. Directory/env changes are not persistent across actions.
3. You must use deterministic, non-interactive commands.
4. You can run multiple independent commands in one response.

Each response should include:
1. **Reasoning text** where you explain your analysis and plan
2. At least one tool call with your command or no tool call at all if you think you have already completed the task.

**CRITICAL REQUIREMENTS:**
- Your response SHOULD include reasoning text explaining what you're doing
- Your response MUST include AT LEAST ONE bash tool call. You can make MULTIPLE tool calls in a single response when the commands are independent (e.g., searching multiple files, reading different parts of the codebase).
- For bash calls, always set `expect_file_changes` accurately:
  - `false` for read/inspect commands (`rg`, `ls`, `cat`, `sed -n`, `git status`, `git diff`, etc.)
  - `true` only for intentional file-edit commands.
- Prefer one atomic edit per bash call when modifying files.
- After edit commands, run a read-only verification command to confirm the change.
- If you use a subdirectory or env var, prefix in the same command: `MY_ENV=V cd /path && ...`.

## Environment Details
- You have a full Linux shell environment
- Always use non-interactive flags (-y, -f) for commands
- Avoid interactive tools like vi, nano, or any that require user input
- You can use bash commands or invoke any tool that is available in the environment
- You can also create new tools or scripts to help you with the task
- If a tool isn't available, you can also install it

## Delegation Policy
- Literature discovery / related work exploration -> delegate to `research`
- Figure/chart generation workflows beyond shell capability -> delegate to `figure`

## Paper Context
{memory_context}
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
        self.max_tool_iterations = max(config.max_tool_iterations, 1)
        self.default_timeout_seconds = max(config.bash_default_timeout_seconds, 1)
        self.tool_output_max_chars = max(config.tool_output_max_chars, 200)
        self.allowed_workspace_roots = [
            os.path.realpath(root)
            for root in (config.allowed_workspace_roots or [])
            if isinstance(root, str) and root.strip()
        ]

    async def handle(
        self,
        project_id: str,
        message: str,
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
        - {"type": "patch", "data": {EditPatch fields}}
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

        conversation = await self._load_conversation(project_id)

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
        conversation.append({"role": "user", "content": user_content})
        run_id = f"run-{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        response_text = ""
        try:
            async for event in self._run_tool_loop(
                system_prompt=system_prompt,
                conversation=conversation,
                memory=memory,
                project_id=project_id,
                files=files,
                run_id=run_id,
            ):
                if event["type"] == "text":
                    response_text += event["data"]
                elif event["type"] == "response":
                    response_text += str(event["data"].get("content") or "")
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
                yield self._response_event(
                    response_id=fallback_response_id,
                    content=chunk,
                )

        conversation.append({"role": "assistant", "content": response_text})
        await self._save_conversation(project_id, conversation)
        logger.info(
            "MainAgent handle completed project_id=%s response_chars=%d",
            project_id,
            len(response_text),
        )

    async def _run_tool_loop(
        self,
        *,
        system_prompt: str,
        conversation: list[dict],
        memory: PaperMemory | None,
        project_id: str,
        files: dict[str, str] | None,
        run_id: str,
    ) -> AsyncIterator[dict]:
        action_sequence = 0
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
                        raise ValueError(f"Unsupported tool argument type: {type(raw_args).__name__}")
                except (json.JSONDecodeError, ValueError):
                    error_text = f"Tool call `{func_name}` has invalid JSON arguments: {raw_args}"
                    logger.error(
                        "Tool call failed to parse args project_id=%s iteration=%d call=%d/%d tool=%s error=%s",
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
                    action_id=action_id,
                )
                tool_result = execution["tool_result"]
                status = "completed" if not tool_result.get("error") else "error"
                detail = self._tool_action_detail(func_name, tool_result)
                logger.info(
                    "Tool call finished project_id=%s iteration=%d call=%d/%d tool=%s status=%s detail=%s",
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
                )

                for patch in execution["patches"]:
                    patch_data = {
                        **patch,
                        "action_id": action_id,
                        "action_sequence": action_sequence,
                        "response_id": response_id,
                    }
                    yield {"type": "patch", "data": patch_data}

                if execution["visible_text"]:
                    yield self._response_event(
                        response_id=response_id,
                        content=f"\n\n{execution['visible_text']}",
                    )

                conversation.append(
                    {
                        "role": "user",
                        "content": self._build_tool_result_message(
                            func_name=func_name,
                            args=args,
                            tool_result=tool_result,
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
        action_id: str,
    ) -> dict:
        if func_name == "delegate_to_subagent":
            agent_type = args.get("agent_type", "")
            task_desc = args.get("task_description", "")
            agent = self.sub_agents.get(agent_type)
            if not agent:
                message = f"Unknown sub-agent: {agent_type}"
                return {"tool_result": {"error": message}, "patches": [], "visible_text": message}

            task = Task(type=agent_type, description=task_desc)
            result = await agent.execute(task, memory)
            return {
                "tool_result": {
                    "status": result.status,
                    "content": result.content,
                    "artifacts": result.artifacts,
                },
                "patches": [],
                "visible_text": result.content,
            }

        if func_name == "bash":
            return await self._execute_bash_tool(
                args=args,
                project_id=project_id,
                files=files,
                action_id=action_id,
            )

        message = f"Unsupported tool: {func_name}"
        return {"tool_result": {"error": message}, "patches": [], "visible_text": message}

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
            return {"tool_result": {"error": message}, "patches": [], "visible_text": message}

        if not self.config.runner_url:
            message = "Runner URL is not configured for bash execution."
            return {"tool_result": {"error": message}, "patches": [], "visible_text": message}

        workspace_path = self.config.workspace_path
        workspace_error = self._validate_workspace_path(workspace_path)
        if workspace_error:
            return {
                "tool_result": {"error": workspace_error},
                "patches": [],
                "visible_text": workspace_error,
            }

        requested_timeout = args.get("timeout_seconds", self.default_timeout_seconds)
        timeout_seconds = self._coerce_timeout_seconds(requested_timeout)
        working_subdir = args.get("working_subdir")
        command_summary = self._summarize_command(command, 120)
        command_intent = self._classify_bash_command(command)
        expect_file_changes = self._coerce_expect_file_changes(
            args.get("expect_file_changes"),
            command=command,
        )

        runner = RunnerClient(self.config.runner_url)

        try:
            result = await runner.execute(
                project_id=project_id,
                workspace_path=workspace_path,
                command=command,
                timeout_seconds=timeout_seconds,
                working_subdir=working_subdir,
                files=files,
            )
        except Exception as exc:
            message = f"Runner execution failed: {exc}"
            return {"tool_result": {"error": message}, "patches": [], "visible_text": message}

        patches = []
        for changed in result.changed_files:
            before = changed.before or ""
            after = changed.after or ""
            patch_path = self._normalize_patch_path(changed.path, workspace_path)
            selection_from, selection_to, original_text, replacement_text = compute_minimal_edit(
                before, after
            )

            patch = {
                "file_path": patch_path,
                "selection_from": selection_from,
                "selection_to": selection_to,
                "original_text": original_text,
                "replacement_text": replacement_text,
                "description": f"Bash edit via `{self._truncate(command, 80)}`",
                "action_id": action_id,
                "command_summary": command_summary,
            }
            patches.append(patch)

        tool_result = {
            "command": command,
            "command_summary": command_summary,
            "command_intent": command_intent,
            "expect_file_changes": expect_file_changes,
            "timeout_seconds": timeout_seconds,
            "exit_code": result.exit_code,
            "stdout": self._truncate(result.stdout, self.tool_output_max_chars),
            "stderr": self._truncate(result.stderr, self.tool_output_max_chars),
            "changed_files": [
                self._normalize_patch_path(c.path, workspace_path) for c in result.changed_files
            ],
            "patch_count": len(patches),
            "has_patch": bool(patches),
        }

        visible_text = ""
        if patches:
            visible_text = (
                f"Prepared {len(patches)} file update"
                f"{'' if len(patches) == 1 else 's'} for your review."
            )
            if not expect_file_changes:
                visible_text += " This command was marked read-only but produced edits."
        elif result.exit_code == 0 and expect_file_changes:
            visible_text = (
                "This step expected file edits but no diff patch was produced. "
                "I will adjust command strategy."
            )
        elif result.exit_code != 0:
            visible_text = (
                "A command step failed while working on your request. "
                "I will adjust and try another approach."
            )

        return {
            "tool_result": tool_result,
            "patches": patches,
            "visible_text": visible_text,
        }

    def _validate_workspace_path(self, workspace_path: str | None) -> str | None:
        if not workspace_path:
            return "workspace_path is not configured for this project."
        if not os.path.isabs(workspace_path):
            return "workspace_path must be an absolute path."

        real_workspace = os.path.realpath(workspace_path)

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


    @staticmethod
    def _normalize_patch_path(path: str, workspace_path: str) -> str:
        if not path:
            return path
        if not os.path.isabs(path):
            return path.lstrip("/")

        real_workspace = os.path.realpath(workspace_path)
        real_path = os.path.realpath(path)
        if real_path == real_workspace or real_path.startswith(f"{real_workspace}{os.sep}"):
            return os.path.relpath(real_path, real_workspace).lstrip("./")
        return path

    def _build_tool_result_message(self, *, func_name: str, args: dict, tool_result: dict) -> str:
        safe_payload = {
            "tool": func_name,
            "arguments": args,
            "result": tool_result,
        }
        serialized = self._safe_json_dumps(safe_payload)
        return (
            "Tool execution result (use this to decide the next step):\n"
            f"```json\n{self._truncate(serialized, self.tool_output_max_chars)}\n```"
        )

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

        if func_name == "bash":
            exit_code = tool_result.get("exit_code", "?")
            command = str(tool_result.get("command_summary") or "bash command")
            patch_count = int(tool_result.get("patch_count", 0) or 0)
            expect_file_changes = bool(tool_result.get("expect_file_changes"))

            patch_summary = (
                f"created {patch_count} diff patch"
                f"{'' if patch_count == 1 else 'es'}"
                if patch_count
                else "created no diff patch"
            )
            mismatch = ""
            if expect_file_changes and patch_count == 0 and exit_code == 0:
                mismatch = " (expected file edits, but none were detected)"
            elif not expect_file_changes and patch_count > 0:
                mismatch = " (unexpected file edits detected)"

            return f"`{command}` exited {exit_code}; {patch_summary}{mismatch}."

        if func_name == "delegate_to_subagent":
            status = tool_result.get("status", "unknown")
            return f"Sub-agent returned status `{status}`"

        return "Tool completed"

    @staticmethod
    def _summarize_command(command: str, max_chars: int = 120) -> str:
        compact = " ".join(command.strip().split())
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 16] + "...[truncated]"

    @staticmethod
    def _classify_bash_command(command: str) -> str:
        normalized = " ".join(command.lower().split())
        read_prefixes = (
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
            "git status",
            "git diff",
        )
        write_markers = (
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

        if any(marker in normalized for marker in write_markers):
            return "edit"
        if normalized.startswith(read_prefixes):
            return "inspect"
        return "generic"

    def _coerce_expect_file_changes(self, value: object, *, command: str) -> bool:
        if isinstance(value, bool):
            return value
        return self._classify_bash_command(command) == "edit"

    @staticmethod
    def _extract_command_summary(func_name: str, args: dict) -> str | None:
        if func_name != "bash":
            return None
        command = str(args.get("command", "")).strip()
        if not command:
            return None
        return MainAgent._summarize_command(command, 120)

    def _tool_start_detail(
        self,
        *,
        func_name: str,
        args: dict,
        call_index: int,
        call_count: int,
    ) -> str:
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

        return {
            "type": "action",
            "data": data,
        }

    @staticmethod
    def _response_event(*, response_id: str, content: str) -> dict:
        return {
            "type": "response",
            "data": {
                "response_id": response_id,
                "content": content,
            },
        }

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
