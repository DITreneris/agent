from pathlib import Path
import ast


def build_same_file_context(
    file_path: Path,
    target_start_line: int,
    target_end_line: int,
) -> str:
    if file_path.suffix.lower() != ".py":
        return ""

    source = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    lines = source.splitlines()

    target_node = None

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        node_end_line = getattr(node, "end_lineno", None)

        if (
            node.lineno == target_start_line
            and node_end_line == target_end_line
        ):
            target_node = node
            break

    if target_node is None:
        return ""

    called_names = {
        call.func.id
        for call in ast.walk(target_node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
    }

    context_blocks: list[str] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        if node is target_node:
            continue

        if node.name not in called_names:
            continue

        node_end_line = getattr(node, "end_lineno", None)

        if node_end_line is None:
            continue

        block = "\n".join(
            lines[node.lineno - 1:node_end_line]
        )
        context_blocks.append(block)

    return "\n\n".join(context_blocks)


def build_same_file_context_names(
    file_path: Path,
    target_start_line: int,
    target_end_line: int,
) -> set[str]:
    if file_path.suffix.lower() != ".py":
        return set()

    source = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    target_node = None

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        node_end_line = getattr(node, "end_lineno", None)

        if (
            node.lineno == target_start_line
            and node_end_line == target_end_line
        ):
            target_node = node
            break

    if target_node is None:
        return set()

    called_names = {
        call.func.id
        for call in ast.walk(target_node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
    }

    available_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node is not target_node
    }

    return called_names & available_names
