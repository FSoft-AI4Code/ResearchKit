import asyncio
from types import SimpleNamespace

import pytest

from researchkit.literature import asta_mcp_client as asta_module


class _FakeTransport:
    async def __aenter__(self):
        return "read-stream", "write-stream", lambda: None

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeClientSession:
    def __init__(self, read_stream, write_stream):
        self.read_stream = read_stream
        self.write_stream = write_stream

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def initialize(self):
        return None

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name="search_papers_by_relevance")])


@pytest.mark.asyncio
async def test_asta_client_uses_legacy_http_client_argument(monkeypatch):
    calls = {}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            calls["async_client_kwargs"] = kwargs

        async def __aenter__(self):
            calls["async_client_entered"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            calls["async_client_exited"] = True
            return None

    def _fake_streamablehttp_client(url, *, http_client):
        calls["url"] = url
        calls["http_client"] = http_client
        return _FakeTransport()

    monkeypatch.setattr(asta_module, "ClientSession", _FakeClientSession)
    monkeypatch.setattr(asta_module, "streamablehttp_client", _fake_streamablehttp_client)
    monkeypatch.setattr(asta_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = asta_module.AstaMcpClient(
        "test-key",
        server_url="https://example.test/mcp",
        timeout_seconds=12.5,
    )

    async with client:
        assert calls["url"] == "https://example.test/mcp"
        assert calls["async_client_kwargs"] == {
            "headers": {"x-api-key": "test-key"},
            "timeout": 12.5,
        }
        assert calls["async_client_entered"] is True
        assert isinstance(calls["http_client"], _FakeAsyncClient)
        assert client.tool_names == {"search_papers_by_relevance"}

    assert calls["async_client_exited"] is True


@pytest.mark.asyncio
async def test_asta_client_uses_header_based_transport_when_http_client_is_unavailable(monkeypatch):
    calls = {}

    def _unexpected_async_client(**kwargs):
        raise AssertionError(f"httpx.AsyncClient should not be created: {kwargs}")

    def _fake_streamablehttp_client(url, *, headers=None, timeout=30):
        calls["url"] = url
        calls["headers"] = headers
        calls["timeout"] = timeout
        return _FakeTransport()

    monkeypatch.setattr(asta_module, "ClientSession", _FakeClientSession)
    monkeypatch.setattr(asta_module, "streamablehttp_client", _fake_streamablehttp_client)
    monkeypatch.setattr(asta_module.httpx, "AsyncClient", _unexpected_async_client)

    client = asta_module.AstaMcpClient(
        "test-key",
        server_url="https://example.test/mcp",
        timeout_seconds=7.0,
    )

    async with client:
        assert calls == {
            "url": "https://example.test/mcp",
            "headers": {"x-api-key": "test-key"},
            "timeout": 7.0,
        }
        assert client.tool_names == {"search_papers_by_relevance"}


@pytest.mark.asyncio
async def test_asta_client_times_out_hung_tool_calls(monkeypatch):
    class _HungClientSession(_FakeClientSession):
        async def call_tool(self, tool_name, arguments):
            await asyncio.sleep(3600)

    def _fake_streamablehttp_client(url, *, headers=None, timeout=30):
        return _FakeTransport()

    monkeypatch.setattr(asta_module, "ClientSession", _HungClientSession)
    monkeypatch.setattr(asta_module, "streamablehttp_client", _fake_streamablehttp_client)

    client = asta_module.AstaMcpClient(
        "test-key",
        server_url="https://example.test/mcp",
        timeout_seconds=0.01,
    )

    async with client:
        with pytest.raises(RuntimeError, match="Timed out after 0.01 seconds"):
            await client.search_papers_by_relevance("rust")


def test_extract_papers_reads_result_key_payload():
    payload = {
        "result": [
            {
                "paperId": "p1",
                "title": "CTRL: A Conditional Transformer Language Model for Controllable Generation",
                "year": 2019,
                "authors": [{"name": "N. Keskar"}],
                "journal": {"name": "ArXiv"},
                "url": "https://example.test/p1",
                "abstract": "Large-scale language models show promising text generation capabilities.",
            }
        ]
    }

    papers = asta_module.AstaMcpClient._extract_papers(payload)

    assert len(papers) == 1
    assert papers[0].paper_id == "p1"
    assert papers[0].title == "CTRL: A Conditional Transformer Language Model for Controllable Generation"
    assert papers[0].year == 2019


def test_extract_papers_reads_direct_paper_payload_without_treating_authors_as_items():
    payload = {
        "paperId": "p2",
        "title": "Analyzing the Structure of Attention in a Transformer Language Model",
        "year": 2019,
        "authors": [{"authorId": "a1", "name": "Jesse Vig"}],
        "journal": {"name": "BlackboxNLP"},
        "url": "https://example.test/p2",
        "abstract": "We analyze attention patterns in transformer language models.",
    }

    papers = asta_module.AstaMcpClient._extract_papers(payload)

    assert len(papers) == 1
    assert papers[0].paper_id == "p2"
    assert papers[0].authors[0].name == "Jesse Vig"


def test_extract_snippets_reads_nested_result_data_payload():
    payload = {
        "result": {
            "data": [
                {
                    "score": 0.42,
                    "paper": {
                        "corpusId": "202573071",
                        "title": "CTRL: A Conditional Transformer Language Model for Controllable Generation",
                    },
                    "snippet": {
                        "text": "CTRL: A Conditional Transformer Language Model for Controllable Generation",
                        "snippetKind": "title",
                    },
                }
            ]
        }
    }

    snippets = asta_module.AstaMcpClient._extract_snippets(payload)

    assert len(snippets) == 1
    assert snippets[0].paper_id == "202573071"
    assert snippets[0].paper_title == "CTRL: A Conditional Transformer Language Model for Controllable Generation"
    assert snippets[0].text == "CTRL: A Conditional Transformer Language Model for Controllable Generation"
    assert snippets[0].score == 0.42
