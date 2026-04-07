import json
import re
import sys
import types
from pathlib import Path

fake_db_module = types.ModuleType("researchkit.db")
fake_db_module.get_db = lambda: None

async def _fake_close_client():
    return None

fake_db_module.close_client = _fake_close_client
sys.modules.setdefault("researchkit.db", fake_db_module)

from researchkit.agents.main_agent import EditorRetryState, MainAgent  # noqa: E402
from researchkit.agents.base import Result  # noqa: E402
from researchkit.agents.patch_utils import compute_minimal_edit  # noqa: E402
from researchkit.agents.runner_client import ChangedFile, RunnerExecutionResult  # noqa: E402
from researchkit.agents.tools import AGENT_TOOLS  # noqa: E402
from researchkit.config.schema import ProviderConfig  # noqa: E402


class _DummyProvider:
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        return ""

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        if False:
            yield ""

    async def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        return {"content": "", "tool_calls": []}


class _FakeConversationCollection:
    def __init__(self, messages: list[dict] | None = None):
        self.messages = messages or []
        self.saved_messages: list[dict] | None = None
        self.last_find_query: dict | None = None
        self.last_update_query: dict | None = None

    async def find_one(self, query: dict) -> dict | None:
        self.last_find_query = dict(query)
        return {
            "project_id": query["project_id"],
            "conversation_id": query.get("conversation_id", "default"),
            "messages": list(self.messages),
        }

    async def update_one(self, query: dict, payload: dict, upsert: bool = False) -> None:
        self.last_update_query = dict(query)
        self.saved_messages = payload["$set"]["messages"]
        self.messages = list(self.saved_messages)


class _FakeDB:
    def __init__(self, messages: list[dict] | None = None):
        self.researchkitConversations = _FakeConversationCollection(messages)


def _build_agent(
    monkeypatch, tmp_path, *, runner_url: str | None = "http://runner.local"
) -> MainAgent:
    monkeypatch.setattr(
        "researchkit.agents.main_agent.create_provider",
        lambda config: _DummyProvider(),
    )
    config = ProviderConfig(
        provider_type="custom",
        model="dummy-model",
        workspace_path=str(tmp_path),
        runner_url=runner_url,
        allowed_workspace_roots=[str(tmp_path)],
    )
    return MainAgent(config)


def _apply_patch_to_text(text: str, patch: dict) -> str:
    return (
        text[: patch["selection_from"]]
        + patch["replacement_text"]
        + text[patch["selection_to"] :]
    )


def test_compute_minimal_edit_for_mid_file_change():
    before = "alpha\nbeta\ncharlie\n"
    after = "alpha\nbeta updated\ncharlie\n"

    selection_from, selection_to, original_text, replacement_text = (
        compute_minimal_edit(before, after)
    )

    assert selection_from == len("alpha\nbeta")
    assert selection_to == len("alpha\nbeta")
    assert original_text == ""
    assert replacement_text == " updated"


def test_compute_minimal_edit_for_full_replacement():
    before = "old text"
    after = "new text"

    selection_from, selection_to, original_text, replacement_text = (
        compute_minimal_edit(before, after)
    )

    assert selection_from == 0
    assert selection_to == 3
    assert original_text == "old"
    assert replacement_text == "new"


def test_compute_minimal_edit_for_deletion():
    before = "abc123xyz"
    after = "abcxyz"

    selection_from, selection_to, original_text, replacement_text = (
        compute_minimal_edit(before, after)
    )

    assert selection_from == 3
    assert selection_to == 6
    assert original_text == "123"
    assert replacement_text == ""


def test_agent_tools_include_str_replace_editor_and_execution_only_bash():
    tool_names = [tool["function"]["name"] for tool in AGENT_TOOLS]

    assert "str_replace_editor" in tool_names

    bash_tool = next(tool for tool in AGENT_TOOLS if tool["function"]["name"] == "bash")
    assert "Do not use bash to read or edit workspace files" in bash_tool["function"]["description"]
    assert "expect_file_changes" not in bash_tool["function"]["parameters"]["properties"]


