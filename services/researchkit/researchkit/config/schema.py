from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    provider_type: str = "openai"  # "openai" | "anthropic" | "custom"
    api_key: str | None = None
    base_url: str | None = None
    model: str = "gpt-4o"
    workspace_path: str | None = None
    runner_url: str | None = None
    bash_default_timeout_seconds: int = 60
    max_tool_iterations: int = 8
    tool_output_max_chars: int = 12000
    asta_api_key: str | None = None
    asta_mcp_url: str | None = None
    allowed_workspace_roots: list[str] = Field(default_factory=list)
