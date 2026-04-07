import json
import re

from researchkit.agents.base import SubAgentContext, Task
from researchkit.agents.research_agent import ResearchAgent
from researchkit.config.schema import ProviderConfig
from researchkit.literature.asta_mcp_client import AstaSnippet
from researchkit.literature.models import Author, Paper
from researchkit.literature.verify import VerificationReport
from researchkit.memory.schema import CitationEntry, PaperMemory, VenueConfig


class _ScriptedProvider:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.messages: list[list[dict]] = []

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        return ""

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        if False:
            yield ""

    async def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        self.messages.append(list(messages))
        index = len(self.messages) - 1
        if index < len(self.responses):
            return self.responses[index]
        return {"content": "", "tool_calls": []}


def _tool_call(name: str, arguments: dict) -> dict:
    return {
        "id": f"{name}-1",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def _build_paper() -> Paper:
    return Paper(
        paper_id="p1",
        title="Robust Graph Models",
        authors=(Author(name="Alice Smith"),),
        year=2024,
        abstract="A robust graph learning method.",
        venue="NeurIPS",
        citation_count=42,
        doi="10.1000/xyz123",
        url="https://example.org/p1",
        source="semantic_scholar",
    )


async def test_research_agent_runs_react_search_and_verification(monkeypatch):
    provider = _ScriptedProvider(
        [
            {
                "content": "Search for relevant papers.",
                "tool_calls": [
                    _tool_call("search_literature", {"query": "robust graph representation learning"})
                ],
            },
            {
                "content": "Verify the generated citations.",
                "tool_calls": [
                    _tool_call("verify_citations", {"use_latest_search_bibtex": True})
                ],
            },
            {
                "content": "Return the final summary.",
                "tool_calls": [
                    _tool_call(
                        "finish",
                        {
                            "summary": (
                                "Found recent robust graph papers and verified the generated citations."
                            )
                        },
                    )
                ],
            },
        ]
    )

    class _FakeAstaClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def search_papers_by_relevance(self, *args, **kwargs):
            return [_build_paper()]

        async def search_paper_by_title(self, *args, **kwargs):
            return []

        async def search_authors_by_name(self, *args, **kwargs):
            return []

        async def get_author_papers(self, *args, **kwargs):
            return []

        async def get_paper(self, paper_id, *args, **kwargs):
            paper = _build_paper()
            return Paper(**{**paper.__dict__, "paper_id": paper_id})

        async def get_citations(self, *args, **kwargs):
            return []

        async def snippet_search(self, *args, **kwargs):
            return [
                AstaSnippet(
                    paper_id="p1",
                    paper_title="Robust Graph Models",
                    text="A robust graph learning method.",
                )
            ]

    def _fake_papers_to_bibtex(papers):
        return "@article{smith2024robust,\n  title={Robust Graph Models}\n}\n"

    def _fake_verify_citations(*args, **kwargs):
        return VerificationReport(
            total=1,
            verified=1,
            suspicious=0,
            hallucinated=0,
            skipped=0,
        )

    monkeypatch.setattr("researchkit.agents.research_agent.create_provider", lambda config: provider)
    monkeypatch.setattr(
        "researchkit.agents.research_agent.ResearchAgent._create_asta_client",
        lambda self, **kwargs: _FakeAstaClient(),
    )
    monkeypatch.setattr(
        "researchkit.agents.research_agent.papers_to_bibtex",
        _fake_papers_to_bibtex,
    )
    monkeypatch.setattr(
        "researchkit.agents.research_agent.verify_citations",
        _fake_verify_citations,
    )

    agent = ResearchAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            asta_api_key="asta-key",
            max_tool_iterations=6,
        )
    )
    result = await agent.execute(
        Task(
            type="research",
            description="Search recent robust graph papers and verify citations",
        ),
        memory=PaperMemory(project_id="p1"),
    )

    assert result.status == "completed"
    assert "Found recent robust graph papers" in result.content
    assert len(result.artifacts) == 2
    assert result.artifacts[0]["type"] == "literature_search_result"
    assert result.artifacts[1]["type"] == "citation_verification_result"


async def test_research_agent_verify_only_request_skips_search(monkeypatch):
    provider = _ScriptedProvider(
        [
            {
                "content": "Verify only.",
                "tool_calls": [
                    _tool_call(
                        "verify_citations",
                        {"bibtex": "@article{a, title={A paper}, year={2024}}"},
                    )
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    _tool_call(
                        "finish",
                        {"summary": "Verified the provided BibTeX without running a literature search."},
                    )
                ],
            },
        ]
    )
    called = {"search": False, "verify": False}

    def _fake_verify_citations(*args, **kwargs):
        called["verify"] = True
        return VerificationReport(total=1, verified=1, suspicious=0, hallucinated=0, skipped=0)

    def _fake_create_asta_client(self, **kwargs):
        called["search"] = True
        raise AssertionError("ASTA client should not be created for verify-only requests")

    monkeypatch.setattr("researchkit.agents.research_agent.create_provider", lambda config: provider)
    monkeypatch.setattr(
        "researchkit.agents.research_agent.ResearchAgent._create_asta_client",
        _fake_create_asta_client,
    )
    monkeypatch.setattr(
        "researchkit.agents.research_agent.verify_citations",
        _fake_verify_citations,
    )

    agent = ResearchAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            max_tool_iterations=4,
        )
    )
    result = await agent.execute(
        Task(
            type="research",
            description=(
                "Verify these citations only:\n"
                "```bibtex\n@article{a, title={A paper}, year={2024}}\n```"
            ),
        ),
        memory=None,
    )

    assert result.status == "completed"
    assert called["search"] is False
    assert called["verify"] is True
    assert any(a["type"] == "citation_verification_result" for a in result.artifacts)


