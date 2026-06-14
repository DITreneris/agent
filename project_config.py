from pathlib import Path

# Project root directory.
# "." means: current folder where you run chat_agent.py
PROJECT_ROOT = Path(".")

# Folders that should never be indexed.
EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
}

# File types that are safe and useful for project context.
INCLUDED_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}

# Safety limit: do not read huge files fully.
MAX_FILE_CHARS = 20000
