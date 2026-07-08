from chat_agent import contains_multiple_slash_commands, handle_memory_command


def test_contains_multiple_slash_commands_detects_multiple_commands():
    user_input = "/audit_lines chat_agent.py 1 20\n/audit_lines chat_agent.py 21 40"

    assert contains_multiple_slash_commands(user_input) is True


def test_contains_multiple_slash_commands_allows_single_command():
    user_input = "/audit_lines chat_agent.py 1 20"

    assert contains_multiple_slash_commands(user_input) is False


def test_multi_command_input_is_rejected():
    user_input = "/audit_lines chat_agent.py 1 20\n/audit_lines chat_agent.py 21 40"

    result = handle_memory_command(user_input)

    assert result == "Please run one command at a time.\nNo audit started."
