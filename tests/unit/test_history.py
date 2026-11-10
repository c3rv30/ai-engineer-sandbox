"""Regression of the conversation history (BUG-03).

The client sends the history: it must reach the prompt limited to the last turns and
without a malformed turn taking down the request.
"""
import pytest

from src.services.history import format_history


def turn(i):
    return {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"}


def test_window_of_the_last_four_turns_in_order():
    result = format_history([turn(i) for i in range(6)])
    lines = result.splitlines()
    assert lines[0] == "Recent conversation history:"
    assert lines[1:] == ["- USER: message 2", "- ASSISTANT: message 3", "- USER: message 4", "- ASSISTANT: message 5"]


def test_malformed_turns_are_dropped():
    history = [
        "not a dictionary",
        {"role": "user"},
        {"content": "no role"},
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "valid"},
    ]
    assert format_history(history) == "Recent conversation history:\n- ASSISTANT: valid\n"


@pytest.mark.parametrize("history", [None, [], [{"role": "user"}], ["text", 3]])
def test_empty_or_unusable_history(history):
    assert format_history(history) == ""
