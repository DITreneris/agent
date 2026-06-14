from pathlib import Path

from project_scanner import scan_project_files


def build_project_summary(root_path: Path) -> str:
    """Build a compact human-readable project summary."""
    root_path = root_path.resolve()
    files = scan_project_files(root_path)

    lines = [
        "PROJECT CONTEXT",
        f"Root: {root_path}",
        f"Files indexed: {len(files)}",
        "",
        "Files:",
    ]

    for file_path in files:
        relative_path = file_path.relative_to(root_path)
        lines.append(f"- {relative_path}")

    return "\n".join(lines)
