import re

from researchkit.memory.schema import CitationEntry, SectionInfo, VenueConfig


def parse_sections(content: str, file_path: str = "main.tex") -> list[SectionInfo]:
    """Extract section hierarchy from LaTeX content."""
    sections = []
    level_map = {"section": 1, "subsection": 2, "subsubsection": 3}
    pattern = re.compile(r"\\(section|subsection|subsubsection)\*?\{([^}]+)\}")

    for i, line in enumerate(content.split("\n"), start=1):
        match = pattern.search(line)
        if match:
            cmd, name = match.group(1), match.group(2)
            sections.append(SectionInfo(
                name=name.strip(),
                level=level_map[cmd],
                file_path=file_path,
                line_start=i,
            ))

    # Set line_end for each section (start of next section - 1)
    for i in range(len(sections) - 1):
        sections[i].line_end = sections[i + 1].line_start - 1

    return sections


def parse_citations(bib_content: str) -> list[CitationEntry]:
    """Extract citation entries from BibTeX content."""
    entries = []
    pattern = re.compile(r"@\w+\{([^,]+),", re.MULTILINE)

    for match in pattern.finditer(bib_content):
        key = match.group(1).strip()
        # Extract fields within this entry
        start = match.end()
        brace_count = 1
        end = start
        for j in range(start, len(bib_content)):
            if bib_content[j] == "{":
                brace_count += 1
            elif bib_content[j] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = j
                    break

        entry_text = bib_content[start:end]
        title = _extract_bib_field(entry_text, "title")
        author = _extract_bib_field(entry_text, "author")
        year = _extract_bib_field(entry_text, "year")
        venue = _extract_bib_field(entry_text, "journal") or _extract_bib_field(
            entry_text, "booktitle"
        )

        authors = [a.strip() for a in author.split(" and ")] if author else []

        entries.append(CitationEntry(
            key=key, title=title, authors=authors, year=year, venue=venue
        ))

    return entries


def _extract_bib_field(entry_text: str, field: str) -> str:
    pattern = re.compile(rf"{field}\s*=\s*[\{{\"](.*?)[\}}\"]", re.IGNORECASE | re.DOTALL)
    match = pattern.search(entry_text)
    return match.group(1).strip() if match else ""


def parse_document_class(content: str) -> VenueConfig:
    """Detect venue/template from \\documentclass."""
    pattern = re.compile(r"\\documentclass(?:\[([^\]]*)\])?\{([^}]+)\}")
    match = pattern.search(content)
    if not match:
        return VenueConfig()

    options = match.group(1) or ""
    doc_class = match.group(2)

    venue_hints = {
        "acl": "ACL",
        "acmart": "ACM",
        "neurips": "NeurIPS",
        "icml": "ICML",
        "aaai": "AAAI",
        "ieee": "IEEE",
        "iclr": "ICLR",
    }

    venue_name = ""
    for hint, name in venue_hints.items():
        if hint in doc_class.lower():
            venue_name = name
            break

    return VenueConfig(name=venue_name, doc_class=doc_class)


def parse_abstract(content: str) -> str:
    """Extract abstract text."""
    pattern = re.compile(
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL
    )
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def resolve_inputs(main_content: str, files: dict[str, str]) -> str:
    """Resolve \\input{} and \\include{} commands to build full document."""
    pattern = re.compile(r"\\(?:input|include)\{([^}]+)\}")

    def replacer(match):
        path = match.group(1)
        # Try with and without .tex extension
        for candidate in [path, f"{path}.tex"]:
            if candidate in files:
                return files[candidate]
            # Try with sections/ prefix
            prefixed = f"sections/{candidate}"
            if prefixed in files:
                return files[prefixed]
        return match.group(0)  # Keep original if not found

    return pattern.sub(replacer, main_content)
