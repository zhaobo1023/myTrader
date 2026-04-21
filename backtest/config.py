# -*- coding: utf-8 -*-
"""
回测配置模块
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class BacktestConfig:
    """回测配置"""

    # 资金配置
    initial_cash: float = 1_000_000

    # 交易成本
    commission: float = 0.0003
    slippage: float = 0.001
    stamp_tax: float = 0.001

    # 仓位管理
    max_positions: int = 10
    position_sizing: str = 'equal'
    single_position_limit: float = 0.1

    # 风控配置
    default_hold_days: int = 60
    default_stop_loss: float = -0.10
    default_take_profit: float = 0.20

    # 基准配置
    benchmark: Optional[str] = '000300.SH'

    # 其他配置
    allow_short: bool = False

    def validate(self):
        """验证配置合法性"""
        assert self.initial_cash > 0, "初始资金必须大于0"
        assert 0 <= self.commission <= 0.01, "手续费率应在0-1%之间"
        assert 0 <= self.slippage <= 0.01, "滑点率应在0-1%之间"
        assert 0 <= self.stamp_tax <= 0.01, "印花税率应在0-1%之间"
        assert self.max_positions > 0, "最大持仓数必须大于0"
        assert 0 < self.single_position_limit <= 1.0, "单只股票仓位限制应在0-100%之间"
        assert self.default_hold_days > 0, "持仓天数必须大于0"
        assert -1.0 <= self.default_stop_loss < 0, "止损应在-100%-0%之间"
        assert 0 < self.default_take_profit <= 10.0, "止盈应在0-1000%之间"
        assert self.position_sizing in ['equal', 'risk_parity', 'kelly'], "仓位管理方式不支持"
