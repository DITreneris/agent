from pathlib import Path
import ast


class FunctionNotFoundError(ValueError):
    pass

class MethodNotFoundError(ValueError):
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

def find_python_method_range(file_path: Path, class_name: str, method_name: str) -> tuple[int, int]:
    """
    Return 1-based start and end line numbers for a direct Python class method.
    Supports regular and async methods.
    Nested classes and inherited methods are intentionally out of scope.
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
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for class_node in node.body:
                if (
                    isinstance(class_node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and class_node.name == method_name
                ):
                    start_line = class_node.lineno
                    end_line = getattr(class_node, "end_lineno", None)

                    if end_line is None:
                        raise ValueError(
                            f"Could not determine end line for method: {class_name}.{method_name}"
                        )

                    return start_line, end_line

            raise MethodNotFoundError(f"Method not found: {class_name}.{method_name}")

    raise MethodNotFoundError(f"Method not found: {class_name}.{method_name}")
