"""Data models for LaTeX project elements."""

from dataclasses import dataclass, field


@dataclass
class Section:
    name: str
    level: int  # 0=section, 1=subsection, 2=subsubsection
    content: str
    line_start: int = 0
    line_end: int = 0
    subsections: list["Section"] = field(default_factory=list)


@dataclass
class Citation:
    key: str
    title: str = ""
    authors: str = ""
    year: str = ""
    venue: str = ""
    entry_type: str = ""  # article, inproceedings, etc.
    raw: str = ""


@dataclass
class Figure:
    label: str = ""
    caption: str = ""
    path: str = ""  # \includegraphics path
    line_start: int = 0
    line_end: int = 0


@dataclass
class Table:
    label: str = ""
    caption: str = ""
    line_start: int = 0
    line_end: int = 0