async def test_main_agent_rejects_bash_inspection_commands(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path)

    execution = await agent._execute_bash_tool(
        args={"command": "rg -n TODO ."},
        project_id="p1",
        files=None,
        action_id="a1",
    )

    assert execution["tool_result"]["command_intent"] == "inspect"
    assert "Bash is reserved for execution-oriented tasks only" in execution["tool_result"]["error"]


async def test_main_agent_allows_bash_execution_commands(monkeypatch, tmp_path):
    class _FakeRunnerClient:
        def __init__(self, base_url: str):
            self.base_url = base_url

        async def execute(self, **kwargs):
            return RunnerExecutionResult(
                exit_code=0,
                stdout="tests passed",
                stderr="",
                changed_files=[],
            )

    monkeypatch.setattr("researchkit.agents.main_agent.RunnerClient", _FakeRunnerClient)
    agent = _build_agent(monkeypatch, tmp_path)

    execution = await agent._execute_bash_tool(
        args={"command": "pytest -q"},
        project_id="p1",
        files=None,
        action_id="a1",
    )

    assert execution["tool_result"]["exit_code"] == 0
    assert execution["tool_result"]["command_intent"] == "execute"
    assert execution["tool_result"]["changed_file_count"] == 0
    assert execution["patches"] == []
    assert execution["edit_event"] is None


async def test_delegate_to_subagent_captures_workspace_patches(monkeypatch, tmp_path):
    class _EditingSubAgent:
        async def execute(self, task, memory, context=None):
            (tmp_path / "main.tex").write_text(
                "intro\n\\input{sections/introduction_rewritten}\n",
                encoding="utf-8",
            )
            sections_dir = tmp_path / "sections"
            sections_dir.mkdir(exist_ok=True)
            (sections_dir / "introduction_rewritten.tex").write_text(
                "Rewritten introduction.\n",
                encoding="utf-8",
            )
            return Result(
                status="completed",
                content="Updated main input and drafted the new introduction.",
            )

    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    (tmp_path / "main.tex").write_text("intro\n\\input{sections/introduction}\n", encoding="utf-8")
    agent.sub_agents["research"] = _EditingSubAgent()

    execution = await agent._execute_tool_call(
        func_name="delegate_to_subagent",
        args={
            "agent_type": "research",
            "task_description": "Rewrite the introduction in a new file and update main.tex",
        },
        memory=None,
        project_id="p1",
        files=None,
        action_id="a1",
    )

    assert execution["tool_result"]["status"] == "completed"
    assert len(execution["patches"]) == 2

    patches_by_path = {patch["file_path"]: patch for patch in execution["patches"]}
    assert patches_by_path["main.tex"]["change_type"] == "edit"
    assert patches_by_path["sections/introduction_rewritten.tex"]["change_type"] == "create"
    assert (
        _apply_patch_to_text(
            "",
            patches_by_path["sections/introduction_rewritten.tex"],
        )
        == "Rewritten introduction.\n"
    )


async def test_delegate_to_subagent_passes_context_and_overlay_workspace(monkeypatch, tmp_path):
    captured = {}

    class _InspectingSubAgent:
        async def execute(self, task, memory, context=None):
            captured["task"] = task
            captured["memory"] = memory
            captured["context"] = context
            preview = ""
            if context and context.workspace_path:
                preview = (Path(context.workspace_path) / "draft.tex").read_text(encoding="utf-8")
            return Result(
                status="completed",
                content=f"Inspected overlay workspace.\n\n{preview}".strip(),
            )

    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    agent.sub_agents["research"] = _InspectingSubAgent()

    execution = await agent._execute_tool_call(
        func_name="delegate_to_subagent",
        args={
            "agent_type": "research",
            "task_description": "Inspect the selected draft before searching.",
        },
        memory=None,
        project_id="p1",
        files={"draft.tex": "Intro line\nMethod line\n"},
        action_id="a1",
        file_path="draft.tex",
        selected_text="Intro line",
        cursor_line=1,
        line_from=1,
        line_to=1,
    )

    context = captured["context"]
    assert context is not None
    assert context.project_id == "p1"
    assert context.file_path == "draft.tex"
    assert context.selected_text == "Intro line"
    assert context.cursor_line == 1
    assert context.line_from == 1
    assert context.line_to == 1
    assert Path(context.workspace_path).joinpath("draft.tex").read_text(encoding="utf-8") == (
        "Intro line\nMethod line\n"
    )
    assert execution["tool_result"]["status"] == "completed"
    assert execution["patches"] == []


