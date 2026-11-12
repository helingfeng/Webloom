"""脚本、MCP 试跑和开放采集共用的参数契约。"""

import math
import re
from typing import Any

SENSITIVE_TYPES = {"secret", "header", "cookie", "localStorage"}


def normalize_definitions(definitions: list[dict]) -> list[dict]:
    result, names, header_names = [], set(), set()
    for original in definitions or []:
        item = dict(original)
        name = str(item.get("name", "")).strip()
        if not name or len(name) > 255 or any(c.isspace() for c in name):
            raise ValueError("参数名不能为空、不能含空白且最长 255 字符")
        if name in names:
            raise ValueError(f"参数名重复: {name}")
        names.add(name)
        item["name"] = name
        value = item.get("default")
        kind = item.get("type", "string")
        if kind in ("header", "cookie") and not re.fullmatch(
            r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name
        ):
            raise ValueError(f"参数 {name} 不是合法的 Header / Cookie 名称")
        if kind == "header":
            if name.lower() in header_names:
                raise ValueError(f"Header 参数名重复: {name}")
            header_names.add(name.lower())
        if value is not None:
            if kind == "number" and isinstance(value, str):
                try:
                    value = float(value)
                except ValueError as exc:
                    raise ValueError(f"参数 {name} 的默认值必须是数字") from exc
            if kind == "boolean" and isinstance(value, str):
                if value.lower() not in ("true", "false"):
                    raise ValueError(f"参数 {name} 的默认值必须是 true 或 false")
                value = value.lower() == "true"
            _validate_value(name, kind, value)
            item["default"] = value
        result.append(item)
    return result


def _validate_value(name: str, kind: str, value: Any) -> None:
    if kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "number":
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    else:
        valid = isinstance(value, str)
    if kind == "header" and isinstance(value, str) and ("\r" in value or "\n" in value):
        raise ValueError(f"Header 参数 {name} 不能包含换行")
    if not valid:
        raise ValueError(f"参数 {name} 类型应为 {kind}")


def resolve_inputs(definitions: list[dict], inputs: dict) -> dict:
    definitions = normalize_definitions(definitions)
    by_name = {d["name"]: d for d in definitions}
    unknown = inputs.keys() - by_name.keys()
    if unknown:
        raise ValueError("未声明的输入参数: " + ", ".join(sorted(unknown)))
    values = {
        d["name"]: d["default"] for d in definitions if d.get("default") is not None
    }
    values.update(inputs)
    for name, definition in by_name.items():
        value = values.get(name)
        if value is None:
            if definition.get("required", True):
                raise ValueError(f"缺少必填参数: {name}")
            values.pop(name, None)
            continue
        _validate_value(name, definition.get("type", "string"), value)
        if (
            definition.get("required", True)
            and isinstance(value, str)
            and not value.strip()
        ):
            raise ValueError(f"必填参数 {name} 不能为空")
    return values


def effective_start_url(start_url: str, inputs: dict) -> str:
    value = inputs.get("url")
    return (
        value.strip()
        if isinstance(value, str) and value.strip()
        else (start_url or "").strip()
    )
