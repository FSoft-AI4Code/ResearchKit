"""LaTeX project parser -- regex-based MVP for extracting paper structure."""

from __future__ import annotations

import re
from pathlib import Path

from researchkit.latex.models import Citation, Figure, Section, Table

_SECTION_RE = re.compile(
    r"\\(section|subsection|subsubsection)\*?\{([^}]+)\}", re.MULTILINE
)
_INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_CITE_RE = re.compile(r"\\(?:cite|citep|citet|citeauthor|citeyear)\{([^}]+)\}")
_FIGURE_ENV_RE = re.compile(
    r"\\begin\{figure\}.*?\\end\{figure\}", re.DOTALL
)
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_CAPTION_RE = re.compile(r"\\caption\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_TABLE_ENV_RE = re.compile(r"\\begin\{table\}.*?\\end\{table\}", re.DOTALL)

_BIB_ENTRY_RE = re.compile(
    r"@(\w+)\s*\{([^,]+),\s*(.*?)\n\}", re.DOTALL
)
_BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*\{([^}]*)\}")

_LEVEL_MAP = {"section": 0, "subsection": 1, "subsubsection": 2}


class LaTeXProject:
    """Treats a LaTeX project like a codebase, providing structural queries."""

    def __init__(self, files: dict[str, str] | None = None, project_dir: str | Path | None = None):
        """Initialize from either in-memory files dict or a directory on disk.

        Args:
            files: Dict mapping relative file paths to their content strings.
            project_dir: Path to a LaTeX project directory on disk.
        """
        self._files: dict[str, str] = {}

        if files:
            self._files = dict(files)
        elif project_dir:
            self._load_from_dir(Path(project_dir))

    def _load_from_dir(self, root: Path) -> None:
        for ext in ("*.tex", "*.bib", "*.sty", "*.cls"):
            for f in root.rglob(ext):
                rel = str(f.relative_to(root))
                self._files[rel] = f.read_text(encoding="utf-8", errors="replace")

    @property
    def main_tex(self) -> str:
        """Find and return the main .tex file content."""
        if "main.tex" in self._files:
            return self._files["main.tex"]
        for name, content in self._files.items():
            if name.endswith(".tex") and "\\documentclass" in content:
                return content
        # Fallback: return the first .tex file
        for name, content in self._files.items():
            if name.endswith(".tex"):
                return content
        return ""

    def get_full_text(self) -> str:
        """Resolve \\input{} includes and return the full document as a single string."""
        main = self.main_tex
        return self._resolve_inputs(main, depth=0)

    def _resolve_inputs(self, content: str, depth: int) -> str:
        if depth > 10:
            return content

        def replacer(match: re.Match) -> str:
            path = match.group(1)
            if not path.endswith(".tex"):
                path += ".tex"
            # Try exact path and common variants
            for candidate in [path, f"sections/{path}", f"chapters/{path}"]:
                if candidate in self._files:
                    return self._resolve_inputs(self._files[candidate], depth + 1)
            return match.group(0)

        return _INPUT_RE.sub(replacer, content)

    def get_sections(self) -> list[Section]:
        """Extract section hierarchy from the full document."""
        full_text = self.get_full_text()
        lines = full_text.split("\n")
        sections: list[Section] = []

        matches = list(_SECTION_RE.finditer(full_text))
        for i, m in enumerate(matches):
            level = _LEVEL_MAP.get(m.group(1), 0)
            name = m.group(2).strip()
            start = full_text[:m.start()].count("\n")
            if i + 1 < len(matches):
                end = full_text[:matches[i + 1].start()].count("\n")
                content = "\n".join(lines[start:end])
            else:
                content = "\n".join(lines[start:])

            sections.append(
                Section(
                    name=name,
                    level=level,
                    content=content,
                    line_start=start,
                    line_end=end if i + 1 < len(matches) else len(lines),
                )
            )

        return sections

    def get_citations(self) -> list[Citation]:
        """Parse BibTeX files and return citation entries."""
        citations: list[Citation] = []
        for name, content in self._files.items():
            if not name.endswith(".bib"):
                continue
            for match in _BIB_ENTRY_RE.finditer(content):
                entry_type = match.group(1).lower()
                key = match.group(2).strip()
                body = match.group(3)

                fields: dict[str, str] = {}
                for fm in _BIB_FIELD_RE.finditer(body):
                    fields[fm.group(1).lower()] = fm.group(2).strip()

                citations.append(
                    Citation(
                        key=key,
                        title=fields.get("title", ""),
                        authors=fields.get("author", ""),
                        year=fields.get("year", ""),
                        venue=fields.get("journal", fields.get("booktitle", "")),
                        entry_type=entry_type,
                        raw=match.group(0),
                    )
                )

        return citations

    def get_cite_keys_in_text(self) -> set[str]:
        """Find all citation keys referenced in the document text."""
        full_text = self.get_full_text()
        keys: set[str] = set()
        for match in _CITE_RE.finditer(full_text):
            for key in match.group(1).split(","):
                keys.add(key.strip())
        return keys

    def get_figures(self) -> list[Figure]:
        """Find all figure environments in the document."""
        full_text = self.get_full_text()
        figures: list[Figure] = []

        for match in _FIGURE_ENV_RE.finditer(full_text):
            env_text = match.group(0)
            path_match = _INCLUDEGRAPHICS_RE.search(env_text)
            caption_match = _CAPTION_RE.search(env_text)
            label_match = _LABEL_RE.search(env_text)

            figures.append(
                Figure(
                    label=label_match.group(1) if label_match else "",
                    caption=caption_match.group(1) if caption_match else "",
                    path=path_match.group(1) if path_match else "",
                    line_start=full_text[:match.start()].count("\n"),
                    line_end=full_text[:match.end()].count("\n"),
                )
            )

        return figures

    def get_tables(self) -> list[Table]:
        """Find all table environments in the document."""
        full_text = self.get_full_text()
        tables: list[Table] = []

        for match in _TABLE_ENV_RE.finditer(full_text):
            env_text = match.group(0)
            caption_match = _CAPTION_RE.search(env_text)
            label_match = _LABEL_RE.search(env_text)

            tables.append(
                Table(
                    label=label_match.group(1) if label_match else "",
                    caption=caption_match.group(1) if caption_match else "",
                    line_start=full_text[:match.start()].count("\n"),
                    line_end=full_text[:match.end()].count("\n"),
                )
            )

        return tables
