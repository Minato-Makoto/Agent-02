from agentforge.schema_normalizer import (
    normalize_openai_tools_for_provider,
    normalize_tool_schema_for_provider,
)


def test_gemini_schema_cleanup_drops_unsupported_keywords_and_flattens_literals():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "$defs": {"Mode": {"type": "string"}},
        "properties": {
            "mode": {
                "anyOf": [
                    {"const": "fast", "type": "string"},
                    {"const": "safe", "type": "string"},
                ],
                "pattern": "^[a-z]+$",
            },
            "count": {"type": ["integer", "null"], "minimum": 1},
        },
        "required": ["mode"],
    }

    cleaned = normalize_tool_schema_for_provider(schema, "gemini")
    mode_schema = cleaned["properties"]["mode"]
    count_schema = cleaned["properties"]["count"]

    assert cleaned["type"] == "object"
    assert "additionalProperties" not in cleaned
    assert "$defs" not in cleaned
    assert "anyOf" not in mode_schema
    assert mode_schema["enum"] == ["fast", "safe"]
    assert "pattern" not in mode_schema
    assert count_schema["type"] == "integer"
    assert "minimum" not in count_schema


def test_normalize_openai_tools_for_provider_maintains_tool_contract():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "select_mode",
                "description": "Pick mode",
                "parameters": {
                    "type": "object",
                    "properties": {"mode": {"const": "safe", "type": "string"}},
                },
            },
        }
    ]

    out = normalize_openai_tools_for_provider(tools, "gemini")
    assert len(out) == 1
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "select_mode"
    assert out[0]["function"]["parameters"]["type"] == "object"
    assert out[0]["function"]["parameters"]["properties"]["mode"]["enum"] == ["safe"]
