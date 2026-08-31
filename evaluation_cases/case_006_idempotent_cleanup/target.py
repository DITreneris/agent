from pathlib import Path


def remove_cache_file(path: Path) -> None:
    path.unlink(missing_ok=True)
