from pathlib import Path
import ast


class FunctionNotFoundError(ValueError):
    pass


def find_python_function_range(file_path: Path, function_name: str) -> tuple[int, int]:
    """
    Return 1-based start and end line numbers for a top-level Python function.
    Supports regular and async functions.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SyntaxError(f"Cannot parse Python file: {file_path}") from exc

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", None)

            if end_line is None:
                raise ValueError(f"Could not determine end line for function: {function_name}")

            return start_line, end_line

    raise FunctionNotFoundError(f"Function not found: {function_name}")
