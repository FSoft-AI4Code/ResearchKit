"""Anthropic Claude LLM provider."""

from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from researchkit.providers.base import (
    LLMProvider,
    Message,
    Response,
    StreamChunk,
    ToolCall,
)


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ):
        self.model = model
        self._client = AsyncAnthropic(api_key=api_key)

    def _split_messages(
        self, messages: list[Message]
    ) -> tuple[str, list[dict[str, str]]]:
        """Anthropic requires system prompt separate from messages."""
        system = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system += m.content + "\n"
            else:
                api_messages.append({"role": m.role, "content": m.content})
        return system.strip(), api_messages

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Response:
        system, api_messages = self._split_messages(messages)

        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            api_kwargs["system"] = system
        if tools:
            api_kwargs["tools"] = self._convert_tools(tools)

        resp = await self._client.messages.create(**api_kwargs)

        content_parts = []
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        return Response(
            content="\n".join(content_parts),
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
            },
            model=resp.model,
            finish_reason=resp.stop_reason or "",
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        system, api_messages = self._split_messages(messages)

        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            api_kwargs["system"] = system
        if tools:
            api_kwargs["tools"] = self._convert_tools(tools)

        async with self._client.messages.stream(**api_kwargs) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text)
            yield StreamChunk(finish_reason="end_turn")

    @staticmethod
    def _convert_tools(openai_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-format tool definitions to Anthropic format."""
        anthropic_tools = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                fn = tool["function"]
                anthropic_tools.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                anthropic_tools.append(tool)
        return anthropic_tools
