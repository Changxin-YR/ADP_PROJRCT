"""智能体网关错误：统一 code/message/status/data 四个字段，供 HTTP 层翻译。"""

from __future__ import annotations

from typing import Any


class AgentGatewayError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.data = data
