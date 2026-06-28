from pathlib import Path

import pytest

from code_chunker import (
    find_python_function_range,
    find_python_method_range,
    FunctionNotFoundError,
    MethodNotFoundError,
)

def test_find_python_function_range_finds_regular_function(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def first():",
                "    return 1",
                "",
                "def target():",
                "    x = 1",
                "    return x",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert find_python_function_range(file_path, "target") == (4, 6)


def test_find_python_function_range_finds_async_function(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "async def target():",
                "    return 1",
            ]
        ),
        encoding="utf-8",
    )

    assert find_python_function_range(file_path, "target") == (1, 2)


def test_find_python_function_range_raises_when_missing(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def existing():\n    return 1\n",
        encoding="utf-8",
    )

    with pytest.raises(FunctionNotFoundError, match="Function not found"):
        find_python_function_range(file_path, "missing")


def test_find_python_function_range_raises_on_syntax_error(tmp_path: Path):
    file_path = tmp_path / "broken.py"
    file_path.write_text(
        "def broken(:\n    pass\n",
        encoding="utf-8",
    )

    with pytest.raises(SyntaxError, match="Cannot parse Python file"):
        find_python_function_range(file_path, "broken")

def test_find_python_method_range_finds_regular_class_method(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "class Worker:",
                "    def helper(self):",
                "        return 1",
                "",
                "    def target(self):",
                "        x = 1",
                "        return x",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert find_python_method_range(file_path, "Worker", "target") == (5, 7)


def test_find_python_method_range_finds_async_class_method(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "class Worker:",
                "    async def target(self):",
                "        return 1",
            ]
        ),
        encoding="utf-8",
    )

    assert find_python_method_range(file_path, "Worker", "target") == (2, 3)


def test_find_python_method_range_raises_when_class_missing(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "class Existing:\n    def target(self):\n        return 1\n",
        encoding="utf-8",
    )

    with pytest.raises(MethodNotFoundError, match="Method not found"):
        find_python_method_range(file_path, "Missing", "target")


def test_find_python_method_range_raises_when_method_missing(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "class Worker:\n    def existing(self):\n        return 1\n",
        encoding="utf-8",
    )

    with pytest.raises(MethodNotFoundError, match="Method not found"):
        find_python_method_range(file_path, "Worker", "missing")

def test_find_python_method_range_does_not_match_top_level_function(tmp_path: Path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "\n".join(
            [
                "def target():",
                "    return 1",
                "",
                "class Worker:",
                "    def other(self):",
                "        return 2",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(MethodNotFoundError, match="Method not found"):
        find_python_method_range(file_path, "Worker", "target")
