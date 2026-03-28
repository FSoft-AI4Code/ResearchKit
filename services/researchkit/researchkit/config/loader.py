import os

from researchkit.config.schema import ProviderConfig
from researchkit.db import get_db


class ConfigLoader:
    @staticmethod
    async def load(project_id: str, overrides: dict | None = None) -> ProviderConfig:
        """Load config: env defaults → MongoDB per-project overrides → request overrides."""
        # Start with environment defaults
        config_data = {
            "provider_type": os.getenv("RESEARCHKIT_PROVIDER_TYPE", "openai"),
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "base_url": os.getenv("OPENAI_BASE_URL"),
            "model": os.getenv("RESEARCHKIT_MODEL", "gpt-4o"),
        }

        # Override with per-project config from MongoDB
        db = get_db()
        project_config = await db.researchkitConfig.find_one({"project_id": project_id})
        if project_config:
            for key in ("provider_type", "api_key", "base_url", "model"):
                if project_config.get(key):
                    config_data[key] = project_config[key]

        # If provider is anthropic, use anthropic API key from env if not overridden
        if config_data["provider_type"] == "anthropic" and not config_data.get("api_key"):
            config_data["api_key"] = os.getenv("ANTHROPIC_API_KEY", "")

        # Override with request-level config
        if overrides:
            for key in ("provider_type", "api_key", "base_url", "model"):
                if overrides.get(key):
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
            }},
            upsert=True,
        )