def test_build_workspace_prompt_context_includes_nested_paper_directory(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)

    try:
        context = agent._build_workspace_prompt_context(
            project_id="p1",
            files={
                "MigraAgent-paper/main.tex": "\\documentclass{article}\n",
                "MigraAgent-paper/main.bib": "@article{ref}\n",
            },
            file_path=None,
        )
    finally:
        agent._cleanup_overlay_workspace("p1")

    assert re.search(
        r"Working directory for `str_replace_editor`: `/.+/MigraAgent-paper`\.",
        context,
    )
    assert re.search(
        r"Primary paper directory inside the workspace: `/.+/MigraAgent-paper`\.",
        context,
    )
    assert re.search(r"- `/.+/MigraAgent-paper/main\.bib`", context)
    assert re.search(r"- `/.+/MigraAgent-paper/main\.tex`", context)


async def test_main_agent_executes_str_replace_editor_and_returns_edit_event(
    monkeypatch, tmp_path
):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("alpha\nbeta\n", encoding="utf-8")

    execution = await agent._execute_tool_call(
        func_name="str_replace_editor",
        args={
            "command": "str_replace",
            "path": str(paper_path),
            "old_str": "beta",
            "new_str": "gamma",
        },
        memory=None,
        project_id="p1",
        files=None,
        action_id="a1",
    )

    assert execution["tool_result"]["summary"] == f"Edited `{paper_path}` with `str_replace`."
    assert execution["edit_event"]["command"] == "str_replace"
    assert execution["edit_event"]["path"] == "paper.tex"
    assert paper_path.read_text(encoding="utf-8") == "alpha\ngamma\n"


async def test_main_agent_rejects_missing_workspace_path_before_editor_runs(monkeypatch):
    monkeypatch.setattr(
        "researchkit.agents.main_agent.create_provider",
        lambda config: _DummyProvider(),
    )
    agent = MainAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            workspace_path="/projects/default",
            runner_url=None,
        )
    )

    execution = await agent._execute_tool_call(
        func_name="str_replace_editor",
        args={"command": "view", "path": "."},
        memory=None,
        project_id="p1",
        files=None,
        action_id="a1",
    )

    assert execution["tool_result"]["error"] == (
        "workspace_path does not exist: `/projects/default`."
    )
    assert execution["edit_event"] is None


async def test_main_agent_uses_request_files_for_editor_when_workspace_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        "researchkit.agents.main_agent.create_provider",
        lambda config: _DummyProvider(),
    )
    agent = MainAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            workspace_path="/projects/default",
            runner_url=None,
        )
    )

    execution = await agent._execute_tool_call(
        func_name="str_replace_editor",
        args={
            "command": "str_replace",
            "path": "sections/introduction.tex",
            "old_str": "beta",
            "new_str": "gamma",
        },
        memory=None,
        project_id="p1",
        files={"sections/introduction.tex": "alpha\nbeta\n"},
        action_id="a1",
    )

    assert execution["tool_result"].get("error") is None
    assert execution["tool_result"]["path"] == "sections/introduction.tex"
    assert execution["tool_result"]["absolute_path"] is None
    assert len(execution["patches"]) == 1
    assert execution["patches"][0]["file_path"] == "sections/introduction.tex"
    assert _apply_patch_to_text(
        "alpha\nbeta\n",
        execution["patches"][0],
    ) == "alpha\ngamma\n"


