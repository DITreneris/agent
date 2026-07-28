from pathlib import Path

from audit_context import build_same_file_context


def test_build_same_file_context_includes_called_top_level_helper(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def helper(value):\n"
        "    return value.strip()\n"
        "\n"
        "def target(value):\n"
        "    return helper(value)\n",
        encoding="utf-8",
    )

    context = build_same_file_context(
        file_path=file_path,
        target_start_line=4,
        target_end_line=5,
    )

    assert "def helper(value):" in context
    assert "return value.strip()" in context
    assert "def target(value):" not in context


def test_build_same_file_context_excludes_uncalled_helpers(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def used(value):\n"
        "    return value.strip()\n"
        "\n"
        "def unused(value):\n"
        "    return value.upper()\n"
        "\n"
        "def target(value):\n"
        "    return used(value)\n",
        encoding="utf-8",
    )

    context = build_same_file_context(
        file_path=file_path,
        target_start_line=7,
        target_end_line=8,
    )

    assert "def used(value):" in context
    assert "def unused(value):" not in context


def test_build_same_file_context_includes_multiple_called_helpers(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def normalize(value):\n"
        "    return value.strip()\n"
        "\n"
        "def validate(value):\n"
        "    return bool(value)\n"
        "\n"
        "def target(value):\n"
        "    cleaned = normalize(value)\n"
        "    return validate(cleaned)\n",
        encoding="utf-8",
    )

    context = build_same_file_context(
        file_path=file_path,
        target_start_line=7,
        target_end_line=9,
    )

    assert "def normalize(value):" in context
    assert "def validate(value):" in context


def test_build_same_file_context_names_returns_called_helpers(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def normalize(value):\n"
        "    return value.strip()\n"
        "\n"
        "def validate(value):\n"
        "    return bool(value)\n"
        "\n"
        "def target(value):\n"
        "    cleaned = normalize(value)\n"
        "    return validate(cleaned)\n",
        encoding="utf-8",
    )

    from audit_context import build_same_file_context_names

    names = build_same_file_context_names(
        file_path=file_path,
        target_start_line=7,
        target_end_line=9,
    )

    assert names == {"normalize", "validate"}


def test_build_same_file_context_handles_invalid_python(
    tmp_path: Path,
) -> None:
    from audit_context import build_same_file_context_names

    file_path = tmp_path / "broken.py"
    file_path.write_text(
        "def broken(:\n"
        "    pass\n",
        encoding="utf-8",
    )

    assert build_same_file_context(
        file_path=file_path,
        target_start_line=1,
        target_end_line=2,
    ) == ""

    assert build_same_file_context_names(
        file_path=file_path,
        target_start_line=1,
        target_end_line=2,
    ) == set()
