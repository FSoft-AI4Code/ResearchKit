import pytest

from researchkit.agents.str_replace_editor import WorkspaceStrReplaceEditor


def test_view_file_range(tmp_path):
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))

    result = editor.execute(
        command="view",
        path=str(paper_path),
        view_range=[2, 3],
    )

    assert result.command == "view"
    assert result.metadata["view_range"] == [2, 3]
    assert "line2" in result.output
    assert "line1" not in result.output


def test_view_accepts_workspace_relative_path(tmp_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    intro_path = sections_dir / "introduction.tex"
    intro_path.write_text("intro line\n", encoding="utf-8")
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))

    result = editor.execute(command="view", path="sections/introduction.tex")

    assert result.command == "view"
    assert "intro line" in result.output
    assert result.summary == f"Viewed file `{intro_path}`."


def test_view_directory_ignores_view_range(tmp_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    (sections_dir / "introduction.tex").write_text("intro line\n", encoding="utf-8")
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))

    result = editor.execute(command="view", path=".", view_range=[1, 10])

    assert result.command == "view"
    assert result.metadata["kind"] == "directory"
    assert result.metadata["ignored_view_range"] == [1, 10]
    assert "sections/introduction.tex" in result.output


@pytest.mark.parametrize(
    "alias_path",
    [
        "/workspace",
        "/root/project",
        "/home/oai/project",
        "/workspace/sections/introduction.tex",
        "/root/project/sections/introduction.tex",
        "/home/oai/project/sections/introduction.tex",
    ],
)
def test_view_accepts_common_workspace_aliases(tmp_path, alias_path):
    sections_dir = tmp_path / "sections"
    sections_dir.mkdir()
    intro_path = sections_dir / "introduction.tex"
    intro_path.write_text("intro line\n", encoding="utf-8")
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))

    result = editor.execute(command="view", path=alias_path)

    assert result.command == "view"
    assert "intro line" in result.output or "sections/introduction.tex" in result.output


def test_create_insert_and_undo_edit(tmp_path):
    paper_path = tmp_path / "paper.tex"
    history: dict[str, list[str | None]] = {}
    editor = WorkspaceStrReplaceEditor(
        workspace_path=str(tmp_path),
        history=history,
    )

    create_result = editor.execute(
        command="create",
        path=str(paper_path),
        file_text="alpha\nbeta\n",
    )
    insert_result = editor.execute(
        command="insert",
        path=str(paper_path),
        insert_line=1,
        new_str="inserted",
    )
    undo_result = editor.execute(command="undo_edit", path=str(paper_path))

    assert create_result.metadata["created"] is True
    assert insert_result.metadata["insert_line"] == 1
    assert undo_result.metadata["restored"] is True
    assert paper_path.read_text(encoding="utf-8") == "alpha\nbeta\n"


def test_str_replace_requires_unique_match(tmp_path):
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("repeat\nrepeat\n", encoding="utf-8")
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))

    with pytest.raises(ValueError, match="appears multiple times"):
        editor.execute(
            command="str_replace",
            path=str(paper_path),
            old_str="repeat",
            new_str="done",
        )


def test_str_replace_reports_trailing_newline_hint_for_near_match(tmp_path):
    paper_path = tmp_path / "paper.tex"
    paper_path.write_text("alpha\nbeta", encoding="utf-8")
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))

    with pytest.raises(ValueError, match="remove trailing newline characters"):
        editor.execute(
            command="str_replace",
            path=str(paper_path),
            old_str="alpha\nbeta\n",
            new_str="",
        )


def test_str_replace_succeeds_when_old_str_matches_exact_eof_block(tmp_path):
    paper_path = tmp_path / "introduction.tex"
    paper_path.write_text(
        "\\section{Introduction}\n"
        "\\label{sec:introduction}\n\n"
        "Contributions\n"
        "- A novel documentation-driven paradigm for idiomatic code migration.\n"
        "- We propose a new approach that leverages automatically generated documentation (via CodeWiki) as an intermediate representation, enabling migration at the codebase level rather than traditional file-by-file or component-level translation. This paradigm explicitly targets the generation of idiomatic Rust codebases, rather than merely syntactic translations.\n"
        "- A documentation-guided iterative refinement mechanism.\n"
        "We introduce an iterative process that assesses and refines generated Rust code by comparing its documentation against that of the original C codebase. This mechanism promotes semantic completeness, improves alignment with the original system’s functionality, and encourages idiomatic structure.\n"
        "- Execution-aware code revision with test-driven feedback.\n"
        "We incorporate dynamic feedback from test execution to iteratively revise the translated code, enabling the system to correct behavioral inconsistencies and improve functional correctness beyond static translation.\n"
        "Large-scale evaluation on real-world codebases.\n"
        "- To the best of our knowledge, we present the first evaluation of automated C-to-Rust migration on large-scale, real-world codebases (up to XX K lines of code), addressing a key limitation of prior work that primarily focuses on small benchmarks.",
        encoding="utf-8",
    )
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))
    old_str = (
        "- A novel documentation-driven paradigm for idiomatic code migration.\n"
        "- We propose a new approach that leverages automatically generated documentation (via CodeWiki) as an intermediate representation, enabling migration at the codebase level rather than traditional file-by-file or component-level translation. This paradigm explicitly targets the generation of idiomatic Rust codebases, rather than merely syntactic translations.\n"
        "- A documentation-guided iterative refinement mechanism.\n"
        "We introduce an iterative process that assesses and refines generated Rust code by comparing its documentation against that of the original C codebase. This mechanism promotes semantic completeness, improves alignment with the original system’s functionality, and encourages idiomatic structure.\n"
        "- Execution-aware code revision with test-driven feedback.\n"
        "We incorporate dynamic feedback from test execution to iteratively revise the translated code, enabling the system to correct behavioral inconsistencies and improve functional correctness beyond static translation.\n"
        "Large-scale evaluation on real-world codebases.\n"
        "- To the best of our knowledge, we present the first evaluation of automated C-to-Rust migration on large-scale, real-world codebases (up to XX K lines of code), addressing a key limitation of prior work that primarily focuses on small benchmarks."
    )

    result = editor.execute(
        command="str_replace",
        path=str(paper_path),
        old_str=old_str,
        new_str="",
    )

    assert result.command == "str_replace"
    assert paper_path.read_text(encoding="utf-8") == (
        "\\section{Introduction}\n"
        "\\label{sec:introduction}\n\n"
        "Contributions\n"
    )


def test_editor_rejects_paths_outside_workspace(tmp_path):
    editor = WorkspaceStrReplaceEditor(workspace_path=str(tmp_path))
    outside_path = tmp_path.parent / "outside.tex"
    outside_path.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the configured workspace"):
        editor.execute(command="view", path=str(outside_path))

    with pytest.raises(ValueError, match="outside the configured workspace"):
        editor.execute(command="view", path="../outside.tex")
