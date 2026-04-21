# -*- coding: utf-8 -*-
"""
风控规则抽象基类
"""
from abc import ABC, abstractmethod

from .models import Decision, RiskContext, RiskDecision


class BaseRule(ABC):
    """风控规则基类，所有规则必须继承此类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """规则名称（用于配置启用/禁用）"""
        ...

    @abstractmethod
    def evaluate(self, ctx: RiskContext) -> RiskDecision:
        """
        评估规则

        Args:
            ctx: 风控上下文

        Returns:
            单条规则的评估结果
        """
        ...

    # 便捷构造方法
    def _approve(self, reason: str = "通过", max_pct: float = 1.0) -> RiskDecision:
        return RiskDecision(Decision.APPROVE, reason, self.name, max_pct)

    def _warn(self, reason: str, max_pct: float = 1.0) -> RiskDecision:
        return RiskDecision(Decision.WARN, reason, self.name, max_pct)

    def _reject(self, reason: str, max_pct: float = 0.0) -> RiskDecision:
        return RiskDecision(Decision.REJECT, reason, self.name, max_pct)

    def _halt(self, reason: str) -> RiskDecision:
        return RiskDecision(Decision.HALT, reason, self.name, 0.0)
