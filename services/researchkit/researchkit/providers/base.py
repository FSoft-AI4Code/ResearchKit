"""Base LLM provider abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Response:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""


@dataclass
class StreamChunk:
    content: str = ""
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Each provider wraps a specific SDK (OpenAI, Anthropic, etc.) and exposes
    a uniform interface for completion and streaming.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Response:
        """Single-turn completion."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming completion yielding chunks."""
        ...
        # Make this a valid async generator for the ABC
        if False:
            yield StreamChunk()  # pragma: no cover