async def test_main_agent_requires_view_before_retrying_failed_edit(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("alpha\nbeta\n", encoding="utf-8")
    retry_state = EditorRetryState()

    first_execution = await agent._execute_tool_call(
        func_name="str_replace_editor",
        args={
            "command": "str_replace",
            "path": "paper.tex",
            "old_str": "missing",
            "new_str": "gamma",
        },
        memory=None,
        project_id="p1",
        files=None,
        editor_retry_state=retry_state,
        action_id="a1",
    )
    agent._update_editor_retry_state(
        state=retry_state,
        func_name="str_replace_editor",
        args={"command": "str_replace", "path": "paper.tex"},
        tool_result=first_execution["tool_result"],
        patches=first_execution["patches"],
    )

    second_execution = await agent._execute_tool_call(
        func_name="str_replace_editor",
        args={
            "command": "insert",
            "path": "paper.tex",
            "insert_line": 1,
            "new_str": "gamma\n",
        },
        memory=None,
        project_id="p1",
        files=None,
        editor_retry_state=retry_state,
        action_id="a2",
    )

    assert first_execution["tool_result"]["error_code"] == "str_replace_no_match"
    assert second_execution["tool_result"]["error_code"] == "view_required_after_failed_edit"
    assert "must use `view`" in second_execution["tool_result"]["error"]


async def test_main_agent_rejects_create_for_existing_viewed_file(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("alpha\n", encoding="utf-8")
    retry_state = EditorRetryState(viewed_existing_paths={"paper.tex"})

    execution = await agent._execute_tool_call(
        func_name="str_replace_editor",
        args={
            "command": "create",
            "path": "paper.tex",
            "file_text": "replacement\n",
        },
        memory=None,
        project_id="p1",
        files=None,
        editor_retry_state=retry_state,
        action_id="a1",
    )

    assert execution["tool_result"]["error_code"] == "create_existing_file"
    assert "already exists" in execution["tool_result"]["error"]
    assert "brand-new files" in execution["tool_result"]["guidance"]


async def test_main_agent_allows_bash_with_overlay_files_when_workspace_is_missing(
    monkeypatch,
):
    class _FakeRunnerClient:
        def __init__(self, base_url: str):
            self.base_url = base_url

        async def execute(self, **kwargs):
            return RunnerExecutionResult(
                exit_code=0,
                stdout="ok",
                stderr="",
                changed_files=[
                    ChangedFile(
                        path="sections/introduction.tex",
                        before="alpha\nbeta\n",
                        after="alpha\ngamma\n",
                    )
                ],
            )

    monkeypatch.setattr(
        "researchkit.agents.main_agent.create_provider",
        lambda config: _DummyProvider(),
    )
    monkeypatch.setattr("researchkit.agents.main_agent.RunnerClient", _FakeRunnerClient)
    agent = MainAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            workspace_path="/projects/default",
            runner_url="http://runner.local",
        )
    )

    execution = await agent._execute_tool_call(
        func_name="bash",
        args={"command": "pytest -q"},
        memory=None,
        project_id="p1",
        files={"sections/introduction.tex": "alpha\nbeta\n"},
        action_id="a1",
    )

    assert execution["tool_result"].get("error") is None
    assert execution["tool_result"]["changed_file_count"] == 1
    assert len(execution["patches"]) == 1
    assert execution["patches"][0]["file_path"] == "sections/introduction.tex"
    assert _apply_patch_to_text(
        "alpha\nbeta\n",
        execution["patches"][0],
    ) == "alpha\ngamma\n"


