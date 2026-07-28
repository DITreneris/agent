from pathlib import Path

import pytest

from chat_agent import prepare_selected_code_audit


def test_prepare_selected_code_audit_valid_range(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def one():\n"
        "    return 1\n"
        "\n"
        "def two():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    prepared = prepare_selected_code_audit(
        project_root=tmp_path,
        file_name="sample.py",
        start_line=1,
        end_line=2,
    )

    assert prepared.file_path == file_path.resolve()
    assert prepared.relative_path == "sample.py"
    assert prepared.start_line == 1
    assert prepared.end_line == 2
    assert prepared.selected_content == "1: def one():\n2:     return 1"
    assert prepared.context_content == ""

def test_prepare_selected_code_audit_rejects_invalid_range(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("print('x')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid line range"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="sample.py",
            start_line=2,
            end_line=1,
        )


def test_prepare_selected_code_audit_rejects_range_over_200_lines(tmp_path: Path) -> None:
    file_path = tmp_path / "large.py"
    file_path.write_text(
        "\n".join(f"line_{i} = {i}" for i in range(1, 203)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Maximum audit range is 200 lines"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="large.py",
            start_line=1,
            end_line=201,
        )


def test_prepare_selected_code_audit_rejects_path_escape(tmp_path: Path) -> None:
    outside_file = tmp_path.parent / "outside.py"
    outside_file.write_text("print('outside')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Access denied"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="../outside.py",
            start_line=1,
            end_line=1,
        )


def test_prepare_selected_code_audit_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="File not found"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="missing.py",
            start_line=1,
            end_line=1,
        )


def test_prepare_selected_code_audit_rejects_directory_path(tmp_path: Path) -> None:
    directory_path = tmp_path / "folder"
    directory_path.mkdir()

    with pytest.raises(ValueError, match="Path is not a file"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="folder",
            start_line=1,
            end_line=1,
        )


def test_prepare_selected_code_audit_rejects_start_line_beyond_file_length(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("print('x')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Start line exceeds file length"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="sample.py",
            start_line=2,
            end_line=2,
        )

def test_prepare_selected_code_audit_rejects_end_line_beyond_file_length(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "a = 1\n"
        "b = 2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="End line exceeds file length"):
        prepare_selected_code_audit(
            project_root=tmp_path,
            file_name="sample.py",
            start_line=1,
            end_line=10,
        )


def test_prepare_selected_code_audit_accepts_typescript_range(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.ts"
    file_path.write_text(
        "export function result(challengeTargetYears: number): string {\n"
        "    return `Challenge cleared: you outlasted your colleague's "
        "${challengeTargetYears.toFixed(1)}y.`;\n"
        "}\n",
        encoding="utf-8",
    )

    prepared = prepare_selected_code_audit(
        project_root=tmp_path,
        file_name="sample.ts",
        start_line=1,
        end_line=3,
    )

    assert "colleague's" in prepared.selected_content
    assert prepared.context_content == ""
    assert prepared.context_names == set()
