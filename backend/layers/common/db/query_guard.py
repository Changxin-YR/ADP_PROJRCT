"""SQL 动态标识符与查询组装的安全工具。

本项目动态 SQL 只允许两类内容进入查询文本：
1. 表名/列名：必须来自代码内固定白名单（SPECS、EXPORT_QUERIES 等），并经过 sql_identifier 校验；
2. 查询值：一律使用 %s 参数绑定，绝不拼接用户输入。
新增动态 SQL 时必须遵守以上约定。
"""
from __future__ import annotations

import re

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def sql_identifier(name: str) -> str:
    """校验表名/列名是合法 SQL 标识符，防止白名单被误改成注入点。"""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"非法 SQL 标识符: {name!r}")
    return name


def select_from(table: str, *, columns: str = "*", suffix: str = "") -> str:
    """按固定表名组装 SELECT，避免各处重复拼 f-string。"""
    return f"SELECT {columns} FROM {sql_identifier(table)}{suffix}"
