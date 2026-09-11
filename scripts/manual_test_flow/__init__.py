"""ADP 闭环验收脚本包：纯标准库实现，用于手工/自动验收前后端联通与业务闭环。

- client.py   : HTTP + 会话 + CSRF + 附件上传
- runner.py   : 断言框架与通用单据流转
- flows_*.py  : 按业务域拆分的阶段实现（混入 Runner）
- __main__.py : 命令行入口

数据前缀 MT2609-，全部为真实写库操作，测试后按前缀清理。
"""

from .client import ApiError, Client, PREFIX
from .flows import Runner

__all__ = ["ApiError", "Client", "PREFIX", "Runner"]
