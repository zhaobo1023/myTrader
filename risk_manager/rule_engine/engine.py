# -*- coding: utf-8 -*-
"""
风控引擎 - 双模式核心
"""
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from .audit import AuditLog
from .base import BaseRule
from .config import RiskConfig
from .hooks import RiskHook
from .models import AggregatedDecision, Decision, RiskContext, RiskDecision
from .rules import ALL_RULES


class RiskEngine:
    """
    风控引擎

    支持两种模式:
    - 独立模式: 直接调用 check_stock() 获取决策建议
    - 回测模式: 通过 build_context_from_portfolio() + evaluate() 嵌入回测引擎
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self.rules: List[BaseRule] = []
        self.hooks: List[RiskHook] = []
        self.audit = AuditLog()

        # 初始化内置规则
        self._init_builtin_rules()

    def _init_builtin_rules(self):
        """初始化内置规则（根据 enabled_rules 过滤）"""
        for rule_cls in ALL_RULES:
            rule = rule_cls(self.config)
            if self.config.enabled_rules is None or rule.name in self.config.enabled_rules:
                self.rules.append(rule)

    def add_rule(self, rule: BaseRule):
        """注册自定义规则"""
        self.rules.append(rule)

    def add_hook(self, hook: RiskHook):
        """注册通知钩子"""
        self.hooks.append(hook)

    def evaluate(self, ctx: RiskContext) -> AggregatedDecision:
        """
        执行所有规则评估并聚合结果

        一票否决: final_decision = max(所有规则)
        仓位缩放: suggested_position_pct = min(所有 max_pct)
        advisory_mode: REJECT 降级为 WARN
        """
        decisions: List[RiskDecision] = []

        for rule in self.rules:
            decision = rule.evaluate(ctx)

            # advisory_mode: REJECT 降级为 WARN（HALT 不降级，熔断必须强制执行）
            if self.config.advisory_mode and decision.decision == Decision.REJECT:
                decision = RiskDecision(
                    decision=Decision.WARN,
                    reason=f"[advisory] {decision.reason}",
                    rule_name=decision.rule_name,
                    max_position_pct=decision.max_position_pct,
                )

            decisions.append(decision)

        # 聚合
        final_decision = max((d.decision for d in decisions), default=Decision.APPROVE)
        suggested_pct = min((d.max_position_pct for d in decisions), default=1.0)

        agg = AggregatedDecision(
            decisions=decisions,
            final_decision=final_decision,
            suggested_position_pct=max(suggested_pct, 0.0),
        )

        # 审计记录
        self.audit.record(ctx, agg)

        # 触发钩子
        self._fire_hooks(ctx, agg)

        return agg

    def check_stock(
        self,
        stock_code: str,
        price: float,
        ohlcv_history: Optional[pd.DataFrame] = None,
        portfolio_value: float = 1_000_000,
        cash: float = 1_000_000,
        current_positions: Optional[Dict[str, float]] = None,
        position_count: int = 0,
        daily_pnl_pct: float = 0.0,
        order_amount: Optional[float] = None,
    ) -> AggregatedDecision:
        """
        独立模式: 快速检查单只股票

        Args:
            stock_code: 股票代码
            price: 当前价格
            ohlcv_history: OHLCV 历史数据
            portfolio_value: 组合总价值
            cash: 可用资金
            current_positions: 当前持仓 {code: market_value}
            position_count: 当前持仓数
            daily_pnl_pct: 当日盈亏比例
            order_amount: 预估下单金额（不传则按等权计算）

        Returns:
            聚合决策结果
        """
        if order_amount is None:
            order_amount = portfolio_value / self.config.max_positions

        ctx = RiskContext(
            stock_code=stock_code,
            price=price,
            date=datetime.now(),
            portfolio_value=portfolio_value,
            cash=cash,
            current_positions=current_positions or {},
            position_count=position_count,
            max_positions=self.config.max_positions,
            daily_pnl_pct=daily_pnl_pct,
            ohlcv_history=ohlcv_history,
            order_amount=order_amount,
        )

        return self.evaluate(ctx)

    def build_context_from_portfolio(
        self,
        stock_code: str,
        price: float,
        date: datetime,
        portfolio,
        current_prices: Dict[str, float],
        ohlcv_df: Optional[pd.DataFrame] = None,
        signal_weight: float = 1.0,
    ) -> RiskContext:
        """
        回测模式: 从 Portfolio 对象构建 RiskContext

        Args:
            stock_code: 待买入的股票代码
            price: 当前价格
            date: 当前日期
            portfolio: backtest.Portfolio 实例
            current_prices: 当日所有股票价格
            ohlcv_df: 该股票的 OHLCV 历史
            signal_weight: 信号权重
        """
        portfolio_value = portfolio.total_value(current_prices)

        # 构建当前持仓市值字典
        positions_value = {}
        for code, pos in portfolio.positions.items():
            p = current_prices.get(code, 0)
            positions_value[code] = pos.shares * p

        # 计算当日盈亏
        daily_pnl = 0.0
        daily_pnl_pct = 0.0
        if portfolio.daily_records:
            prev_value = portfolio.daily_records[-1].get('total_value', portfolio_value)
            if prev_value > 0:
                daily_pnl = portfolio_value - prev_value
                daily_pnl_pct = daily_pnl / prev_value

        # 预估下单金额
        order_amount = (portfolio.initial_cash / self.config.max_positions) * signal_weight

        return RiskContext(
            stock_code=stock_code,
            price=price,
            date=date,
            portfolio_value=portfolio_value,
            cash=portfolio.cash,
            current_positions=positions_value,
            position_count=portfolio.position_count(),
            max_positions=self.config.max_positions,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            ohlcv_history=ohlcv_df,
            order_amount=order_amount,
            signal_weight=signal_weight,
        )

    def _fire_hooks(self, ctx: RiskContext, agg: AggregatedDecision):
        """触发钩子事件"""
        for hook in self.hooks:
            hook.on_decision(ctx, agg)
            if agg.final_decision == Decision.WARN:
                hook.on_warning(ctx, agg)
            elif agg.final_decision >= Decision.REJECT:
                hook.on_rejection(ctx, agg)
