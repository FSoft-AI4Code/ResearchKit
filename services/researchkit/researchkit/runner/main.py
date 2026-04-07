from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

RUNNER_TMP_ROOT = Path(
    os.getenv("RESEARCHKIT_RUNNER_TMP_ROOT", "/tmp/researchkit-runner")
).resolve()
RUNNER_MAX_TIMEOUT_SECONDS = int(
    os.getenv("RESEARCHKIT_RUNNER_MAX_TIMEOUT_SECONDS", "300")
)
RUNNER_MAX_OUTPUT_CHARS = int(os.getenv("RESEARCHKIT_RUNNER_MAX_OUTPUT_CHARS", "20000"))
RUNNER_MAX_TEXT_FILE_BYTES = int(
    os.getenv("RESEARCHKIT_RUNNER_MAX_TEXT_FILE_BYTES", "2000000")
)
RUNNER_MAX_CHANGED_FILES = int(os.getenv("RESEARCHKIT_RUNNER_MAX_CHANGED_FILES", "200"))


class ExecuteRequest(BaseModel):
    project_id: str
    workspace_path: str
    command: str
    timeout_seconds: int = 60
    working_subdir: str | None = None
    files: dict[str, str] | None = None


class ChangedFile(BaseModel):
    path: str
    before: str
    after: str
    before_exists: bool = True
    after_exists: bool = True


class ExecuteResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    changed_files: list[ChangedFile]


@asynccontextmanager
async def lifespan(app: FastAPI):
    RUNNER_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="ResearchKit Runner",
    description="Sandboxed command runner for ResearchKit bash tool",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "researchkit-runner"}


def _sanitize_project_id(project_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in project_id.strip())
    return safe[:80] or "project"


def _normalize_rel_path(path: str) -> Path:
    normalized = PurePosixPath(path.lstrip("/"))
    if not normalized.parts:
        raise ValueError("empty file path")
    if any(part in ("", ".", "..") for part in normalized.parts):
        raise ValueError(f"invalid file path: {path}")
    return Path(*normalized.parts)


def _write_overlay_files(workspace: Path, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        normalized = _normalize_rel_path(rel_path)
        target = workspace / normalized
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _collect_text_files(workspace: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            if size > RUNNER_MAX_TEXT_FILE_BYTES:
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(workspace).as_posix()
        snapshot[rel] = text
    return snapshot


def _diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[ChangedFile]:
    changed: list[ChangedFile] = []
    for rel_path in sorted(set(before) | set(after)):
        before_exists = rel_path in before
        after_exists = rel_path in after
        prev = before.get(rel_path, "")
        curr = after.get(rel_path, "")
        if prev == curr and before_exists == after_exists:
            continue
        changed.append(
            ChangedFile(
                path=rel_path,
                before=prev,
                after=curr,
                before_exists=before_exists,
                after_exists=after_exists,
            )
        )
        if len(changed) >= RUNNER_MAX_CHANGED_FILES:
            break
    return changed


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 16] + "\n...[truncated]"


def _resolve_cwd(workspace: Path, working_subdir: str | None) -> Path:
    if not working_subdir:
        return workspace
    normalized = _normalize_rel_path(working_subdir)
    cwd = (workspace / normalized).resolve()
    if not (cwd == workspace or str(cwd).startswith(f"{workspace}{os.sep}")):
        raise ValueError("working_subdir escapes workspace")
    if not cwd.exists() or not cwd.is_dir():
        raise ValueError("working_subdir does not exist")
    return cwd


async def _run_command(command: str, cwd: Path, timeout_seconds: int) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        executable="/bin/bash",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return 124, "", f"Command timed out after {timeout_seconds} seconds."

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return process.returncode or 0, stdout, stderr


@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest) -> ExecuteResponse:
    command = request.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    timeout_seconds = min(max(request.timeout_seconds, 1), RUNNER_MAX_TIMEOUT_SECONDS)
    project_safe = _sanitize_project_id(request.project_id)
    source_workspace = Path(request.workspace_path).resolve()

    with tempfile.TemporaryDirectory(prefix=f"rk-{project_safe}-", dir=RUNNER_TMP_ROOT) as temp_dir:
        sandbox_root = Path(temp_dir)
        workspace = sandbox_root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        # Optional baseline copy from mounted workspace path if available in runner container.
        if source_workspace.exists() and source_workspace.is_dir():
            shutil.copytree(source_workspace, workspace, dirs_exist_ok=True)

        if request.files:
            try:
                _write_overlay_files(workspace, request.files)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        before = _collect_text_files(workspace)
        try:
            cwd = _resolve_cwd(workspace, request.working_subdir)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        exit_code, stdout, stderr = await _run_command(command, cwd, timeout_seconds)
        after = _collect_text_files(workspace)
        changed_files = _diff_snapshots(before, after)

    return ExecuteResponse(
        exit_code=exit_code,
        stdout=_truncate(stdout, RUNNER_MAX_OUTPUT_CHARS),
        stderr=_truncate(stderr, RUNNER_MAX_OUTPUT_CHARS),
        changed_files=changed_files,
    )
