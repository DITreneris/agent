from prompt_builder import build_file_audit_prompt


def test_file_audit_prompt_includes_usefulness_rules():
    prompt = build_file_audit_prompt("example.py", "print('hello')")

    assert "Audit usefulness rules" in prompt
    assert "practical failure mode" in prompt
    assert "generic approval" in prompt
    assert "non-blocking risk" in prompt


def test_file_audit_prompt_includes_verdict_guidance():
    prompt = build_file_audit_prompt("example.py", "print('hello')")

    assert "Verdict guidance" in prompt
    assert "GO_WITH_NOTES" in prompt
    assert "BLOCK" in prompt
    assert "meaningful practical risk" in prompt

def test_file_audit_prompt_preserves_special_characters():
    file_content = "print('hello')\n# markdown: ### heading\ntext = \"triple quote marker: '''\""
    prompt = build_file_audit_prompt("example.py", file_content)

    assert "AUDIT TARGET:" in prompt
    assert "CODE:" in prompt
    assert "example.py" in prompt
    assert file_content in prompt
