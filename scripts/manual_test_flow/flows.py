"""把通用 Runner 与各业务域阶段组合成可执行的验收器。"""
from __future__ import annotations

from .flows_commerce import CommerceFlows
from .flows_finance import FinanceFlows
from .flows_production import ProductionFlows
from .runner import Runner as _BaseRunner


class Runner(ProductionFlows, CommerceFlows, FinanceFlows, _BaseRunner):
    """完整验收器：主数据/批次在基类，其余阶段按业务域混入，便于单文件保持 ≤300 行。"""


__all__ = ["Runner"]
