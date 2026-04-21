# -*- coding: utf-8 -*-
"""
7 条内置风控规则
"""
from typing import Optional

import pandas as pd

from .atr import calc_atr
from .base import BaseRule
from .config import RiskConfig
from .models import RiskContext, RiskDecision


class ConcentrationLimit(BaseRule):
    """持仓集中度：持仓数达上限则 REJECT"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "concentration_limit"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        if ctx.position_count >= self.config.max_positions:
            return self._reject(
                f"持仓数 {ctx.position_count} 已达上限 {self.config.max_positions}"
            )
        return self._approve()


class STBlacklist(BaseRule):
    """ST 黑名单：检测 ST 股"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "st_blacklist"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        code = ctx.stock_code.upper()

        # 检查显式黑名单
        if code in self.config.st_blacklist:
            return self._reject(f"{code} 在 ST 黑名单中")

        # 通过股票名称检测 ST/*ST
        if ctx.stock_name and 'ST' in ctx.stock_name.upper():
            return self._reject(f"{ctx.stock_name} 为 ST 股")

        return self._approve()


class PriceLimitGuard(BaseRule):
    """涨跌停检测：接近涨跌停板时 WARN"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "price_limit_guard"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        if ctx.ohlcv_history is None or len(ctx.ohlcv_history) < 2:
            return self._approve()

        prev_close = ctx.ohlcv_history['close'].iloc[-2]
        if prev_close <= 0:
            return self._approve()

        change_pct = (ctx.price - prev_close) / prev_close
        limit = self.config.price_limit_pct

        if abs(change_pct) >= limit * 0.98:
            direction = "涨停" if change_pct > 0 else "跌停"
            return self._warn(
                f"价格变动 {change_pct:.2%} 接近{direction}板 ({limit:.0%})"
            )

        return self._approve()


class OrderAmountCap(BaseRule):
    """单笔金额上限：预估下单金额超限 WARN"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "order_amount_cap"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        if ctx.order_amount > self.config.order_amount_cap:
            return self._warn(
                f"预估下单金额 {ctx.order_amount:,.0f} "
                f"超过上限 {self.config.order_amount_cap:,.0f}"
            )
        return self._approve()


class ATRPositionScaler(BaseRule):
    """ATR 仓位缩放：高波动自动降仓位"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "atr_position_scaler"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        if ctx.ohlcv_history is None or len(ctx.ohlcv_history) < self.config.atr_period:
            return self._approve()

        atr_series = calc_atr(ctx.ohlcv_history, self.config.atr_period)
        current_atr = atr_series.iloc[-1]

        if pd.isna(current_atr) or current_atr <= 0 or ctx.price <= 0:
            return self._approve()

        # ATR 占价格的比例
        atr_pct = current_atr / ctx.price

        # 基于风险预算反算建议仓位比例
        # risk_per_trade / (atr_pct * multiplier) 即为建议仓位占组合比例
        risk_budget = self.config.atr_risk_per_trade
        stop_risk = atr_pct * self.config.atr_multiplier

        if stop_risk <= 0:
            return self._approve()

        suggested_pct = min(risk_budget / stop_risk, 1.0)

        if suggested_pct < 0.5:
            return self._warn(
                f"ATR 偏高 ({atr_pct:.2%}), 建议仓位缩减至 {suggested_pct:.0%}",
                max_pct=suggested_pct,
            )
        elif suggested_pct < 1.0:
            return self._approve(
                f"ATR 正常 ({atr_pct:.2%}), 建议仓位 {suggested_pct:.0%}",
                max_pct=suggested_pct,
            )
        return self._approve()


class DailyLossCircuitBreaker(BaseRule):
    """当日亏损熔断：日亏超阈值 HALT"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "daily_loss_circuit_breaker"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        if ctx.portfolio_value <= 0:
            return self._approve()

        if ctx.daily_pnl_pct <= self.config.daily_max_loss_pct:
            return self._halt(
                f"当日亏损 {ctx.daily_pnl_pct:.2%} "
                f"触发熔断阈值 {self.config.daily_max_loss_pct:.2%}"
            )
        return self._approve()


class SinglePositionLimit(BaseRule):
    """单只仓位限制：单股仓位上限检查"""

    def __init__(self, config: RiskConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "single_position_limit"

    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        if ctx.portfolio_value <= 0:
            return self._approve()

        # 检查新买入后该股票占组合比例
        existing_value = ctx.current_positions.get(ctx.stock_code, 0.0)
        total_value = existing_value + ctx.order_amount
        position_pct = total_value / ctx.portfolio_value

        if position_pct > self.config.single_position_limit:
            return self._reject(
                f"{ctx.stock_code} 仓位 {position_pct:.1%} "
                f"超过上限 {self.config.single_position_limit:.0%}",
                max_pct=self.config.single_position_limit,
            )
        return self._approve()


# 所有内置规则的注册表
ALL_RULES = [
    ConcentrationLimit,
    STBlacklist,
    PriceLimitGuard,
    OrderAmountCap,
    ATRPositionScaler,
    DailyLossCircuitBreaker,
    SinglePositionLimit,
]
