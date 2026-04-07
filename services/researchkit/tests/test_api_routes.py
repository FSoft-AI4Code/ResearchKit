import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

fake_db_module = types.ModuleType("researchkit.db")
fake_db_module.get_db = lambda: None

async def _fake_close_client():
    return None

fake_db_module.close_client = _fake_close_client
sys.modules.setdefault("researchkit.db", fake_db_module)

from researchkit.main import app  # noqa: E402


class _FakeAgent:
    async def handle(self, **kwargs):
        yield {
            "type": "edit",
            "data": {
                "tool": "str_replace_editor",
                "command": "view",
                "path": "paper.tex",
                "absolute_path": "/workspace/paper.tex",
                "status": "completed",
                "summary": "Viewed file `/workspace/paper.tex`.",
                "metadata": {"kind": "file"},
            },
        }
        yield {
            "type": "response",
            "data": {"response_id": "r1", "content": "done"},
        }


class _FakeConversationCollection:
    def __init__(self):
        self.last_find_query: dict | None = None
        self.last_list_query: dict | None = None
        self.last_delete_query: dict | None = None
        self.delete_queries: list[dict] = []
        self.documents = [
            {
                "project_id": "p1",
                "conversation_id": "thread-1",
                "updated_at": datetime(2026, 4, 1, 10, 15, tzinfo=timezone.utc),
                "messages": [
                    {"role": "user", "content": "hello"},
                    {
                        "role": "assistant",
                        "content": "hi",
                        "response_id": "r1",
                        "actions": [
                            {
                                "tool": "bash",
                                "status": "completed",
                                "iteration": 1,
                                "detail": "done",
                                "response_id": "r1",
                            }
                        ],
                        "patches": [
                            {
                                "file_path": "draft.tex",
                                "selection_from": 0,
                                "selection_to": 0,
                                "original_text": "",
                                "replacement_text": "hello\n",
                                "description": "Create draft",
                                "response_id": "r1",
                                "change_type": "create",
                            }
                        ],
                    },
                ],
            }
        ]

    async def find_one(self, query: dict) -> dict | None:
        self.last_find_query = dict(query)
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                return dict(document)
        return None

    def find(self, query: dict):
        self.last_list_query = dict(query)
        docs = [
            dict(document)
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        return _FakeConversationCursor(docs)

    async def delete_one(self, query: dict):
        self.last_delete_query = dict(query)
        self.delete_queries.append(dict(query))
        return None


class _FakeConversationCursor:
    def __init__(self, documents: list[dict]):
        self.documents = documents

    def sort(self, key: str, order: int):
        reverse = order < 0
        self.documents.sort(key=lambda doc: doc.get(key), reverse=reverse)
        return self

    async def to_list(self, length: int):
        return self.documents[:length]


class _FakeDB:
    def __init__(self):
        self.researchkitConversations = _FakeConversationCollection()


def test_chat_route_filters_internal_edit_events(monkeypatch):
    async def _fake_load(project_id: str, config: dict | None = None):
        return object()

    async def _fake_needs_reindex(self, project_id: str, files: dict[str, str]):
        return False

    async def _fake_get_memory(self, project_id: str):
        return None

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.load", _fake_load)
    monkeypatch.setattr("researchkit.api.routes.MemoryManager.needs_reindex", _fake_needs_reindex)
    monkeypatch.setattr("researchkit.api.routes.MemoryManager.get_memory", _fake_get_memory)
    monkeypatch.setattr("researchkit.api.routes.MainAgent", lambda config: _FakeAgent())

    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/chat",
        json={"project_id": "p1", "message": "inspect file"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: edit" not in body
    assert "event: response" in body
    assert '"content": "done"' in body


def test_get_conversation_route_returns_messages(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr("researchkit.api.routes.get_db", lambda: fake_db)

    client = TestClient(app)
    response = client.get("/api/conversation/p1?conversation_id=thread-1")

    assert response.status_code == 200
    assert response.json() == {
        "project_id": "p1",
        "conversation_id": "thread-1",
        "messages": [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": "hi",
                "response_id": "r1",
                "actions": [
                    {
                        "tool": "bash",
                        "status": "completed",
                        "iteration": 1,
                        "detail": "done",
                        "response_id": "r1",
                    }
                ],
                "patches": [
                    {
                        "file_path": "draft.tex",
                        "selection_from": 0,
                        "selection_to": 0,
                        "original_text": "",
                        "replacement_text": "hello\n",
                        "description": "Create draft",
                        "change_type": "create",
                        "response_id": "r1",
                    }
                ],
            },
        ],
    }
    assert fake_db.researchkitConversations.last_find_query == {
        "project_id": "p1",
        "conversation_id": "thread-1",
    }


def test_list_conversations_route_returns_sorted_summaries(monkeypatch):
    fake_db = _FakeDB()
    fake_db.researchkitConversations.documents = [
        {
            "project_id": "p1",
            "conversation_id": "thread-older",
            "updated_at": datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
            "messages": [
                {"role": "user", "content": "older hello"},
                {"role": "assistant", "content": "older reply"},
            ],
        },
        {
            "project_id": "p1",
            "updated_at": datetime(2026, 4, 1, 12, 30, tzinfo=timezone.utc),
            "messages": [
                {"role": "user", "content": "legacy hello"},
                {"role": "assistant", "content": "legacy reply"},
            ],
        },
        {
            "project_id": "p1",
            "conversation_id": "thread-new",
            "updated_at": datetime(2026, 4, 2, 8, 45, tzinfo=timezone.utc),
            "messages": [
                {"role": "user", "content": "new hello"},
                {"role": "assistant", "content": "new reply"},
            ],
        },
    ]
    monkeypatch.setattr("researchkit.api.routes.get_db", lambda: fake_db)

    client = TestClient(app)
    response = client.get("/api/conversation/p1/list")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "p1"
    assert [item["conversation_id"] for item in body["conversations"]] == [
        "thread-new",
        "default",
        "thread-older",
    ]
    assert [item["message_count"] for item in body["conversations"]] == [2, 2, 2]
    assert body["conversations"][0]["last_message_preview"] == "new reply"
    assert fake_db.researchkitConversations.last_list_query == {"project_id": "p1"}


def test_clear_conversation_route_scopes_by_conversation_id(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr("researchkit.api.routes.get_db", lambda: fake_db)

    client = TestClient(app)
    response = client.delete("/api/conversation/p1?conversation_id=thread-1")

    assert response.status_code == 200
    assert response.json() == {
        "status": "cleared",
        "project_id": "p1",
        "conversation_id": "thread-1",
    }
    assert fake_db.researchkitConversations.last_delete_query == {
        "project_id": "p1",
        "conversation_id": "thread-1",
    }


def test_clear_default_conversation_also_clears_legacy_document(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr("researchkit.api.routes.get_db", lambda: fake_db)

    client = TestClient(app)
    response = client.delete("/api/conversation/p1")

    assert response.status_code == 200
    assert fake_db.researchkitConversations.delete_queries == [
        {"project_id": "p1", "conversation_id": "default"},
        {"project_id": "p1"},
    ]


def test_list_models_route_returns_models(monkeypatch):
    async def _fake_load(project_id: str, overrides: dict | None = None):
        assert project_id == "p1"
        assert overrides is None
        return SimpleNamespace(
            provider_type="openai",
            model="my-model",
            api_key="sk-stored",
            base_url=None,
        )

    async def _fake_list_models(config):
        assert config.provider_type == "custom"
        assert config.api_key == "sk-custom"
        assert config.base_url == "http://localhost:4000/v1"
        return [
            {"id": "my-model", "label": "my-model"},
            {"id": "other-model", "label": "other-model"},
        ]

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.load", _fake_load)
    monkeypatch.setattr("researchkit.api.routes.list_models_for_config", _fake_list_models)

    client = TestClient(app)
    response = client.post(
        "/api/models/p1",
        json={
            "provider_type": "custom",
            "base_url": "http://localhost:4000/v1",
            "api_key": "sk-custom",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider_type": "custom",
        "models": [
            {"id": "my-model", "label": "my-model"},
            {"id": "other-model", "label": "other-model"},
        ],
        "selected_model": "my-model",
    }


def test_list_models_route_surfaces_discovery_errors(monkeypatch):
    async def _fake_load(project_id: str, overrides: dict | None = None):
        return SimpleNamespace(
            provider_type="openai",
            model="gpt-4o",
            api_key="sk-fail",
            base_url=None,
        )

    async def _fake_list_models(config):
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.load", _fake_load)
    monkeypatch.setattr("researchkit.api.routes.list_models_for_config", _fake_list_models)

    client = TestClient(app)
    response = client.post("/api/models/p1", json={})

    assert response.status_code == 502
    assert response.json()["detail"] == "Failed to fetch models from provider."


def test_test_config_route_returns_success(monkeypatch):
    async def _fake_load(project_id: str, overrides: dict | None = None):
        assert project_id == "p1"
        assert overrides is None
        return SimpleNamespace(
            provider_type="openai",
            model="gpt-4o-mini",
            api_key="sk-stored",
            base_url=None,
        )

    class _FakeProvider:
        async def complete(self, messages):
            assert len(messages) == 2
            return "OK"

    captured = {}

    def _fake_create_provider(config):
        captured["provider_type"] = config.provider_type
        captured["model"] = config.model
        captured["api_key"] = config.api_key
        captured["base_url"] = config.base_url
        return _FakeProvider()

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.load", _fake_load)
    monkeypatch.setattr("researchkit.api.routes.create_provider", _fake_create_provider)

    client = TestClient(app)
    response = client.post(
        "/api/config/p1/test",
        json={
            "provider_type": "custom",
            "api_key": "sk-custom",
            "base_url": "http://localhost:4000/v1",
            "model": "my-model",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["provider_type"] == "custom"
    assert body["model"] == "my-model"
    assert body["message"] == "Configuration test succeeded."
    assert captured == {
        "provider_type": "custom",
        "model": "my-model",
        "api_key": "sk-custom",
        "base_url": "http://localhost:4000/v1",
    }


def test_test_config_route_requires_model(monkeypatch):
    async def _fake_load(project_id: str, overrides: dict | None = None):
        return SimpleNamespace(
            provider_type="openai",
            model="gpt-4o",
            api_key="sk-stored",
            base_url=None,
        )

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.load", _fake_load)

    client = TestClient(app)
    response = client.post("/api/config/p1/test", json={"model": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Model is required."


def test_get_config_route_returns_asta_key_presence(monkeypatch):
    async def _fake_load(project_id: str):
        assert project_id == "p1"
        return SimpleNamespace(
            provider_type="openai",
            base_url=None,
            model="gpt-4o",
            workspace_path="/workspace",
            runner_url="http://runner:3030",
            bash_default_timeout_seconds=60,
            max_tool_iterations=8,
            tool_output_max_chars=12000,
            api_key="sk-stored",
            asta_api_key="asta-stored",
        )

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.load", _fake_load)

    client = TestClient(app)
    response = client.get("/api/config/p1")

    assert response.status_code == 200
    assert response.json() == {
        "provider_type": "openai",
        "base_url": None,
        "model": "gpt-4o",
        "workspace_path": "/workspace",
        "runner_url": "http://runner:3030",
        "bash_default_timeout_seconds": 60,
        "max_tool_iterations": 8,
        "tool_output_max_chars": 12000,
        "has_api_key": True,
        "has_asta_api_key": True,
    }


def test_update_config_route_accepts_asta_key_fields(monkeypatch):
    captured = {}

    async def _fake_save(project_id: str, request):
        captured["project_id"] = project_id
        captured["asta_api_key"] = request.asta_api_key
        captured["clear_asta_api_key"] = request.clear_asta_api_key

    monkeypatch.setattr("researchkit.api.routes.ConfigLoader.save", _fake_save)

    client = TestClient(app)
    response = client.post(
        "/api/config/p1",
        json={
            "provider_type": "openai",
            "model": "gpt-4o",
            "asta_api_key": "asta-live",
            "clear_asta_api_key": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "updated", "project_id": "p1"}
    assert captured == {
        "project_id": "p1",
        "asta_api_key": "asta-live",
        "clear_asta_api_key": False,
    }