async def test_run_tool_loop_streams_edit_events(monkeypatch, tmp_path):
    class _LoopProvider(_DummyProvider):
        def __init__(self):
            self._responses = iter(
                [
                    {
                        "content": "Updating the file now.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "str_replace_editor",
                                    "arguments": json.dumps(
                                        {
                                            "command": "create",
                                            "path": str(tmp_path / "draft.tex"),
                                            "file_text": "hello\n",
                                        }
                                    ),
                                }
                            }
                        ],
                    },
                    {"content": "Done.", "tool_calls": []},
                ]
            )

        async def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
            return next(self._responses)

    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    agent.provider = _LoopProvider()

    events = [
        event
        async for event in agent._run_tool_loop(
            system_prompt="system",
            conversation=[],
            memory=None,
            project_id="p1",
            files=None,
            run_id="run-1",
        )
    ]

    assert any(event["type"] == "edit" for event in events)
    assert not any(
        event["type"] == "response" and event.get("data", {}).get("kind") == "tool_output"
        for event in events
    )
    assert (tmp_path / "draft.tex").read_text(encoding="utf-8") == "hello\n"


async def test_run_tool_loop_blocks_completion_until_failed_edit_is_fixed(monkeypatch, tmp_path):
    class _LoopProvider(_DummyProvider):
        def __init__(self):
            self.calls: list[list[dict]] = []
            self._responses = iter(
                [
                    {
                        "content": "Trying the replacement.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "str_replace_editor",
                                    "arguments": json.dumps(
                                        {
                                            "command": "str_replace",
                                            "path": "paper.tex",
                                            "old_str": "missing",
                                            "new_str": "gamma",
                                        }
                                    ),
                                }
                            }
                        ],
                    },
                    {"content": "Done.", "tool_calls": []},
                    {
                        "content": "Re-reading the file.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "str_replace_editor",
                                    "arguments": json.dumps(
                                        {
                                            "command": "view",
                                            "path": "paper.tex",
                                            "view_range": [1, -1],
                                        }
                                    ),
                                }
                            }
                        ],
                    },
                    {
                        "content": "Applying the exact edit.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "str_replace_editor",
                                    "arguments": json.dumps(
                                        {
                                            "command": "str_replace",
                                            "path": "paper.tex",
                                            "old_str": "beta",
                                            "new_str": "gamma",
                                        }
                                    ),
                                }
                            }
                        ],
                    },
                    {"content": "Done.", "tool_calls": []},
                ]
            )

        async def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
            self.calls.append(list(messages))
            return next(self._responses)

    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    agent.provider = _LoopProvider()
    (tmp_path / "paper.tex").write_text("alpha\nbeta\n", encoding="utf-8")

    events = [
        event
        async for event in agent._run_tool_loop(
            system_prompt="system",
            conversation=[],
            memory=None,
            project_id="p1",
            files=None,
            run_id="run-1",
        )
    ]

    assert (tmp_path / "paper.tex").read_text(encoding="utf-8") == "alpha\ngamma\n"
    assert len(agent.provider.calls) == 5
    assert any(event["type"] == "edit" for event in events)
    assert any(
        "Do not finalize yet. A requested file edit failed"
        in message["content"]
        for message in agent.provider.calls[2]
        if message["role"] == "user"
    )


def test_build_tool_result_message_for_editor_is_compact(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)

    message = agent._build_tool_result_message(
        func_name="str_replace_editor",
        args={"command": "view", "path": "paper.tex"},
        tool_result={
            "command": "view",
            "path": "paper.tex",
            "status": "completed",
            "summary": "Viewed `paper.tex`.",
            "absolute_path": "/tmp/researchkit/paper.tex",
        },
        visible_text="Updated `/tmp/researchkit/paper.tex`.\n\n1\tHello world",
    )

    assert message.startswith("Tool result for `str_replace_editor`:")
    assert "```json" not in message
    assert "absolute_path" not in message
    assert "Visible output:" in message
    assert "paper.tex" in message


