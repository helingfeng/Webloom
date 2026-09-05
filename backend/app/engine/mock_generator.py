from typing import Any


def generate_mock_inputs(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for variable in inputs:
        name = variable.get("name")
        var_type = variable.get("type", "string")
        default = variable.get("default")
        if default is not None:
            result[name] = default
            continue
        if var_type in ("string", "header", "cookie", "localStorage"):
            result[name] = f"mock_{name}"
        elif var_type == "secret":
            result[name] = "mock_password"
        elif var_type == "number":
            result[name] = 0
        elif var_type == "boolean":
            result[name] = False
        else:
            result[name] = ""
    return result
