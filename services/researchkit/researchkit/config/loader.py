import os

from researchkit.config.schema import ProviderConfig
from researchkit.db import get_db


def _is_provided(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


class ConfigLoader:
    @staticmethod
    async def load(project_id: str, overrides: dict | None = None) -> ProviderConfig:
        """Load config: env defaults → MongoDB per-project overrides → request overrides."""
        allowed_workspace_roots = [
            p.strip()
            for p in os.getenv("RESEARCHKIT_ALLOWED_WORKSPACE_ROOTS", "").split(":")
            if p.strip()
        ]

        # Start with environment defaults
        config_data = {
            "provider_type": os.getenv("RESEARCHKIT_PROVIDER_TYPE", "openai"),
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL"),
            "model": os.getenv("RESEARCHKIT_MODEL", "gpt-4o"),
            "workspace_path": os.getenv("RESEARCHKIT_WORKSPACE_PATH"),
            "runner_url": os.getenv("RESEARCHKIT_RUNNER_URL"),
            "bash_default_timeout_seconds": int(
                os.getenv("RESEARCHKIT_BASH_TIMEOUT_SECONDS", "60")
            ),
            "max_tool_iterations": int(os.getenv("RESEARCHKIT_MAX_TOOL_ITERATIONS", "8")),
            "tool_output_max_chars": int(os.getenv("RESEARCHKIT_TOOL_OUTPUT_MAX_CHARS", "12000")),
            "allowed_workspace_roots": allowed_workspace_roots,
        }

        # Override with per-project config from MongoDB
        db = get_db()
        project_config = await db.researchkitConfig.find_one({"project_id": project_id})
        if project_config:
            for key in (
                "provider_type",
                "api_key",
                "base_url",
                "model",
                "workspace_path",
                "runner_url",
                "bash_default_timeout_seconds",
                "max_tool_iterations",
                "tool_output_max_chars",
            ):
                if _is_provided(project_config.get(key)):
                    config_data[key] = project_config[key]

        # If provider is anthropic, use anthropic API key from env if not overridden
        if config_data["provider_type"] == "anthropic" and not config_data.get("api_key"):
            config_data["api_key"] = os.getenv("ANTHROPIC_API_KEY", "")

        # Override with request-level config
        if overrides:
            for key in (
                "provider_type",
                "api_key",
                "base_url",
                "model",
                "workspace_path",
                "runner_url",
                "bash_default_timeout_seconds",
                "max_tool_iterations",
                "tool_output_max_chars",
            ):
                if _is_provided(overrides.get(key)):
                    config_data[key] = overrides[key]

        return ProviderConfig(**config_data)

    @staticmethod
    async def save(project_id: str, config) -> None:
        db = get_db()
        await db.researchkitConfig.update_one(
            {"project_id": project_id},
            {"$set": {
                "project_id": project_id,
                "provider_type": config.provider_type,
                "api_key": config.api_key,
                "base_url": config.base_url,
                "model": config.model,
                "workspace_path": config.workspace_path,
                "runner_url": config.runner_url,
                "bash_default_timeout_seconds": config.bash_default_timeout_seconds,
                "max_tool_iterations": config.max_tool_iterations,
                "tool_output_max_chars": config.tool_output_max_chars,
            }},
            upsert=True,
        )
