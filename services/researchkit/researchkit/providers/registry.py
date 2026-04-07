from researchkit.config.schema import ProviderConfig
from researchkit.providers.base import LLMProvider
from researchkit.providers.claude_provider import ClaudeProvider
from researchkit.providers.openai_provider import OpenAIProvider


def create_provider(config: ProviderConfig) -> LLMProvider:
    match config.provider_type:
        case "openai" | "custom":
            return OpenAIProvider(
                api_key=config.api_key or "",
                model=config.model,
                base_url=config.base_url,
            )
        case "anthropic":
            return ClaudeProvider(
                api_key=config.api_key or "",
                model=config.model,
                base_url=config.base_url,
            )
        case _:
            raise ValueError(f"Unknown provider type: {config.provider_type}")