async def test_research_agent_view_workspace_tool_reads_context(monkeypatch, tmp_path):
    provider = _ScriptedProvider(
        [
            {
                "content": "Inspect the active file before searching.",
                "tool_calls": [
                    _tool_call(
                        "str_replace_editor",
                        {"command": "view", "path": "main.tex", "view_range": [1, 2]},
                    )
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    _tool_call(
                        "finish",
                        {"summary": "Inspected `main.tex` to ground the research request in the current draft."},
                    )
                ],
            },
        ]
    )
    monkeypatch.setattr("researchkit.agents.research_agent.create_provider", lambda config: provider)

    (tmp_path / "main.tex").write_text("Intro line\nMethod line\n", encoding="utf-8")

    agent = ResearchAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            max_tool_iterations=4,
        )
    )
    result = await agent.execute(
        Task(type="research", description="Review the active draft before searching for citations."),
        memory=PaperMemory(project_id="p1"),
        context=SubAgentContext(workspace_path=str(tmp_path), file_path="main.tex"),
    )

    assert result.status == "completed"
    assert "Inspected `main.tex`" in result.content
    assert any("Intro line" in message["content"] for message in provider.messages[1] if message["role"] == "user")


async def test_research_agent_returns_partial_summary_when_iteration_limit_is_hit(
    monkeypatch, tmp_path
):
    provider = _ScriptedProvider(
        [
            {
                "content": "Keep inspecting the draft.",
                "tool_calls": [
                    _tool_call(
                        "str_replace_editor",
                        {"command": "view", "path": "draft.tex", "view_range": [1, 1]},
                    )
                ],
            },
            {
                "content": "Keep inspecting the draft.",
                "tool_calls": [
                    _tool_call(
                        "str_replace_editor",
                        {"command": "view", "path": "draft.tex", "view_range": [1, 1]},
                    )
                ],
            },
        ]
    )
    monkeypatch.setattr("researchkit.agents.research_agent.create_provider", lambda config: provider)
    tmp_path.joinpath("draft.tex").write_text("line one\n", encoding="utf-8")

    agent = ResearchAgent(
        ProviderConfig(
            provider_type="custom",
            model="dummy-model",
            max_tool_iterations=2,
        )
    )
    result = await agent.execute(
        Task(type="research", description="Investigate related work for the current section."),
        memory=PaperMemory(project_id="p1"),
        context=SubAgentContext(workspace_path=str(tmp_path), file_path="draft.tex"),
    )

    assert result.status == "completed"
    assert "Reached the research tool iteration limit" in result.content


def test_build_publication_date_range_handles_venue_config_without_year():
    memory = PaperMemory(
        project_id="p1",
        venue=VenueConfig(name="FPT", doc_class="fpt"),
    )

    date_range = ResearchAgent._build_publication_date_range(
        "find repository-level c-to-rust migration papers",
        memory,
    )

    assert re.fullmatch(r"\d{4}:", date_range)


def test_extract_title_queries_resolves_citation_keys_from_memory():
    memory = PaperMemory(
        project_id="p1",
        citations=[
            CitationEntry(
                key="Emre2021TranslatingCTD",
                title="Translating C to safer Rust",
                year="2021",
            ),
            CitationEntry(
                key="Cai2025RustMapTPA",
                title="RustMap: Towards Project-Scale C-to-Rust Migration via Program Analysis and LLM",
                year="2025",
            ),
        ],
    )

    titles = ResearchAgent._extract_title_queries(
        (
            "Read the bibliography and prioritize Emre2021TranslatingCTD, "
            "Cai2025RustMapTPA, and Emre2021TranslatingCTD."
        ),
        memory,
    )

    assert titles == [
        "Translating C to safer Rust",
        "RustMap: Towards Project-Scale C-to-Rust Migration via Program Analysis and LLM",
    ]


def test_build_search_query_prefers_resolved_titles_from_memory():
    memory = PaperMemory(
        project_id="p1",
        citations=[
            CitationEntry(
                key="Emre2021TranslatingCTD",
                title="Translating C to safer Rust",
                year="2021",
            ),
            CitationEntry(
                key="Ling2022InRWE",
                title="In Rust We Trust – A Transpiler from Unsafe C to Safer Rust",
                year="2022",
            ),
        ],
    )

    query = ResearchAgent._build_search_query(
        "Analyze Emre2021TranslatingCTD and Ling2022InRWE for the introduction.",
        memory,
    )

    assert query == (
        "Translating C to safer Rust ; "
        "In Rust We Trust – A Transpiler from Unsafe C to Safer Rust"
    )


def test_build_user_message_includes_workspace_context_for_nested_project(tmp_path):
    paper_dir = tmp_path / "MigraAgent-paper"
    paper_dir.mkdir()
    (paper_dir / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")

    agent = ResearchAgent()
    message = agent._build_user_message(
        Task(type="research", description="Inspect the workspace before searching."),
        memory=None,
        context=SubAgentContext(
            workspace_path=str(tmp_path),
            file_path="MigraAgent-paper/main.tex",
        ),
    )

    assert f"Working directory for `str_replace_editor`: `{paper_dir}`." in message
    assert f"Primary paper directory inside the workspace: `{paper_dir}`." in message
    assert f"Active file path: `{paper_dir / 'main.tex'}`." in message
    assert f"- `{paper_dir / 'main.tex'}`" in message
