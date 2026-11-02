import pytest

from avatar.tools.tool_registry import ToolRegistry, ToolSpec


def test_registry_validates_before_executor_runs():
    calls = []
    registry = ToolRegistry([ToolSpec('echo', '回显', {'text'}, lambda args: {'text': args['text'].strip()})])
    assert registry.validate('echo', {'text': ' hi '}) == {'text': 'hi'}
    with pytest.raises(ValueError, match='不允许'):
        registry.validate('echo', {'text': 'hi', 'command': 'delete'})
    with pytest.raises(ValueError, match='未知'):
        registry.validate('missing', {})
    assert calls == []


def test_registry_exports_openai_tool_schemas():
    registry = ToolRegistry([ToolSpec('ping', '检查', set(), lambda args: {})])
    schema = registry.schemas[0]
    assert schema['function']['name'] == 'ping'
    assert schema['function']['parameters']['additionalProperties'] is False
