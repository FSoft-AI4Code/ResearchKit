from __future__ import annotations

import asyncio
import inspect
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx

from researchkit.literature.models import Author, Paper

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:  # pragma: no cover - guarded at runtime in __aenter__
    ClientSession = None  # type: ignore[assignment]
    streamablehttp_client = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_DEFAULT_ASTA_MCP_URL = "https://asta-tools.allen.ai/mcp/v1"
_DEFAULT_PAPER_FIELDS = "abstract,authors,journal,url,venue,year"
_DEFAULT_AUTHOR_FIELDS = "name,url,affiliations,paperCount,citationCount,hIndex"


@dataclass(frozen=True)
class AstaSnippet:
    paper_id: str
    paper_title: str
    text: str
    score: float | None = None


class _RateLimiter:
    def __init__(self, requests_per_second: float):
        self._interval = 1.0 / max(requests_per_second, 0.1)
        self._lock = asyncio.Lock()
        self._next_available = 0.0

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._lock:
            now = loop.time()
            if now < self._next_available:
                await asyncio.sleep(self._next_available - now)
                now = loop.time()
            self._next_available = now + self._interval


class AstaMcpClient:
    def __init__(
        self,
        api_key: str,
        *,
        server_url: str | None = None,
        requests_per_second: float = 8.0,
        timeout_seconds: float = 30.0,
    ):
        self.api_key = api_key.strip()
        self.server_url = (server_url or _DEFAULT_ASTA_MCP_URL).strip()
        self.timeout_seconds = timeout_seconds
        self._rate_limiter = _RateLimiter(requests_per_second)
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tool_names: set[str] = set()

    async def __aenter__(self) -> AstaMcpClient:
        if ClientSession is None or streamablehttp_client is None:
            raise RuntimeError("The `mcp` package is required for ASTA search support.")
        if not self.api_key:
            raise RuntimeError("ASTA API key is required for research search.")

        self._exit_stack = AsyncExitStack()
        read_stream, write_stream, _ = await self._exit_stack.enter_async_context(
            await self._open_streamable_http_transport()
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        tools = await self._session.list_tools()
        self._tool_names = {tool.name for tool in tools.tools}
        logger.info("ASTA MCP connected with tools: %s", ", ".join(sorted(self._tool_names)))
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None
        self._tool_names = set()

    @property
    def tool_names(self) -> set[str]:
        return set(self._tool_names)

    async def _open_streamable_http_transport(self):
        signature = inspect.signature(streamablehttp_client)
        headers = {"x-api-key": self.api_key}
        if "http_client" in signature.parameters:
            http_client = await self._exit_stack.enter_async_context(
                httpx.AsyncClient(
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            )
            return streamablehttp_client(
                self.server_url,
                http_client=http_client,
            )
        return streamablehttp_client(
            self.server_url,
            headers=headers,
            timeout=self.timeout_seconds,
        )

    async def search_papers_by_relevance(
        self,
        keyword: str,
        *,
        limit: int = 10,
        publication_date_range: str = "",
        venues: str = "",
        fields: str = _DEFAULT_PAPER_FIELDS,
    ) -> list[Paper]:
        payload = await self._call_tool(
            "search_papers_by_relevance",
            {
                "keyword": keyword,
                "fields": fields,
                "limit": limit,
                "publication_date_range": publication_date_range,
                "venues": venues,
            },
        )
        return self._extract_papers(payload)

    async def search_paper_by_title(
        self,
        title: str,
        *,
        publication_date_range: str = "",
        venues: str = "",
        fields: str = _DEFAULT_PAPER_FIELDS,
    ) -> list[Paper]:
        payload = await self._call_tool(
            "search_paper_by_title",
            {
                "title": title,
                "fields": fields,
                "publication_date_range": publication_date_range,
                "venues": venues,
            },
        )
        return self._extract_papers(payload)

    async def get_paper(self, paper_id: str, *, fields: str = _DEFAULT_PAPER_FIELDS) -> Paper | None:
        payload = await self._call_tool("get_paper", {"paper_id": paper_id, "fields": fields})
        papers = self._extract_papers(payload)
        return papers[0] if papers else None

    async def get_citations(
        self,
        paper_id: str,
        *,
        limit: int = 10,
        publication_date_range: str = "",
        fields: str = _DEFAULT_PAPER_FIELDS,
    ) -> list[Paper]:
        payload = await self._call_tool(
            "get_citations",
            {
                "paper_id": paper_id,
                "fields": fields,
                "limit": limit,
                "publication_date_range": publication_date_range,
            },
        )
        return self._extract_papers(payload)

    async def search_authors_by_name(
        self,
        name: str,
        *,
        limit: int = 5,
        fields: str = _DEFAULT_AUTHOR_FIELDS,
    ) -> list[dict[str, Any]]:
        payload = await self._call_tool(
            "search_authors_by_name",
            {"name": name, "fields": fields, "limit": limit},
        )
        return self._extract_authors(payload)

    async def get_author_papers(
        self,
        author_id: str,
        *,
        limit: int = 10,
        publication_date_range: str = "",
        paper_fields: str = _DEFAULT_PAPER_FIELDS,
    ) -> list[Paper]:
        payload = await self._call_tool(
            "get_author_papers",
            {
                "author_id": author_id,
                "paper_fields": paper_fields,
                "limit": limit,
                "publication_date_range": publication_date_range,
            },
        )
        return self._extract_papers(payload)

    async def snippet_search(
        self,
        query: str,
        *,
        limit: int = 5,
        venues: str = "",
        paper_ids: list[str] | None = None,
        inserted_before: str = "",
    ) -> list[AstaSnippet]:
        arguments: dict[str, Any] = {"query": query, "limit": limit, "venues": venues}
        if paper_ids:
            arguments["paper_ids"] = ",".join(paper_ids[:100])
        if inserted_before:
            arguments["inserted_before"] = inserted_before
        payload = await self._call_tool("snippet_search", arguments)
        return self._extract_snippets(payload)

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("ASTA MCP client session is not initialized.")
        if tool_name not in self._tool_names:
            raise RuntimeError(f"ASTA MCP tool unavailable: {tool_name}")

        sanitized = {
            key: value
            for key, value in arguments.items()
            if value not in ("", None, [])
        }
        last_error: Exception | None = None
        for attempt in range(3):
            await self._rate_limiter.acquire()
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(tool_name, arguments=sanitized),
                    timeout=self.timeout_seconds,
                )
                return self._extract_structured_content(result)
            except asyncio.TimeoutError as exc:
                last_error = TimeoutError(
                    f"Timed out after {self.timeout_seconds} seconds calling ASTA tool `{tool_name}`."
                )
                if attempt >= 2:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= 2 or not self._is_retryable(exc):
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"ASTA tool call failed for {tool_name}: {last_error}") from last_error

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {429, 500, 502, 503, 504}
        return isinstance(exc, (httpx.HTTPError, TimeoutError))

    @staticmethod
    def _extract_structured_content(result: Any) -> Any:
        structured = getattr(result, "structuredContent", None)
        if structured not in (None, ""):
            return structured

        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if not isinstance(text, str):
                continue
            text = text.strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
        return {}

    @classmethod
    def _extract_papers(cls, payload: Any) -> list[Paper]:
        papers: list[Paper] = []
        for item in cls._collect_items(payload):
            paper_obj = item
            if isinstance(item, dict):
                for wrapper_key in ("paper", "citingPaper", "citedPaper"):
                    wrapped = item.get(wrapper_key)
                    if isinstance(wrapped, dict):
                        paper_obj = wrapped
                        break
            paper = cls._to_paper(paper_obj)
            if paper is not None:
                papers.append(paper)
        return papers

    @classmethod
    def _extract_authors(cls, payload: Any) -> list[dict[str, Any]]:
        authors: list[dict[str, Any]] = []
        for item in cls._collect_items(payload):
            if not isinstance(item, dict):
                continue
            author_id = str(
                item.get("authorId")
                or item.get("author_id")
                or item.get("id")
                or ""
            ).strip()
            name = str(item.get("name") or "").strip()
            if author_id or name:
                authors.append({"author_id": author_id, "name": name, "raw": item})
        return authors

    @classmethod
    def _extract_snippets(cls, payload: Any) -> list[AstaSnippet]:
        snippets: list[AstaSnippet] = []
        for item in cls._collect_items(payload):
            if not isinstance(item, dict):
                continue
            paper_obj = item.get("paper") if isinstance(item.get("paper"), dict) else item
            snippet_obj = item.get("snippet") if isinstance(item.get("snippet"), dict) else item
            paper_id = str(
                paper_obj.get("paperId")
                or paper_obj.get("paper_id")
                or paper_obj.get("corpusId")
                or item.get("paperId")
                or item.get("paper_id")
                or item.get("corpusId")
                or ""
            ).strip()
            title = str(
                paper_obj.get("title")
                or item.get("title")
                or item.get("paperTitle")
                or ""
            ).strip()
            text = str(
                snippet_obj.get("text")
                or item.get("snippet")
                or item.get("text")
                or item.get("content")
                or ""
            ).strip()
            if not text:
                continue
            score_value = item.get("score")
            score = float(score_value) if isinstance(score_value, (int, float)) else None
            snippets.append(
                AstaSnippet(
                    paper_id=paper_id,
                    paper_title=title,
                    text=text,
                    score=score,
                )
            )
        return snippets

    @classmethod
    def _collect_items(cls, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return [payload]

        if cls._looks_like_paper(payload) or cls._looks_like_author(payload) or cls._looks_like_snippet(payload):
            return [payload]

        for key in ("result", "data", "papers", "results", "items", "citations", "snippets", "authors"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return cls._collect_items(value)
        return [payload]

    @staticmethod
    def _looks_like_paper(item: dict[str, Any]) -> bool:
        return bool(
            item.get("title")
            and (
                item.get("paperId")
                or item.get("paper_id")
                or item.get("id")
                or item.get("corpusId")
                or item.get("abstract")
                or item.get("journal")
                or item.get("venue")
                or item.get("authors")
            )
        )

    @staticmethod
    def _looks_like_author(item: dict[str, Any]) -> bool:
        return bool(
            item.get("name")
            and (
                item.get("authorId")
                or item.get("author_id")
                or item.get("paperCount")
                or item.get("citationCount")
                or item.get("hIndex")
            )
        )

    @staticmethod
    def _looks_like_snippet(item: dict[str, Any]) -> bool:
        snippet = item.get("snippet")
        paper = item.get("paper")
        if isinstance(snippet, dict) and isinstance(paper, dict):
            return bool(snippet.get("text") and paper.get("title"))
        return bool(item.get("snippet") or item.get("text") or item.get("content"))

    @classmethod
    def _to_paper(cls, item: Any) -> Paper | None:
        if not isinstance(item, dict):
            return None

        title = str(item.get("title") or "").strip()
        if not title:
            return None

        paper_id = str(
            item.get("paperId")
            or item.get("paper_id")
            or item.get("id")
            or item.get("corpusId")
            or ""
        ).strip()
        if not paper_id and isinstance(item.get("externalIds"), dict):
            external_ids = item["externalIds"]
            paper_id = str(
                external_ids.get("CorpusId")
                or external_ids.get("DOI")
                or external_ids.get("ArXiv")
                or ""
            ).strip()
        if not paper_id:
            paper_id = title

        authors: list[Author] = []
        for author in item.get("authors", []) or []:
            if not isinstance(author, dict):
                continue
            name = str(author.get("name") or "").strip()
            if not name:
                continue
            affiliations = author.get("affiliations") or []
            if isinstance(affiliations, list):
                affiliation = ", ".join(str(entry).strip() for entry in affiliations if str(entry).strip())
            else:
                affiliation = str(affiliations).strip()
            authors.append(Author(name=name, affiliation=affiliation))

        doi = ""
        arxiv_id = ""
        external_ids = item.get("externalIds")
        if isinstance(external_ids, dict):
            doi = str(external_ids.get("DOI") or "").strip()
            arxiv_id = str(external_ids.get("ArXiv") or "").strip()

        journal = item.get("journal")
        venue = str(item.get("venue") or "").strip()
        if not venue and isinstance(journal, dict):
            venue = str(journal.get("name") or "").strip()
        elif not venue and isinstance(journal, str):
            venue = journal.strip()

        citation_count_raw = item.get("citationCount")
        if isinstance(citation_count_raw, int):
            citation_count = citation_count_raw
        elif isinstance(item.get("citations"), list):
            citation_count = len(item["citations"])
        else:
            citation_count = 0

        year_value = item.get("year")
        year = int(year_value) if isinstance(year_value, int) else 0

        return Paper(
            paper_id=paper_id,
            title=title,
            authors=tuple(authors),
            year=year,
            abstract=str(item.get("abstract") or "").strip(),
            venue=venue,
            citation_count=citation_count,
            doi=doi,
            arxiv_id=arxiv_id,
            url=str(item.get("url") or "").strip(),
            source="asta",
        )
