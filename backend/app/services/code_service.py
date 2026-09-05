"""脚本代码片段的语法校验与格式化。

用户代码片段为"顶层 await 风格"，执行时会被整体缩进嵌入 runner.py
的 async main() 内，因此校验/格式化前先 wrap 成 async 函数，
错误行号再减 1 映射回用户代码。
"""

import ast
import re
import textwrap

import black
import sqlglot
from sqlglot.errors import SqlglotError

from app.schemas.code import CodeError, CodeValidateResult


def _wrap(code: str) -> str:
    return "async def _wrapper():\n" + textwrap.indent(code, "    ")


def _unwrap(formatted: str) -> str:
    lines = formatted.splitlines()
    body = lines[1:] if lines else []
    return textwrap.dedent("\n".join(body)).rstrip("\n")


def validate_code(code: str) -> CodeValidateResult:
    if not code.strip():
        return CodeValidateResult(ok=True)
    try:
        ast.parse(_wrap(code))
        return CodeValidateResult(ok=True)
    except SyntaxError as exc:
        # wrap 首行占 1 行，减 1 映射回用户代码
        line = max((exc.lineno or 1) - 1, 1)
        return CodeValidateResult(
            ok=False,
            errors=[
                CodeError(
                    line=line,
                    column=max(exc.offset or 0, 1),
                    message=exc.msg,
                )
            ],
        )


def format_code(code: str) -> str:
    """格式化成功返回新代码；失败抛 ValueError（消息可直接展示给用户）"""
    if not code.strip():
        return code
    try:
        formatted = black.format_str(_wrap(code), mode=black.Mode())
    except Exception as exc:
        raise ValueError(f"格式化失败，请先修复语法错误：{exc}") from exc
    return _unwrap(formatted)


def validate_sql(sql: str) -> CodeValidateResult:
    """SQL 语法校验（静态解析，不执行），MySQL 方言"""
    if not sql.strip():
        return CodeValidateResult(ok=True)
    try:
        sqlglot.parse(sql, read="mysql", error_level=sqlglot.ErrorLevel.RAISE)
        return CodeValidateResult(ok=True)
    except SqlglotError as exc:
        errors = [
            CodeError(
                line=max(e.get("line") or 1, 1),
                column=max(e.get("col") or 1, 1),
                message=e.get("description") or str(exc),
            )
            for e in (exc.errors or [])
        ]
        if not errors:
            errors = [CodeError(line=1, column=1, message=str(exc))]
        return CodeValidateResult(ok=False, errors=errors)


def format_sql(sql: str) -> str:
    """SQL 格式化（MySQL 方言，大写关键字 + 换行缩进）；失败抛 ValueError"""
    if not sql.strip():
        return sql
    try:
        statements = sqlglot.transpile(sql, read="mysql", write="mysql", pretty=True)
    except SqlglotError as exc:
        # 去掉 ANSI 高亮码与源码上下文，仅保留首行描述（含行列号）
        message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).splitlines()[0]
        raise ValueError(f"格式化失败，请先修复语法错误：{message}") from exc
    statements = [s for s in statements if s.strip()]
    if not statements:
        return sql
    formatted = ";\n".join(statements)
    if sql.rstrip().endswith(";"):
        formatted += ";"
    return formatted
