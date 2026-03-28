from pydantic import BaseModel


class ProviderConfig(BaseModel):
    provider_type: str = "openai"  # "openai" | "anthropic" | "custom"
    api_key: str | None = None
    base_url: str | None = None
    model: str = "gpt-4o"
