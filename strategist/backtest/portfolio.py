# -*- coding: utf-8 -*-
"""
组合管理模块
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class Position:
    """持仓"""
    stock_code: str
    entry_date: datetime
    entry_price: float
    shares: float
    signal_type: str
    target_hold_days: int = 60
    stop_loss: float = -0.10
    take_profit: float = 0.20
    
    def current_value(self, current_price: float) -> float:
        """当前市值"""
        return self.shares * current_price
    
    def pnl(self, current_price: float) -> float:
        """盈亏比例"""
        return (current_price - self.entry_price) / self.entry_price
    
    def hold_days(self, current_date: datetime) -> int:
        """持仓天数"""
        return (current_date - self.entry_date).days


@dataclass
class Trade:
    """交易记录"""
    date: datetime
    stock_code: str
    action: str
    price: float
    shares: float
    amount: float
    commission: float
    signal_type: str = ''
    exit_reason: str = ''


class Portfolio:
    """组合管理器"""
    
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_records: List[Dict] = []
        
    @property
    def position_value(self) -> float:
        """持仓总市值（需要外部传入当前价格）"""
        return sum(pos.shares * 0 for pos in self.positions.values())
    
    def total_value(self, current_prices: Dict[str, float]) -> float:
        """总资产"""
        position_val = sum(
            pos.shares * current_prices.get(code, 0)
            for code, pos in self.positions.items()
        )
        return self.cash + position_val
    
    def available_cash(self) -> float:
        """可用资金"""
        return self.cash
    
    def position_count(self) -> int:
        """持仓数量"""
        return len(self.positions)
    
    def has_position(self, stock_code: str) -> bool:
        """是否持有某只股票"""
        return stock_code in self.positions
    
    def get_position(self, stock_code: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(stock_code)
    
    def calculate_position_size(
        self,
        stock_code: str,
        price: float,
        config,
        signal_weight: float = 1.0
    ) -> float:
        """
        计算仓位大小
        
        Args:
            stock_code: 股票代码
            price: 当前价格
            config: 回测配置
            signal_weight: 信号权重（0-1）
            
        Returns:
            可买入股数
        """
        if config.position_sizing == 'equal':
            # 等权重：总资金 / 最大持仓数
            target_value = self.initial_cash / config.max_positions
            # 考虑信号权重
            target_value *= signal_weight
            # 不超过单只股票仓位限制
            max_value = self.initial_cash * config.single_position_limit
            target_value = min(target_value, max_value)
            # 不超过可用资金
            target_value = min(target_value, self.cash * 0.95)
            
            shares = target_value / price
            return shares
        
        elif config.position_sizing == 'risk_parity':
            # 风险平价（简化版：根据波动率调整）
            # TODO: 需要传入波动率数据
            return self.calculate_position_size(stock_code, price, config, signal_weight)
        
        else:
            # 默认等权重
            return self.calculate_position_size(stock_code, price, config, signal_weight)
    
    def execute_buy(
        self,
        stock_code: str,
        date: datetime,
        price: float,
        shares: float,
        config,
        signal_type: str = ''
    ) -> bool:
        """
        执行买入
        
        Returns:
            是否成功
        """
        if shares <= 0:
            return False
        
        # 考虑滑点
        actual_price = price * (1 + config.slippage)
        
        # 计算成本
        amount = shares * actual_price
        commission = amount * config.commission
        total_cost = amount + commission
        
        # 检查资金是否足够
        if total_cost > self.cash:
            return False
        
        # 扣除资金
        self.cash -= total_cost
        
        # 创建持仓
        position = Position(
            stock_code=stock_code,
            entry_date=date,
            entry_price=actual_price,
            shares=shares,
            signal_type=signal_type,
            target_hold_days=config.default_hold_days,
            stop_loss=config.default_stop_loss,
            take_profit=config.default_take_profit,
        )
        self.positions[stock_code] = position
        
        # 记录交易
        trade = Trade(
            date=date,
            stock_code=stock_code,
            action='BUY',
            price=actual_price,
            shares=shares,
            amount=amount,
            commission=commission,
            signal_type=signal_type,
        )
        self.trades.append(trade)
        
        return True
    
    def execute_sell(
        self,
        stock_code: str,
        date: datetime,
        price: float,
        config,
        exit_reason: str = ''
    ) -> bool:
        """
        执行卖出
        
        Returns:
            是否成功
        """
        if stock_code not in self.positions:
            return False
        
        position = self.positions[stock_code]
        
        # 考虑滑点
        actual_price = price * (1 - config.slippage)
        
        # 计算收入
        amount = position.shares * actual_price
        commission = amount * config.commission
        stamp_tax = amount * config.stamp_tax
        total_revenue = amount - commission - stamp_tax
        
        # 增加资金
        self.cash += total_revenue
        
        # 记录交易
        trade = Trade(
            date=date,
            stock_code=stock_code,
            action='SELL',
            price=actual_price,
            shares=position.shares,
            amount=amount,
            commission=commission + stamp_tax,
            signal_type=position.signal_type,
            exit_reason=exit_reason,
        )
        self.trades.append(trade)
        
        # 删除持仓
        del self.positions[stock_code]
        
        return True
    
    def check_exit_conditions(
        self,
        stock_code: str,
        current_date: datetime,
        current_price: float,
        config
    ) -> Optional[str]:
        """
        检查退出条件
        
        Returns:
            退出原因，None表示不退出
        """
        if stock_code not in self.positions:
            return None
        
        position = self.positions[stock_code]
        
        # 计算盈亏
        pnl = position.pnl(current_price)
        
        # 止损
        if pnl <= position.stop_loss:
            return 'stop_loss'
        
        # 止盈
        if pnl >= position.take_profit:
            return 'take_profit'
        
        # 持仓到期
        hold_days = position.hold_days(current_date)
        if hold_days >= position.target_hold_days:
            return 'hold_days'
        
        return None
    
    def record_daily(
        self,
        date: datetime,
        current_prices: Dict[str, float]
    ):
        """记录每日状态"""
        position_value = sum(
            pos.shares * current_prices.get(code, 0)
            for code, pos in self.positions.items()
        )
        total_value = self.cash + position_value
        
        record = {
            'date': date,
            'cash': self.cash,
            'position_value': position_value,
            'total_value': total_value,
            'position_count': len(self.positions),
        }
        self.daily_records.append(record)
    
    def get_daily_df(self) -> pd.DataFrame:
        """获取每日记录DataFrame"""
        if not self.daily_records:
            return pd.DataFrame()
        return pd.DataFrame(self.daily_records)
    
    def get_trades_df(self) -> pd.DataFrame:
        """获取交易记录DataFrame"""
        if not self.trades:
            return pd.DataFrame()
        
        trades_data = []
        for trade in self.trades:
            trades_data.append({
                'date': trade.date,
                'stock_code': trade.stock_code,
                'action': trade.action,
                'price': trade.price,
                'shares': trade.shares,
                'amount': trade.amount,
                'commission': trade.commission,
                'signal_type': trade.signal_type,
                'exit_reason': trade.exit_reason,
            })
        return pd.DataFrame(trades_data)
