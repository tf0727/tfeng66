"""Business-agnostic tool protocol and registry."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具已注册：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"未知工具：{name}") from exc

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self.get(name)
        if not isinstance(arguments, dict): raise ValueError('工具参数必须是对象')
        properties = tool.parameters.get('properties', {})
        if set(tool.parameters.get('required', [])) - arguments.keys(): raise ValueError('缺少必填工具参数')
        if tool.parameters.get('additionalProperties') is False and arguments.keys() - properties.keys(): raise ValueError('存在未声明的工具参数')
        for key,value in arguments.items():
            spec = properties.get(key, {})
            kind = spec.get('type')
            expected = {'string':str,'object':dict,'array':list,'number':(int,float),'integer':int,'boolean':bool}.get(kind)
            if expected and (not isinstance(value,expected) or (kind in {'number','integer'} and isinstance(value,bool))): raise ValueError('工具参数类型不正确')
            if kind in {'number','integer'} and (value < spec.get('minimum',float('-inf')) or value > spec.get('maximum',float('inf'))): raise ValueError('工具参数超出范围')
        return tool.handler(**arguments)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]
