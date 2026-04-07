from researchkit.config.schema import ProviderConfig
from researchkit.providers.registry import create_provider


def test_create_provider_passes_base_url_to_anthropic_provider(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeAsyncAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "researchkit.providers.claude_provider.AsyncAnthropic",
        _FakeAsyncAnthropic,
    )

    create_provider(
        ProviderConfig(
            provider_type="anthropic",
            api_key="sk-ant-test",
            base_url="http://pro-x.io.vn",
            model="claude-sonnet-4-6",
        )
    )

    assert captured["api_key"] == "sk-ant-test"
    assert captured["base_url"] == "http://pro-x.io.vn"