def test_action_event_includes_artifacts_and_output(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    event = agent._action_event(
        tool="delegate_to_subagent",
        status="completed",
        iteration=1,
        detail="done",
        artifacts=[{"type": "literature_search_result"}],
        output="sub-agent debug output",
    )

    assert event["type"] == "action"
    assert event["data"]["artifacts"] == [{"type": "literature_search_result"}]
    assert event["data"]["output"] == "sub-agent debug output"


async def test_load_conversation_filters_internal_tool_messages(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    fake_db = _FakeDB(
        [
            {"role": "user", "content": "keep this"},
            {
                "role": "user",
                "content": (
                    "Tool execution result (use this to decide the next step):\n"
                    "```json\n{\"tool\":\"str_replace_editor\"}\n```"
                ),
            },
            {"role": "assistant", "content": "Calling 1 tool call."},
            {
                "role": "assistant",
                "content": "final visible reply",
                "response_id": "r1",
                "actions": [
                    {
                        "tool": "bash",
                        "status": "completed",
                        "iteration": 1,
                        "detail": "done",
                    }
                ],
            },
        ]
    )
    monkeypatch.setattr("researchkit.agents.main_agent.get_db", lambda: fake_db)

    loaded = await agent._load_conversation(project_id="p1", conversation_id="thread-a")

    assert loaded == [
        {"role": "user", "content": "keep this"},
        {"role": "assistant", "content": "final visible reply"},
    ]
    assert fake_db.researchkitConversations.last_find_query == {
        "project_id": "p1",
        "conversation_id": "thread-a",
    }


async def test_handle_persists_only_clean_conversation_messages(monkeypatch, tmp_path):
    class _LoopProvider(_DummyProvider):
        def __init__(self):
            self._responses = iter(
                [
                    {
                        "content": "Updating the file now.",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "str_replace_editor",
                                    "arguments": json.dumps(
                                        {
                                            "command": "create",
                                            "path": "draft.tex",
                                            "file_text": "hello\n",
                                        }
                                    ),
                                }
                            }
                        ],
                    },
                    {"content": "Done.", "tool_calls": []},
                ]
            )

        async def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
            return next(self._responses)

    fake_db = _FakeDB(
        [
            {"role": "user", "content": "older user message"},
            {
                "role": "user",
                "content": "Tool result for `str_replace_editor`:\nError: stale internal message",
            },
            {"role": "assistant", "content": "Calling 1 tool call."},
            {"role": "assistant", "content": "older assistant message"},
        ]
    )
    monkeypatch.setattr("researchkit.agents.main_agent.get_db", lambda: fake_db)
    async def _fake_get_context_for_prompt(self, project_id: str) -> str:
        return ""

    monkeypatch.setattr(
        "researchkit.agents.main_agent.MemoryManager.get_context_for_prompt",
        _fake_get_context_for_prompt,
    )

    agent = _build_agent(monkeypatch, tmp_path, runner_url=None)
    agent.provider = _LoopProvider()

    events = [
        event
        async for event in agent.handle(
            project_id="p1",
            message="create a draft",
            conversation_id="thread-z",
            selected_text=None,
            memory=None,
        )
    ]

    assert any(event["type"] == "edit" for event in events)
    saved_messages = fake_db.researchkitConversations.saved_messages
    assert saved_messages is not None
    assert saved_messages[:3] == [
        {"role": "user", "content": "older user message"},
        {"role": "assistant", "content": "older assistant message"},
        {"role": "user", "content": "create a draft"},
    ]
    assert len(saved_messages) == 5
    first_assistant = saved_messages[3]
    assert first_assistant["role"] == "assistant"
    assert first_assistant["content"] == "Updating the file now."
    assert first_assistant["response_id"].startswith("run-")
    assert len(first_assistant["actions"]) == 2
    assert first_assistant["actions"][0]["status"] == "started"
    assert first_assistant["actions"][1]["status"] == "completed"
    assert len(first_assistant["patches"]) == 1
    assert first_assistant["patches"][0]["file_path"] == "draft.tex"

    second_assistant = saved_messages[4]
    assert second_assistant["role"] == "assistant"
    assert second_assistant["content"] == "Done."
    assert second_assistant["response_id"].startswith("run-")
    assert "actions" not in second_assistant
    assert "patches" not in second_assistant
    assert fake_db.researchkitConversations.last_update_query == {
        "project_id": "p1",
        "conversation_id": "thread-z",
    }
