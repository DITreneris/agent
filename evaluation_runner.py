from __future__ import annotations

import json
from pathlib import Path


EVALUATION_CASES_DIR = Path("evaluation_cases")


def load_evaluation_cases(base_dir: Path = EVALUATION_CASES_DIR) -> list[dict]:
    cases: list[dict] = []

    for case_dir in sorted(base_dir.iterdir()):
        if not case_dir.is_dir():
            continue

        target_path = case_dir / "target.py"
        expected_path = case_dir / "expected.json"

        if not target_path.exists() or not expected_path.exists():
            raise ValueError(f"Incomplete evaluation case: {case_dir}")

        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        expected["case_dir"] = str(case_dir)
        expected["target_path"] = str(target_path)
        cases.append(expected)

    return cases


if __name__ == "__main__":
    loaded_cases = load_evaluation_cases()
    print(f"Loaded evaluation cases: {len(loaded_cases)}")

    for case in loaded_cases:
        print(f"- {case['id']}: {case['symbol']}")
