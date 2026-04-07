from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from researchkit.config.schema import ProviderConfig


class ModelDiscoveryError(Exception):
    pass


def _label_from_model_id(model_id: str) -> str:
    return model_id


async def _list_openai_compatible_models(config: ProviderConfig) -> list[dict[str, str]]:
    kwargs: dict[str, str] = {"api_key": config.api_key or "missing"}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = AsyncOpenAI(**kwargs)
    paginator = client.models.list()
    models: list[dict[str, str]] = []
    async for model in paginator:
        model_id = getattr(model, "id", None)
        if not isinstance(model_id, str) or not model_id:
            continue
        models.append({"id": model_id, "label": _label_from_model_id(model_id)})
        if len(models) >= 200:
            break
    await client.close()
    return sorted(models, key=lambda item: item["id"])


async def _list_anthropic_models(config: ProviderConfig) -> list[dict[str, str]]:
    kwargs: dict[str, str] = {"api_key": config.api_key or ""}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = AsyncAnthropic(**kwargs)
    paginator = client.models.list(limit=200)
    models: list[dict[str, str]] = []
    async for model in paginator:
        model_id = getattr(model, "id", None)
        if not isinstance(model_id, str) or not model_id:
            continue
        label = getattr(model, "display_name", None)
        if not isinstance(label, str) or not label:
            label = _label_from_model_id(model_id)
        models.append({"id": model_id, "label": label})
        if len(models) >= 200:
            break
    await client.close()
    return sorted(models, key=lambda item: item["id"])


async def list_models_for_config(config: ProviderConfig) -> list[dict[str, str]]:
    if config.provider_type in {"openai", "custom"}:
        return await _list_openai_compatible_models(config)
    if config.provider_type == "anthropic":
        return await _list_anthropic_models(config)
    raise ModelDiscoveryError(f"Unknown provider type: {config.provider_type}")
