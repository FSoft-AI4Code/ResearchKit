"""Provider registry -- factory for instantiating LLM providers from config strings."""

import os

from researchkit.providers.base import LLMProvider
from researchkit.providers.claude_provider import ClaudeProvider
from researchkit.providers.openai_provider import OpenAIProvider

# Maps model name prefixes to provider classes.
# The registry checks prefixes in order, so more specific prefixes should come first.
_PREFIX_MAP: list[tuple[str, type[LLMProvider]]] = [
    ("claude-", ClaudeProvider),
    ("gpt-", OpenAIProvider),
    ("o1", OpenAIProvider),
    ("o3", OpenAIProvider),
    ("o4", OpenAIProvider),
]


def create_provider(
    model: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider instance from a model name string.

    Model names are matched by prefix to determine the provider:
      - "claude-*"   -> ClaudeProvider
      - "gpt-*"      -> OpenAIProvider
      - "o1*"/"o3*"  -> OpenAIProvider

    If base_url is provided, always uses OpenAIProvider (for custom endpoints).
    """
    if base_url:
        return OpenAIProvider(
            model=model,
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    for prefix, provider_cls in _PREFIX_MAP:
        if model.startswith(prefix):
            if provider_cls is ClaudeProvider:
                return ClaudeProvider(
                    model=model,
                    api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
                )
            else:
                return OpenAIProvider(
                    model=model,
                    api_key=api_key or os.environ.get("OPENAI_API_KEY"),
                    base_url=os.environ.get("OPENAI_BASE_URL"),
                )

    # Default: treat as OpenAI-compatible (covers local models, proxies, etc.)
    return OpenAIProvider(
        model=model,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
