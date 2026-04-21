# -*- coding: utf-8 -*-
"""
风控决策模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional

import pandas as pd


class Decision(IntEnum):
    """风控决策等级（数值越大越严重）"""
    APPROVE = 0
    WARN = 1
    REJECT = 2
    HALT = 3


@dataclass
class RiskDecision:
    """单条规则的评估结果"""
    decision: Decision
    reason: str
    rule_name: str
    max_position_pct: float = 1.0  # 建议的最大仓位比例 (0-1)

    @property
    def approved(self) -> bool:
        return self.decision <= Decision.WARN

    def __str__(self) -> str:
        return f"[{self.decision.name}] {self.rule_name}: {self.reason}"


@dataclass
class RiskContext:
    """规则评估的统一输入上下文"""
    stock_code: str
    price: float
    date: Optional[datetime] = None
    stock_name: str = ''  # 股票名称（用于 ST 检测等）

    # 组合信息
    portfolio_value: float = 0.0
    cash: float = 0.0
    current_positions: Dict[str, float] = field(default_factory=dict)  # {code: market_value}
    position_count: int = 0
    max_positions: int = 10

    # 当日盈亏
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0

    # OHLCV 历史数据（用于 ATR 等计算）
    ohlcv_history: Optional[pd.DataFrame] = None

    # 相关性矩阵（可选，用于组合相关性风控）
    correlation_matrix: Optional[pd.DataFrame] = None

    # 下单信息
    order_amount: float = 0.0       # 预估下单金额
    signal_weight: float = 1.0


@dataclass
class AggregatedDecision:
    """多规则聚合结果"""
    decisions: List[RiskDecision] = field(default_factory=list)
    final_decision: Decision = Decision.APPROVE
    suggested_position_pct: float = 1.0

    @property
    def approved(self) -> bool:
        return self.final_decision <= Decision.WARN

    def summary(self) -> str:
        """输出可读报告"""
        lines = [f"=== 风控评估结果: {self.final_decision.name} ==="]
        lines.append(f"建议仓位比例: {self.suggested_position_pct:.0%}")
        lines.append("")
        for d in self.decisions:
            marker = "  " if d.decision == Decision.APPROVE else ">>"
            lines.append(f"{marker} {d}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary()
