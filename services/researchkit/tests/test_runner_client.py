import httpx

from researchkit.agents.runner_client import RunnerClient


class _FakeAsyncClient:
    def __init__(self, *, base_url: str, timeout: int):
        self.base_url = base_url
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def post(self, path: str, json: dict):
        assert path == "/execute"
        assert json["project_id"] == "p1"
        request = httpx.Request("POST", f"{self.base_url}/execute")
        return httpx.Response(
            200,
            request=request,
            json={
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
                "changed_files": [
                    {
                        "path": "main.tex",
                        "before": "old",
                        "after": "new",
                        "before_exists": True,
                        "after_exists": True,
                    },
                ],
            },
        )


class _FakeAsyncClientAlt:
    def __init__(self, *, base_url: str, timeout: int):
        self.base_url = base_url
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def post(self, path: str, json: dict):
        request = httpx.Request("POST", f"{self.base_url}/execute")
        return httpx.Response(
            200,
            request=request,
            json={
                "exit_code": 1,
                "output": "x",
                "error": "y",
                "changed_files": [
                    {
                        "file_path": "/workspace/refs.bib",
                        "old_content": "@a{}",
                        "new_content": "@a{ title={T} }",
                        "before_exists": False,
                        "after_exists": True,
                    },
                ],
            },
        )


async def test_runner_client_parses_primary_shape(monkeypatch):
    monkeypatch.setattr("researchkit.agents.runner_client.httpx.AsyncClient", _FakeAsyncClient)
    client = RunnerClient("http://runner.local")

    result = await client.execute(
        project_id="p1",
        workspace_path="/workspace/p1",
        command="echo hi",
        timeout_seconds=30,
    )

    assert result.exit_code == 0
    assert result.stdout == "ok"
    assert result.stderr == ""
    assert len(result.changed_files) == 1
    assert result.changed_files[0].path == "main.tex"
    assert result.changed_files[0].before == "old"
    assert result.changed_files[0].after == "new"
    assert result.changed_files[0].before_exists is True
    assert result.changed_files[0].after_exists is True


async def test_runner_client_parses_alternative_shape(monkeypatch):
    monkeypatch.setattr("researchkit.agents.runner_client.httpx.AsyncClient", _FakeAsyncClientAlt)
    client = RunnerClient("http://runner.local")

    result = await client.execute(
        project_id="p1",
        workspace_path="/workspace/p1",
        command="echo hi",
        timeout_seconds=30,
    )

    assert result.exit_code == 1
    assert result.stdout == "x"
    assert result.stderr == "y"
    assert len(result.changed_files) == 1
    assert result.changed_files[0].path == "/workspace/refs.bib"
    assert result.changed_files[0].before == "@a{}"
    assert result.changed_files[0].after == "@a{ title={T} }"
    assert result.changed_files[0].before_exists is False
    assert result.changed_files[0].after_exists is True
