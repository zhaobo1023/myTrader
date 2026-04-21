# -*- coding: utf-8 -*-
"""
通知/报告抽象接口（预留）
"""
from abc import ABC

from .models import AggregatedDecision, RiskContext


class RiskHook(ABC):
    """风控事件钩子基类"""

    def on_decision(self, ctx: RiskContext, decision: AggregatedDecision):
        """每次评估后调用"""
        pass

    def on_warning(self, ctx: RiskContext, decision: AggregatedDecision):
        """有警告时调用"""
        pass

    def on_rejection(self, ctx: RiskContext, decision: AggregatedDecision):
        """被拒绝时调用"""
        pass

    def on_daily_summary(self, date, summary: str):
        """每日汇总"""
        pass

    def on_session_end(self, summary: str):
        """回测/会话结束"""
        pass


class LoggingHook(RiskHook):
    """内置日志钩子，打印到 stdout"""

    def on_warning(self, ctx: RiskContext, decision: AggregatedDecision):
        print(f"[风控警告] {ctx.stock_code} @ {ctx.price}: "
              f"{decision.final_decision.name}")
        for d in decision.decisions:
            if d.decision.value >= 1:
                print(f"  - {d}")

    def on_rejection(self, ctx: RiskContext, decision: AggregatedDecision):
        print(f"[风控拒绝] {ctx.stock_code} @ {ctx.price}: "
              f"{decision.final_decision.name}")
        for d in decision.decisions:
            if d.decision.value >= 2:
                print(f"  - {d}")
