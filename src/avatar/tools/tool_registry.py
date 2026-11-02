"""Small typed registry shared by the model loop and MCP boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: set[str]
    validator: Callable[[dict], dict]
    properties: dict = field(default_factory=dict)
    required: tuple[str, ...] = ()
    write: bool = False

    @property
    def schema(self) -> dict:
        return {'type': 'function', 'function': {
            'name': self.name,
            'description': self.description,
            'parameters': {'type': 'object', 'properties': self.properties,
                           'required': list(self.required), 'additionalProperties': False},
        }}


class ToolRegistry:
    def __init__(self, specs):
        self._specs = {spec.name: spec for spec in specs}
        if len(self._specs) != len(list(specs)):
            raise ValueError('工具名称重复。')

    @property
    def names(self) -> set[str]:
        return set(self._specs)

    @property
    def schemas(self) -> list[dict]:
        return [spec.schema for spec in self._specs.values()]

    def validate(self, name: str, arguments) -> dict:
        spec = self._specs.get(name)
        if spec is None:
            raise ValueError('未知工具。')
        if not isinstance(arguments, dict):
            raise ValueError('工具参数必须是JSON对象。')
        if not set(arguments) <= spec.parameters:
            raise ValueError('不允许此工具参数。')
        return spec.validator(arguments)
