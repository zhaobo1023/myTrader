# -*- coding: utf-8 -*-
"""
风控配置
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RiskConfig:
    """风控配置"""

    # 仓位限制
    single_position_limit: float = 0.10
    max_positions: int = 10

    # ATR 仓位
    atr_period: int = 14
    atr_risk_per_trade: float = 0.02
    atr_multiplier: float = 2.0

    # 熔断
    daily_max_loss_pct: float = -0.05

    # 事前检查
    order_amount_cap: float = 500_000
    price_limit_pct: float = 0.10
    st_blacklist: List[str] = field(default_factory=list)

    # 规则选择
    enabled_rules: Optional[List[str]] = None   # None = 全部启用
    advisory_mode: bool = True                   # True = REJECT 降级为 WARN
