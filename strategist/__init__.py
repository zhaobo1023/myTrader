# -*- coding: utf-8 -*-
"""
策略师模块

负责：
  - 交易策略实现
  - 策略回测
  - 信号生成
"""

class BaseStrategy:
    """策略基类"""

    def __init__(self, name: str):
        self.name = name

    def generate_signals(self, data):
        """
        生成交易信号

        Args:
            data: 包含行情和技术指标的DataFrame

        Returns:
            信号列表: [{'date': ..., 'action': 'buy/sell', 'price': ..., 'reason': ...}]
        """
        raise NotImplementedError("子类必须实现 generate_signals 方法")

    def backtest(self, data, initial_cash=1000000, commission=0.0002):
        """
        回测策略

        Args:
            data: 行情数据
            initial_cash: 初始资金
            commission: 手续费率

        Returns:
            回测结果
        """
        raise NotImplementedError("子类必须实现 backtest 方法")
