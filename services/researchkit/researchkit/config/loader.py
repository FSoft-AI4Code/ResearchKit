import os

from researchkit.config.schema import ProviderConfig
from researchkit.config.secret_crypto import decrypt_secret, encrypt_secret
from researchkit.db import get_db


def _is_provided(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_valid_workspace_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if not os.path.isabs(value):
        return False
    return os.path.isdir(os.path.realpath(value))


def _merge_workspace_path(current: str | None, candidate: object) -> str | None:
    if not _is_provided(candidate):
        return current

    candidate_path = str(candidate)
    if _is_valid_workspace_path(candidate_path):
        return candidate_path

    if _is_valid_workspace_path(current):
        return current

    return candidate_path


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
            "asta_api_key": os.getenv("RESEARCHKIT_ASTA_API_KEY", ""),
            "asta_mcp_url": os.getenv(
                "RESEARCHKIT_ASTA_MCP_URL",
                "https://asta-tools.allen.ai/mcp/v1",
            ),
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
            api_key_encrypted = project_config.get("api_key_encrypted")
            api_key_plaintext = project_config.get("api_key")
            asta_api_key_encrypted = project_config.get("asta_api_key_encrypted")
            asta_api_key_plaintext = project_config.get("asta_api_key")
            for key in (
                "provider_type",
                "base_url",
                "model",
                "workspace_path",
                "runner_url",
                "bash_default_timeout_seconds",
                "max_tool_iterations",
                "tool_output_max_chars",
            ):
                if _is_provided(project_config.get(key)):
                    if key == "workspace_path":
                        config_data[key] = _merge_workspace_path(
                            config_data.get(key),
                            project_config[key],
                        )
                    else:
                        config_data[key] = project_config[key]

            if _is_provided(api_key_encrypted):
                config_data["api_key"] = decrypt_secret(str(api_key_encrypted))
            elif _is_provided(api_key_plaintext):
                # Backward compatibility for legacy plaintext storage.
                config_data["api_key"] = str(api_key_plaintext)

            if _is_provided(asta_api_key_encrypted):
                config_data["asta_api_key"] = decrypt_secret(str(asta_api_key_encrypted))
            elif _is_provided(asta_api_key_plaintext):
                config_data["asta_api_key"] = str(asta_api_key_plaintext)

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
                "asta_api_key",
            ):
                if _is_provided(overrides.get(key)):
                    if key == "workspace_path":
                        config_data[key] = _merge_workspace_path(
                            config_data.get(key),
                            overrides[key],
                        )
                    else:
                        config_data[key] = overrides[key]

        return ProviderConfig(**config_data)

    @staticmethod
    async def save(project_id: str, config) -> None:
        db = get_db()
        existing = await db.researchkitConfig.find_one({"project_id": project_id}) or {}

        clear_api_key = bool(getattr(config, "clear_api_key", False))
        clear_asta_api_key = bool(getattr(config, "clear_asta_api_key", False))
        provided_api_key = (
            isinstance(getattr(config, "api_key", None), str)
            and bool(config.api_key.strip())
        )
        provided_asta_api_key = (
            isinstance(getattr(config, "asta_api_key", None), str)
            and bool(config.asta_api_key.strip())
        )

        set_doc = {
            "project_id": project_id,
            "provider_type": config.provider_type,
            "base_url": config.base_url,
            "model": config.model,
            "workspace_path": config.workspace_path,
            "runner_url": config.runner_url,
            "bash_default_timeout_seconds": config.bash_default_timeout_seconds,
            "max_tool_iterations": config.max_tool_iterations,
            "tool_output_max_chars": config.tool_output_max_chars,
        }
        unset_doc: dict[str, str] = {}

        if clear_api_key:
            unset_doc["api_key_encrypted"] = ""
            unset_doc["api_key"] = ""
        elif provided_api_key:
            set_doc["api_key_encrypted"] = encrypt_secret(config.api_key.strip())
            unset_doc["api_key"] = ""
        elif _is_provided(existing.get("api_key")) and not _is_provided(
            existing.get("api_key_encrypted")
        ):
            # Migrate legacy plaintext secret on next save.
            set_doc["api_key_encrypted"] = encrypt_secret(str(existing["api_key"]).strip())
            unset_doc["api_key"] = ""

        if clear_asta_api_key:
            unset_doc["asta_api_key_encrypted"] = ""
            unset_doc["asta_api_key"] = ""
        elif provided_asta_api_key:
            set_doc["asta_api_key_encrypted"] = encrypt_secret(config.asta_api_key.strip())
            unset_doc["asta_api_key"] = ""
        elif _is_provided(existing.get("asta_api_key")) and not _is_provided(
            existing.get("asta_api_key_encrypted")
        ):
            set_doc["asta_api_key_encrypted"] = encrypt_secret(
                str(existing["asta_api_key"]).strip()
            )
            unset_doc["asta_api_key"] = ""

        update_doc: dict[str, dict] = {"$set": set_doc}
        if unset_doc:
            update_doc["$unset"] = unset_doc

        await db.researchkitConfig.update_one(
            {"project_id": project_id},
            update_doc,
            upsert=True,
        )
