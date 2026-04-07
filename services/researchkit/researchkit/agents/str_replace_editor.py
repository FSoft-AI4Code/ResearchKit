from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EditorOperationResult:
    command: str
    path: str
    status: str
    summary: str
    output: str
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkspaceStrReplaceEditor:
    _WORKSPACE_ALIASES = (
        "/workspace",
        "/root/project",
        "/home/oai/project",
    )

    def __init__(
        self,
        *,
        workspace_path: str,
        history: dict[str, list[str | None]] | None = None,
        max_response_chars: int = 16000,
    ):
        self.workspace_path = os.path.realpath(workspace_path)
        self.history = history if history is not None else {}
        self.max_response_chars = max(max_response_chars, 200)

    def execute(
        self,
        *,
        command: str,
        path: str,
        file_text: str | None = None,
        view_range: list[int] | None = None,
        old_str: str | None = None,
        new_str: str | None = None,
        insert_line: int | None = None,
    ) -> EditorOperationResult:
        resolved_path = self._validate_path(command, path)

        if command == "view":
            return self._view(resolved_path, view_range=view_range)
        if command == "create":
            if file_text is None:
                raise ValueError("Parameter `file_text` is required for command `create`.")
            return self._create(resolved_path, file_text)
        if command == "str_replace":
            if old_str is None:
                raise ValueError("Parameter `old_str` is required for command `str_replace`.")
            return self._str_replace(resolved_path, old_str=old_str, new_str=new_str or "")
        if command == "insert":
            if insert_line is None:
                raise ValueError("Parameter `insert_line` is required for command `insert`.")
            if new_str is None:
                raise ValueError("Parameter `new_str` is required for command `insert`.")
            return self._insert(resolved_path, insert_line=insert_line, new_str=new_str)
        if command == "undo_edit":
            return self._undo_edit(resolved_path)
        raise ValueError(
            "Unsupported command for `str_replace_editor`. "
            'Allowed commands are: "view", "create", "str_replace", "insert", "undo_edit".'
        )

    def _validate_path(self, command: str, path: str) -> Path:
        candidate_path = self._resolve_candidate_path(path)

        real_path = os.path.realpath(str(candidate_path))
        if not (
            real_path == self.workspace_path
            or real_path.startswith(f"{self.workspace_path}{os.sep}")
        ):
            raise ValueError("The requested path is outside the configured workspace.")

        resolved_path = Path(real_path)
        if command == "create":
            if resolved_path.exists():
                raise ValueError(f"File already exists at `{resolved_path}`.")
            if not resolved_path.parent.exists():
                raise ValueError(
                    f"Parent directory does not exist for `{resolved_path}`. Create it first."
                )
            return resolved_path

        if not resolved_path.exists():
            raise ValueError(f"The path `{resolved_path}` does not exist.")
        return resolved_path

    def _resolve_candidate_path(self, path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            return Path(self.workspace_path) / candidate

        candidate_text = str(candidate)
        for alias in self._WORKSPACE_ALIASES:
            if candidate_text == alias:
                return Path(self.workspace_path)
            if candidate_text.startswith(f"{alias}/"):
                relative_suffix = candidate.relative_to(alias)
                return Path(self.workspace_path) / relative_suffix

        return candidate

    def _view(self, path: Path, *, view_range: list[int] | None) -> EditorOperationResult:
        if path.is_dir():
            output = self._format_directory(path)
            summary = f"Viewed directory `{path}`."
            metadata: dict[str, Any] = {"kind": "directory"}
            if view_range is not None:
                metadata["ignored_view_range"] = view_range
            return EditorOperationResult(
                command="view",
                path=str(path),
                status="completed",
                summary=summary,
                output=output,
                metadata=metadata,
            )

        file_content = self._read_text(path)
        start_line = 1
        if view_range:
            if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
                raise ValueError("`view_range` must be a list of two integers.")
            start_line, end_line = view_range
            lines = file_content.split("\n")
            if start_line < 1 or start_line > len(lines):
                raise ValueError(
                    f"`view_range` start must be within the file line range 1..{len(lines)}."
                )
            if end_line != -1 and end_line < start_line:
                raise ValueError("`view_range` end must be `-1` or >= the start line.")
            if end_line == -1:
                end_line = len(lines)
            if end_line > len(lines):
                raise ValueError(
                    f"`view_range` end must be within the file line range 1..{len(lines)}."
                )
            file_content = "\n".join(lines[start_line - 1 : end_line])

        output = self._format_numbered_output(file_content, str(path), start_line=start_line)
        summary = f"Viewed file `{path}`."
        metadata: dict[str, Any] = {"kind": "file"}
        if view_range:
            metadata["view_range"] = view_range
        return EditorOperationResult(
            command="view",
            path=str(path),
            status="completed",
            summary=summary,
            output=output,
            metadata=metadata,
        )

    def _create(self, path: Path, file_text: str) -> EditorOperationResult:
        self.history.setdefault(str(path), []).append(None)
        path.write_text(file_text, encoding="utf-8")
        output = self._format_numbered_output(file_text, str(path))
        return EditorOperationResult(
            command="create",
            path=str(path),
            status="completed",
            summary=f"Created `{path}`.",
            output=f"Created `{path}`.\n\n{output}",
            metadata={"created": True, "file_text_length": len(file_text)},
        )

    def _str_replace(self, path: Path, *, old_str: str, new_str: str) -> EditorOperationResult:
        original_text = self._read_text(path)
        occurrences = original_text.count(old_str)
        if occurrences == 0:
            hint = self._old_str_mismatch_hint(original_text=original_text, old_str=old_str)
            message = f"No replacement was performed because `old_str` was not found in `{path}`."
            if hint:
                message += f" Hint: {hint}"
            raise ValueError(
                message
            )
        if occurrences > 1:
            raise ValueError(
                "No replacement was performed because `old_str` appears multiple "
                f"times in `{path}`."
            )
        if old_str == new_str:
            raise ValueError(
                "No replacement was performed because `old_str` equals `new_str`."
            )

        updated_text = original_text.replace(old_str, new_str, 1)
        self.history.setdefault(str(path), []).append(original_text)
        path.write_text(updated_text, encoding="utf-8")

        snippet, start_line = self._snippet_for_replacement(
            original_text=original_text,
            updated_text=updated_text,
            replaced_text=new_str,
            needle=old_str,
        )
        output = self._format_numbered_output(snippet, f"snippet of {path}", start_line=start_line)
        return EditorOperationResult(
            command="str_replace",
            path=str(path),
            status="completed",
            summary=f"Edited `{path}` with `str_replace`.",
            output=f"Updated `{path}`.\n\n{output}",
            metadata={"old_str_length": len(old_str), "new_str_length": len(new_str)},
        )

    def _insert(self, path: Path, *, insert_line: int, new_str: str) -> EditorOperationResult:
        original_text = self._read_text(path)
        lines = original_text.split("\n")
        if insert_line < 0 or insert_line > len(lines):
            raise ValueError(
                f"`insert_line` must be within the file line range 0..{len(lines)}."
            )

        new_lines = new_str.split("\n")
        updated_lines = lines[:insert_line] + new_lines + lines[insert_line:]
        updated_text = "\n".join(updated_lines)

        self.history.setdefault(str(path), []).append(original_text)
        path.write_text(updated_text, encoding="utf-8")

        snippet_start = max(1, insert_line - 3)
        snippet_end = min(len(updated_lines), insert_line + len(new_lines) + 3)
        snippet = "\n".join(updated_lines[snippet_start - 1 : snippet_end])
        output = self._format_numbered_output(
            snippet,
            f"snippet of {path}",
            start_line=snippet_start,
        )
        return EditorOperationResult(
            command="insert",
            path=str(path),
            status="completed",
            summary=f"Inserted text into `{path}`.",
            output=f"Updated `{path}`.\n\n{output}",
            metadata={"insert_line": insert_line, "inserted_line_count": len(new_lines)},
        )

    def _undo_edit(self, path: Path) -> EditorOperationResult:
        history = self.history.get(str(path))
        if not history:
            raise ValueError(f"No edit history is available for `{path}`.")

        previous_text = history.pop()
        if previous_text is None:
            if path.exists():
                path.unlink()
            output = f"Deleted `{path}` while undoing the last create operation."
            metadata = {"removed_file": True}
        else:
            path.write_text(previous_text, encoding="utf-8")
            output = self._format_numbered_output(previous_text, str(path))
            metadata = {"restored": True}

        return EditorOperationResult(
            command="undo_edit",
            path=str(path),
            status="completed",
            summary=f"Undid the last edit for `{path}`.",
            output=output,
            metadata=metadata,
        )

    def _read_text(self, path: Path) -> str:
        encodings: list[tuple[str | None, str | None]] = [
            (None, None),
            ("utf-8", None),
            ("latin-1", None),
            ("utf-8", "replace"),
        ]
        last_error: UnicodeDecodeError | None = None
        for encoding, errors in encodings:
            try:
                return path.read_text(encoding=encoding, errors=errors)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError(f"Unable to read `{path}` due to encoding errors: {last_error}")

    def _format_directory(self, path: Path) -> str:
        entries: list[str] = []
        base_depth = len(path.parts)
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            visible_files = sorted(f for f in files if not f.startswith("."))
            depth = len(Path(root).parts) - base_depth
            if depth > 1:
                dirs[:] = []
                continue
            rel_root = Path(root).relative_to(path)
            if str(rel_root) != ".":
                entries.append(f"{rel_root}/")
            for filename in visible_files:
                item = Path(root, filename).relative_to(path)
                entries.append(str(item))
        body = "\n".join(entries) if entries else "(empty)"
        return self._truncate(
            f"Files and directories up to 2 levels deep in `{path}`:\n{body}"
        )

    def _format_numbered_output(
        self,
        file_content: str,
        file_descriptor: str,
        *,
        start_line: int = 1,
    ) -> str:
        numbered = "\n".join(
            f"{line_no:6}\t{line}"
            for line_no, line in enumerate(file_content.split("\n"), start=start_line)
        )
        return self._truncate(
            f"Here's the result of running `cat -n` on {file_descriptor}:\n{numbered}\n"
        )

    def _snippet_for_replacement(
        self,
        *,
        original_text: str,
        updated_text: str,
        replaced_text: str,
        needle: str,
    ) -> tuple[str, int]:
        replacement_line = original_text.split(needle, 1)[0].count("\n") + 1
        updated_lines = updated_text.split("\n")
        start_line = max(1, replacement_line - 3)
        end_line = min(
            len(updated_lines),
            replacement_line + max(replaced_text.count("\n"), 0) + 3,
        )
        snippet = "\n".join(updated_lines[start_line - 1 : end_line])
        return snippet, start_line

    @staticmethod
    def _old_str_mismatch_hint(*, original_text: str, old_str: str) -> str | None:
        variants = [
            (
                "The match exists if you remove leading newline characters from `old_str`.",
                old_str.lstrip("\r\n"),
            ),
            (
                "The match exists if you remove trailing newline characters from `old_str`.",
                old_str.rstrip("\r\n"),
            ),
            (
                "The match exists if you remove leading and trailing newline characters from `old_str`.",
                old_str.strip("\r\n"),
            ),
            (
                "The match exists if you normalize CRLF line endings in `old_str` to LF.",
                old_str.replace("\r\n", "\n"),
            ),
        ]
        checked: set[str] = set()
        for hint, candidate in variants:
            if candidate == old_str or not candidate or candidate in checked:
                continue
            checked.add(candidate)
            if original_text.count(candidate) == 1:
                return hint
        return None

    def _truncate(self, value: str) -> str:
        if len(value) <= self.max_response_chars:
            return value
        return value[: self.max_response_chars - 16] + "\n...[truncated]"
