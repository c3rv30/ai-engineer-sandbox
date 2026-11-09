from typing import List, Dict, Optional

# Window of turns sent to the LLM. It bounds the token cost: the full history of a long
# conversation would inflate every prompt without adding context useful for resolving a
# coreference, which nearly always points to the previous turn.
DEFAULT_WINDOW = 4


def format_history(history: Optional[List[Dict[str, str]]], max_turns: int = DEFAULT_WINDOW) -> str:
    """Formats the last turns of the conversation as a block for a prompt.

    Returns an empty string if there is nothing usable, so the prompt does not contain
    a history header with nothing under it.

    The client sends the history, so a turn without 'role'/'content' (or one that is not
    even a dictionary) is dropped instead of taking down the whole request with a KeyError.
    """
    if not history:
        return ""

    lines = []
    for msg in history[-max_turns:]:
        if not isinstance(msg, dict):
            continue
        role, content = msg.get("role"), msg.get("content")
        if role and content:
            lines.append(f"- {role.upper()}: {content}")

    if not lines:
        return ""

    return "Recent conversation history:\n" + "\n".join(lines) + "\n"
