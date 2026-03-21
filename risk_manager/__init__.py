# -*- coding: utf-8 -*-
"""
风控师模块

负责：
  - 持仓管理
  - 风险监控
  - 止损止盈
  - 仓位控制
"""

class RiskManager:
    """风控管理器"""

    def __init__(self, max_position_pct: float = 0.3, max_single_loss_pct: float = 0.05):
        """
        初始化风控管理器

        Args:
            max_position_pct: 单只股票最大仓位比例
            max_single_loss_pct: 单笔最大亏损比例
        """
        self.max_position_pct = max_position_pct
        self.max_single_loss_pct = max_single_loss_pct

    def check_position_limit(self, current_position: float, total_capital: float) -> bool:
        """
        检查仓位是否超限

        Args:
            current_position: 当前持仓市值
            total_capital: 总资金

        Returns:
            是否在限制范围内
        """
        position_pct = current_position / total_capital
        return position_pct <= self.max_position_pct

    def calculate_stop_loss(self, entry_price: float, stop_loss_pct: float = 0.08) -> float:
        """
        计算止损价

        Args:
            entry_price: 入场价
            stop_loss_pct: 止损比例

        Returns:
            止损价
        """
        return entry_price * (1 - stop_loss_pct)

    def calculate_take_profit(self, entry_price: float, take_profit_pct: float = 0.15) -> float:
        """
        计算止盈价

        Args:
            entry_price: 入场价
            take_profit_pct: 止盈比例

        Returns:
            止盈价
        """
        return entry_price * (1 + take_profit_pct)

    def calculate_position_size(self, total_capital: float, risk_per_trade: float = 0.02) -> float:
        """
        计算建议仓位大小

        Args:
            total_capital: 总资金
            risk_per_trade: 单笔风险比例

        Returns:
            建议仓位金额
        """
        return total_capital * min(risk_per_trade, self.max_single_loss_pct)
