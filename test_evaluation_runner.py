from pathlib import Path

from evaluation_runner import load_evaluation_cases


def test_load_evaluation_cases(tmp_path: Path) -> None:
    case_dir = tmp_path / "case_001"
    case_dir.mkdir()

    (case_dir / "target.py").write_text(
        "def example() -> int:\n    return 1\n",
        encoding="utf-8",
    )

    (case_dir / "expected.json").write_text(
        """{
  "id": "case_001",
  "command": "audit_function",
  "symbol": "example",
  "expected_verdicts": ["GO"],
  "forbidden_claims": []
}
""",
        encoding="utf-8",
    )

    cases = load_evaluation_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0]["id"] == "case_001"
    assert cases[0]["symbol"] == "example"
    assert cases[0]["target_path"].endswith("target.py")


def test_load_real_evaluation_cases() -> None:
    cases = load_evaluation_cases(Path("evaluation_cases"))

    assert [case["id"] for case in cases] == [
        "case_001_correct_helper_contract",
        "case_002_real_none_bug",
        "case_003_intentional_none_contract",
    ]

    assert cases[0]["expected_verdicts"] == ["GO"]
    assert cases[1]["expected_verdicts"] == ["GO_WITH_NOTES", "BLOCK"]
    assert cases[2]["expected_verdicts"] == ["GO"]
