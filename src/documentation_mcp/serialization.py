from __future__ import annotations

import json
from typing import Any


def serialize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def serialized_character_count(value: Any) -> int:
    return len(serialize_json(value))


def serialized_string_prefix(value: str, maximum_content_characters: int) -> str:
    """Return the longest prefix whose JSON string content fits the budget."""
    if maximum_content_characters < 1:
        return ""

    used = 0
    prefix_length = 0
    for character in value:
        if character in {'"', "\\", "\b", "\f", "\n", "\r", "\t"}:
            contribution = 2
        elif ord(character) < 0x20:
            contribution = 6
        else:
            contribution = 1
        if used + contribution > maximum_content_characters:
            break
        used += contribution
        prefix_length += 1
    return value[:prefix_length]
