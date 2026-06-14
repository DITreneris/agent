from pathlib import Path

from project_config import (
    EXCLUDED_DIRS,
    INCLUDED_EXTENSIONS,
    MAX_FILE_CHARS,
)


def is_excluded_path(path: Path) -> bool:
    """Return True if any part of the path is in excluded directories."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def is_included_file(path: Path) -> bool:
    """Return True if file has an allowed extension."""
    return path.is_file() and path.suffix.lower() in INCLUDED_EXTENSIONS


def scan_project_files(root_path: Path) -> list[Path]:
    """Return readable project files under root_path."""
    root_path = root_path.resolve()
    files: list[Path] = []

    for path in root_path.rglob("*"):
        if is_excluded_path(path.relative_to(root_path)):
            continue

        if is_included_file(path):
            files.append(path)

    return sorted(files)


def read_project_file(file_path: Path) -> str:
    """Read a project file safely with a character limit."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Could not read file: {exc}"

    if len(text) > MAX_FILE_CHARS:
        return text[:MAX_FILE_CHARS] + "\n\n[File truncated]"

    return text


def format_file_list(files: list[Path], root_path: Path) -> str:
    """Format project files as relative paths."""
    root_path = root_path.resolve()

    if not files:
        return "No project files found."

    lines = ["Project files:"]
    for index, file_path in enumerate(files, start=1):
        relative_path = file_path.relative_to(root_path)
        lines.append(f"{index}. {relative_path}")

    return "\n".join(lines)
