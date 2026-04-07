import sys
import types
from types import SimpleNamespace

fake_db_module = types.ModuleType("researchkit.db")
fake_db_module.get_db = lambda: None


async def _fake_close_client():
    return None


fake_db_module.close_client = _fake_close_client
sys.modules.setdefault("researchkit.db", fake_db_module)

from researchkit.config.loader import ConfigLoader  # noqa: E402
from researchkit.config.secret_crypto import decrypt_secret, encrypt_secret  # noqa: E402


def _make_config(**overrides):
    config = {
        "provider_type": "openai",
        "api_key": None,
        "clear_api_key": False,
        "base_url": None,
        "model": "gpt-4o",
        "asta_api_key": None,
        "clear_asta_api_key": False,
        "workspace_path": None,
        "runner_url": None,
        "bash_default_timeout_seconds": 60,
        "max_tool_iterations": 8,
        "tool_output_max_chars": 12000,
    }
    config.update(overrides)
    return SimpleNamespace(**config)


class _FakeCollection:
    def __init__(self, document):
        self.document = document
        self.last_update_query: dict | None = None
        self.last_update_doc: dict | None = None
        self.last_upsert: bool = False

    async def find_one(self, query):
        return dict(self.document) if isinstance(self.document, dict) else self.document

    async def update_one(self, query, update, upsert=False):
        self.last_update_query = dict(query)
        self.last_update_doc = dict(update)
        self.last_upsert = bool(upsert)
        if self.document is None:
            self.document = {}

        set_doc = update.get("$set", {})
        unset_doc = update.get("$unset", {})

        for key, value in set_doc.items():
            self.document[key] = value
        for key in unset_doc:
            self.document.pop(key, None)


class _FakeDb:
    def __init__(self, document):
        self.researchkitConfig = _FakeCollection(document)


async def test_load_keeps_valid_env_workspace_when_request_override_is_invalid(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RESEARCHKIT_WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "researchkit.config.loader.get_db",
        lambda: _FakeDb(None),
    )

    config = await ConfigLoader.load(
        "p1",
        overrides={"workspace_path": "/projects/default"},
    )

    assert config.workspace_path == str(tmp_path)


async def test_load_allows_valid_request_workspace_to_override_env(monkeypatch, tmp_path):
    env_workspace = tmp_path / "env"
    request_workspace = tmp_path / "request"
    env_workspace.mkdir()
    request_workspace.mkdir()

    monkeypatch.setenv("RESEARCHKIT_WORKSPACE_PATH", str(env_workspace))
    monkeypatch.setattr(
        "researchkit.config.loader.get_db",
        lambda: _FakeDb(None),
    )

    config = await ConfigLoader.load(
        "p1",
        overrides={"workspace_path": str(request_workspace)},
    )

    assert config.workspace_path == str(request_workspace)


async def test_load_keeps_valid_env_workspace_when_db_workspace_is_invalid(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("RESEARCHKIT_WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "researchkit.config.loader.get_db",
        lambda: _FakeDb({"workspace_path": "/projects/default"}),
    )

    config = await ConfigLoader.load("p1")

    assert config.workspace_path == str(tmp_path)


async def test_load_uses_env_asta_api_key_as_default(monkeypatch):
    monkeypatch.setenv("RESEARCHKIT_ASTA_API_KEY", "asta-default-env-key")
    monkeypatch.setattr(
        "researchkit.config.loader.get_db",
        lambda: _FakeDb(None),
    )

    config = await ConfigLoader.load("p1")

    assert config.asta_api_key == "asta-default-env-key"


async def test_save_encrypts_api_key(monkeypatch):
    encryption_key = "ab" * 32
    monkeypatch.setenv("RESEARCHKIT_CONFIG_ENCRYPTION_KEY", encryption_key)

    fake_db = _FakeDb(None)
    monkeypatch.setattr("researchkit.config.loader.get_db", lambda: fake_db)

    await ConfigLoader.save("p1", _make_config(api_key="sk-live-test"))

    stored = fake_db.researchkitConfig.document
    assert stored is not None
    assert "api_key_encrypted" in stored
    assert "api_key" not in stored
    assert decrypt_secret(stored["api_key_encrypted"]) == "sk-live-test"


async def test_load_prefers_encrypted_api_key_over_legacy_plaintext(monkeypatch):
    monkeypatch.setenv("RESEARCHKIT_CONFIG_ENCRYPTION_KEY", "cd" * 32)
    fake_db = _FakeDb(
        {
            "provider_type": "openai",
            "api_key": "legacy-plain",
            "api_key_encrypted": encrypt_secret("encrypted-live"),
            "model": "gpt-4o",
        }
    )
    monkeypatch.setattr("researchkit.config.loader.get_db", lambda: fake_db)

    config = await ConfigLoader.load("p1")

    assert config.api_key == "encrypted-live"


async def test_save_migrates_legacy_plaintext_key(monkeypatch):
    monkeypatch.setenv("RESEARCHKIT_CONFIG_ENCRYPTION_KEY", "ef" * 32)
    existing_doc = {
        "project_id": "p1",
        "provider_type": "openai",
        "api_key": "legacy-plain",
        "model": "gpt-4o",
    }
    fake_db = _FakeDb(existing_doc)
    monkeypatch.setattr("researchkit.config.loader.get_db", lambda: fake_db)

    await ConfigLoader.save("p1", _make_config(model="gpt-4.1"))

    stored = fake_db.researchkitConfig.document
    assert stored is not None
    assert "api_key" not in stored
    assert decrypt_secret(stored["api_key_encrypted"]) == "legacy-plain"
    assert stored["model"] == "gpt-4.1"


async def test_save_clears_api_key_when_requested(monkeypatch):
    monkeypatch.setenv("RESEARCHKIT_CONFIG_ENCRYPTION_KEY", "01" * 32)
    fake_db = _FakeDb(
        {
            "project_id": "p1",
            "provider_type": "openai",
            "api_key_encrypted": encrypt_secret("will-be-cleared"),
        }
    )
    monkeypatch.setattr("researchkit.config.loader.get_db", lambda: fake_db)

    await ConfigLoader.save("p1", _make_config(clear_api_key=True))

    stored = fake_db.researchkitConfig.document
    assert stored is not None
    assert "api_key_encrypted" not in stored


async def test_save_encrypts_asta_api_key(monkeypatch):
    monkeypatch.setenv("RESEARCHKIT_CONFIG_ENCRYPTION_KEY", "02" * 32)
    fake_db = _FakeDb(None)
    monkeypatch.setattr("researchkit.config.loader.get_db", lambda: fake_db)

    await ConfigLoader.save(
        "p1",
        _make_config(
            asta_api_key="asta-live-key",
        ),
    )

    stored = fake_db.researchkitConfig.document
    assert stored is not None
    assert decrypt_secret(stored["asta_api_key_encrypted"]) == "asta-live-key"


async def test_load_prefers_encrypted_asta_api_key(monkeypatch):
    monkeypatch.setenv("RESEARCHKIT_CONFIG_ENCRYPTION_KEY", "03" * 32)
    fake_db = _FakeDb(
        {
            "provider_type": "openai",
            "asta_api_key": "legacy-asta",
            "asta_api_key_encrypted": encrypt_secret("encrypted-asta"),
            "model": "gpt-4o",
        }
    )
    monkeypatch.setattr("researchkit.config.loader.get_db", lambda: fake_db)

    config = await ConfigLoader.load("p1")

    assert config.asta_api_key == "encrypted-asta"
