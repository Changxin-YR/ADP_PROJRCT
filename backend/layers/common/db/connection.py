from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

import pymysql
from pymysql.connections import Connection

from backend.config.settings import Settings


@dataclass
class _RequestConnectionState:
    connection: Connection | None = None
    settings_key: tuple[object, ...] | None = None


_request_state: ContextVar[_RequestConnectionState | None] = ContextVar(
    "adp_request_connection_state", default=None
)


def begin_request_connection_scope() -> None:
    _request_state.set(_RequestConnectionState())


def end_request_connection_scope(*, rollback: bool = False) -> None:
    state = _request_state.get()
    _request_state.set(None)
    if state is None or state.connection is None:
        return
    try:
        if rollback:
            state.connection.rollback()
    finally:
        state.connection.close()


def _settings_key(settings: Settings) -> tuple[object, ...]:
    return (
        settings.mysql_host,
        settings.mysql_port,
        settings.mysql_database,
        settings.mysql_user,
        settings.mysql_password,
    )


def _connect(settings: Settings) -> Connection:
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


@contextmanager
def get_connection(settings: Settings | None = None) -> Iterator[Connection]:
    """建立一个事务连接；成功提交，异常回滚，最后总是关闭连接。"""
    resolved = settings or Settings.from_env()
    state = _request_state.get()
    request_scoped = state is not None
    key = _settings_key(resolved)
    if state is not None:
        if state.connection is None:
            state.connection = _connect(resolved)
            state.settings_key = key
        elif state.settings_key != key:
            raise RuntimeError("同一 HTTP 请求不能跨数据库复用连接")
        connection = state.connection
    else:
        connection = _connect(resolved)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if not request_scoped:
            connection.close()


transaction = get_connection
