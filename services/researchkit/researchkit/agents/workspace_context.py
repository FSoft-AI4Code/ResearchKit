import os
from collections import deque
from pathlib import Path


def build_workspace_context_lines(
    workspace_path: str | None,
    *,
    active_file: str | None = None,
    max_top_level_entries: int = 8,
    max_tex_files: int = 8,
    max_depth: int = 3,
) -> list[str]:
    if not workspace_path:
        return []

    workspace_root = Path(os.path.realpath(workspace_path))
    root = _resolve_paper_root(workspace_root)
    lines = [
        f"Working directory for `str_replace_editor`: `{root}`.",
        (
            "All paths below are absolute paths. "
            "Resolve relative editor paths from this directory."
        ),
    ]

    if active_file:
        lines.append(
            f"Active file path: `{_resolve_display_path(active_file, workspace_root, root)}`."
        )

    try:
        children = sorted(root.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
    except OSError:
        return lines

    if root != workspace_root:
        lines.append(f"Primary paper directory inside the workspace: `{root}`.")

    top_level_entries = [
        f"{child}/" if child.is_dir() else str(child) for child in children[:max_top_level_entries]
    ]

    if top_level_entries:
        lines.append("Top-level workspace entries:")
        lines.extend(f"- `{entry}`" for entry in top_level_entries)

    tex_files = _find_tex_files(root, max_results=max_tex_files, max_depth=max_depth)
    if tex_files:
        lines.append("Candidate TeX files in this workspace:")
        lines.extend(f"- `{path}`" for path in tex_files)

    return lines


def _find_tex_files(root: Path, *, max_results: int, max_depth: int) -> list[str]:
    tex_files: list[str] = []
    queue: deque[tuple[Path, int]] = deque([(root, 0)])

    while queue and len(tex_files) < max_results:
        current, depth = queue.popleft()
        try:
            children = sorted(
                current.iterdir(),
                key=lambda path: (not path.is_dir(), path.name.lower()),
            )
        except OSError:
            continue

        for child in children:
            if child.is_file() and child.suffix.lower() == ".tex":
                tex_files.append(str(child))
                if len(tex_files) >= max_results:
                    break
            elif child.is_dir() and depth < max_depth:
                queue.append((child, depth + 1))

    return tex_files


def _resolve_paper_root(workspace_root: Path) -> Path:
    try:
        children = sorted(
            workspace_root.iterdir(),
            key=lambda path: (not path.is_dir(), path.name.lower()),
        )
    except OSError:
        return workspace_root

    top_level_dirs = [child for child in children if child.is_dir()]
    top_level_tex_files = [
        child for child in children if child.is_file() and child.suffix.lower() == ".tex"
    ]
    if len(top_level_dirs) == 1 and not top_level_tex_files:
        return top_level_dirs[0].resolve()
    return workspace_root


def _resolve_display_path(path_value: str, workspace_root: Path, root: Path) -> str:
    candidate = Path(path_value)
    if candidate.is_absolute():
        return str(candidate.resolve())

    workspace_candidate = (workspace_root / candidate).resolve()
    if workspace_candidate.exists():
        return str(workspace_candidate)

    root_candidate = (root / candidate).resolve()
    if root_candidate.exists():
        return str(root_candidate)

    if root != workspace_root:
        try:
            relative_to_root = candidate.relative_to(root.name)
        except ValueError:
            pass
        else:
            stripped_candidate = (root / relative_to_root).resolve()
            if stripped_candidate.exists():
                return str(stripped_candidate)

    return str(root_candidate)
