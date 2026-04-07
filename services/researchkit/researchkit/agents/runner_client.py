from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class ChangedFile:
    path: str
    before: str
    after: str
    before_exists: bool = True
    after_exists: bool = True


@dataclass
class RunnerExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    changed_files: list[ChangedFile]


class RunnerClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def execute(
        self,
        *,
        project_id: str,
        workspace_path: str,
        command: str,
        timeout_seconds: int,
        working_subdir: str | None = None,
        files: dict[str, str] | None = None,
    ) -> RunnerExecutionResult:
        payload = {
            "project_id": project_id,
            "workspace_path": workspace_path,
            "command": command,
            "timeout_seconds": timeout_seconds,
        }
        if working_subdir:
            payload["working_subdir"] = working_subdir
        if files:
            payload["files"] = files

        timeout = max(timeout_seconds + 15, 20)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            response = await client.post("/execute", json=payload)
            response.raise_for_status()
            data = response.json()

        changed_files: list[ChangedFile] = []
        for item in data.get("changed_files", []):
            path = item.get("path") or item.get("file_path") or item.get("file")
            before = (
                item.get("before")
                if item.get("before") is not None
                else item.get("original_text", item.get("old_content", ""))
            )
            after = (
                item.get("after")
                if item.get("after") is not None
                else item.get("replacement_text", item.get("new_content", ""))
            )
            before_exists = item.get("before_exists")
            after_exists = item.get("after_exists")
            if not path:
                continue
            changed_files.append(
                ChangedFile(
                    path=path,
                    before=before or "",
                    after=after or "",
                    before_exists=bool(True if before_exists is None else before_exists),
                    after_exists=bool(True if after_exists is None else after_exists),
                )
            )

        exit_code = int(data.get("exit_code", 0))
        stdout = str(data.get("stdout", data.get("output", "")) or "")
        stderr = str(data.get("stderr", data.get("error", "")) or "")

        return RunnerExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            changed_files=changed_files,
        )
