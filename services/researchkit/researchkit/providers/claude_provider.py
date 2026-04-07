import json
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from researchkit.providers.base import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
    ):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncAnthropic(**kwargs)
        self.model = model

    def _convert_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Separate system message from conversation messages for Anthropic API."""
        system = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                conversation.append({"role": msg["role"], "content": msg["content"]})
        return system, conversation

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI tool format to Anthropic tool format."""
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", tool)
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return anthropic_tools

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> str:
        system, conversation = self._convert_messages(messages)
        kwargs = {"model": self.model, "messages": conversation, "max_tokens": 4096}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        response = await self.client.messages.create(**kwargs)
        # Extract text from content blocks
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

    async def stream(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[str]:
        system, conversation = self._convert_messages(messages)
        kwargs = {"model": self.model, "messages": conversation, "max_tokens": 4096}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        system, conversation = self._convert_messages(messages)
        response = await self.client.messages.create(
            model=self.model,
            messages=conversation,
            max_tokens=4096,
            system=system if system else "You are a helpful assistant.",
            tools=self._convert_tools(tools),
        )

        result = {"role": "assistant", "content": ""}
        tool_calls = []
        for block in response.content:
            if hasattr(block, "text"):
                result["content"] += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "function": {"name": block.name, "arguments": json.dumps(block.input)},
                })
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result
