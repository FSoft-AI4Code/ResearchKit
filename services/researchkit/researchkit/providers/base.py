from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        """Stream response tokens."""
        ...

    @abstractmethod
    async def complete_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> dict:
        """Generate a response with tool calling. Returns full message with tool_calls."""
        ...
