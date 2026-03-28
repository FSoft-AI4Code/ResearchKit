"""OpenAI-compatible LLM provider.

Supports any OpenAI-API-compatible endpoint via custom base_url
(e.g. vLLM, LiteLLM proxy, Together, Groq).
"""

from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from researchkit.providers.base import (
    LLMProvider,
    Message,
    Response,
    StreamChunk,
    ToolCall,
)


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _to_api_messages(self, messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Response:
        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_api_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            api_kwargs["tools"] = tools

        resp = await self._client.chat.completions.create(**api_kwargs)
        choice = resp.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            import json

            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return Response(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
            },
            model=resp.model,
            finish_reason=choice.finish_reason or "",
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
        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_api_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            api_kwargs["tools"] = tools

        stream = await self._client.chat.completions.create(**api_kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            yield StreamChunk(
                content=delta.content or "",
                finish_reason=chunk.choices[0].finish_reason,
            )
