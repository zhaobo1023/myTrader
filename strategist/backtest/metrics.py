# -*- coding: utf-8 -*-
"""
回测指标计算模块
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd
import numpy as np


@dataclass
class BacktestResult:
    """回测结果"""
    
    # 基本信息
    start_date: str = ''
    end_date: str = ''
    trading_days: int = 0
    
    # 资金信息
    initial_cash: float = 0
    final_value: float = 0
    
    # 收益指标
    total_return: float = 0
    annual_return: float = 0
    benchmark_return: float = 0
    benchmark_annual: float = 0
    excess_return: float = 0
    
    # 风险指标
    max_drawdown: float = 0
    volatility: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    
    # 交易指标
    total_trades: int = 0
    win_trades: int = 0
    lose_trades: int = 0
    win_rate: float = 0
    avg_return_per_trade: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_loss_ratio: float = 0
    avg_hold_days: float = 0
    
    # 分类统计
    momentum_stats: Dict = field(default_factory=dict)
    reversal_stats: Dict = field(default_factory=dict)
    
    # 原始数据
    daily_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    trades_df: pd.DataFrame = field(default_factory=pd.DataFrame)


class MetricsCalculator:
    """指标计算器"""
    
    def __init__(self):
        self.daily_records: List[Dict] = []
        
    def record_daily(self, date, portfolio):
        """记录每日数据（由引擎调用）"""
        pass
    
    def calculate(
        self,
        daily_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        initial_cash: float,
        benchmark_df: Optional[pd.DataFrame] = None
    ) -> BacktestResult:
        """
        计算回测指标
        
        Args:
            daily_df: 每日净值DataFrame，包含 [date, total_value]
            trades_df: 交易记录DataFrame
            initial_cash: 初始资金
            benchmark_df: 基准数据，包含 [date, close]
        """
        if len(daily_df) == 0:
            return BacktestResult()
        
        # 确保日期索引
        if 'date' in daily_df.columns:
            daily_df = daily_df.set_index('date')
        
        # 基本信息
        start_date = daily_df.index[0]
        end_date = daily_df.index[-1]
        trading_days = len(daily_df)
        
        # 资金信息
        final_value = daily_df['total_value'].iloc[-1]
        
        # 计算收益率
        daily_df = daily_df.copy()
        daily_df['return'] = daily_df['total_value'].pct_change()
        daily_df['cum_return'] = (1 + daily_df['return']).cumprod() - 1
        
        # 收益指标
        total_return = (final_value - initial_cash) / initial_cash
        annual_return = self._calculate_annual_return(total_return, trading_days)
        
        # 基准收益
        benchmark_return = 0
        benchmark_annual = 0
        if benchmark_df is not None and len(benchmark_df) > 0:
            benchmark_return, benchmark_annual = self._calculate_benchmark_return(
                benchmark_df, daily_df.index, trading_days
            )
        
        excess_return = total_return - benchmark_return
        
        # 风险指标
        max_drawdown = self._calculate_max_drawdown(daily_df['total_value'])
        volatility = daily_df['return'].std() * np.sqrt(252)
        sharpe_ratio = self._calculate_sharpe_ratio(daily_df['return'], annual_return)
        sortino_ratio = self._calculate_sortino_ratio(daily_df['return'], annual_return)
        calmar_ratio = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        # 交易指标
        trade_stats = self._calculate_trade_stats(trades_df)
        
        # 分类统计
        momentum_stats = self._calculate_signal_stats(trades_df, 'momentum')
        reversal_stats = self._calculate_signal_stats(trades_df, 'reversal')
        
        return BacktestResult(
            start_date=str(start_date.date()) if hasattr(start_date, 'date') else str(start_date),
            end_date=str(end_date.date()) if hasattr(end_date, 'date') else str(end_date),
            trading_days=trading_days,
            initial_cash=initial_cash,
            final_value=final_value,
            total_return=total_return,
            annual_return=annual_return,
            benchmark_return=benchmark_return,
            benchmark_annual=benchmark_annual,
            excess_return=excess_return,
            max_drawdown=max_drawdown,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            **trade_stats,
            momentum_stats=momentum_stats,
            reversal_stats=reversal_stats,
            daily_df=daily_df,
            trades_df=trades_df,
        )
    
    def _calculate_annual_return(self, total_return: float, trading_days: int) -> float:
        """计算年化收益率"""
        if trading_days <= 0:
            return 0
        return (1 + total_return) ** (252 / trading_days) - 1
    
    def _calculate_benchmark_return(
        self,
        benchmark_df: pd.DataFrame,
        dates: pd.DatetimeIndex,
        trading_days: int
    ) -> tuple:
        """计算基准收益"""
        if len(benchmark_df) == 0:
            return 0, 0
        
        # 对齐日期
        if 'date' in benchmark_df.columns:
            benchmark_df = benchmark_df.set_index('date')
        
        # 找到起始和结束价格
        start_price = benchmark_df.loc[dates[0], 'close'] if dates[0] in benchmark_df.index else None
        end_price = benchmark_df.loc[dates[-1], 'close'] if dates[-1] in benchmark_df.index else None
        
        if start_price is None or end_price is None:
            return 0, 0
        
        benchmark_return = (end_price - start_price) / start_price
        benchmark_annual = self._calculate_annual_return(benchmark_return, trading_days)
        
        return benchmark_return, benchmark_annual
    
    def _calculate_max_drawdown(self, values: pd.Series) -> float:
        """计算最大回撤"""
        peak = values.expanding(min_periods=1).max()
        drawdown = (values - peak) / peak
        return drawdown.min()
    
    def _calculate_sharpe_ratio(self, returns: pd.Series, annual_return: float) -> float:
        """计算夏普比率"""
        if len(returns) < 2:
            return 0
        
        # 假设无风险利率为3%
        risk_free_rate = 0.03
        excess_return = annual_return - risk_free_rate
        volatility = returns.std() * np.sqrt(252)
        
        if volatility == 0:
            return 0
        
        return excess_return / volatility
    
    def _calculate_sortino_ratio(self, returns: pd.Series, annual_return: float) -> float:
        """计算索提诺比率（只考虑下行波动）"""
        if len(returns) < 2:
            return 0
        
        risk_free_rate = 0.03
        excess_return = annual_return - risk_free_rate
        
        # 下行标准差
        downside_returns = returns[returns < 0]
        if len(downside_returns) == 0:
            return 0
        
        downside_std = downside_returns.std() * np.sqrt(252)
        
        if downside_std == 0:
            return 0
        
        return excess_return / downside_std
    
    def _calculate_trade_stats(self, trades_df: pd.DataFrame) -> Dict:
        """计算交易统计"""
        if len(trades_df) == 0:
            return {
                'total_trades': 0,
                'win_trades': 0,
                'lose_trades': 0,
                'win_rate': 0,
                'avg_return_per_trade': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_loss_ratio': 0,
                'avg_hold_days': 0,
            }
        
        # 配对买卖交易
        buy_trades = trades_df[trades_df['action'] == 'BUY'].copy()
        sell_trades = trades_df[trades_df['action'] == 'SELL'].copy()
        
        # 计算每笔交易的收益
        trade_returns = []
        hold_days_list = []
        
        for _, sell in sell_trades.iterrows():
            # 找到对应的买入
            buy = buy_trades[buy_trades['stock_code'] == sell['stock_code']]
            if len(buy) > 0:
                buy = buy.iloc[-1]  # 取最后一次买入
                trade_return = (sell['price'] - buy['price']) / buy['price']
                trade_returns.append(trade_return)
                
                # 计算持仓天数
                hold_days = (sell['date'] - buy['date']).days
                hold_days_list.append(hold_days)
        
        if len(trade_returns) == 0:
            return {
                'total_trades': 0,
                'win_trades': 0,
                'lose_trades': 0,
                'win_rate': 0,
                'avg_return_per_trade': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_loss_ratio': 0,
                'avg_hold_days': 0,
            }
        
        trade_returns = np.array(trade_returns)
        win_trades = (trade_returns > 0).sum()
        lose_trades = (trade_returns <= 0).sum()
        total_trades = len(trade_returns)
        
        win_rate = win_trades / total_trades if total_trades > 0 else 0
        avg_return = trade_returns.mean()
        
        avg_win = trade_returns[trade_returns > 0].mean() if win_trades > 0 else 0
        avg_loss = trade_returns[trade_returns <= 0].mean() if lose_trades > 0 else 0
        profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        avg_hold_days = np.mean(hold_days_list) if hold_days_list else 0
        
        return {
            'total_trades': total_trades,
            'win_trades': int(win_trades),
            'lose_trades': int(lose_trades),
            'win_rate': win_rate,
            'avg_return_per_trade': avg_return,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_loss_ratio': profit_loss_ratio,
            'avg_hold_days': avg_hold_days,
        }
    
    def _calculate_signal_stats(self, trades_df: pd.DataFrame, signal_type: str) -> Dict:
        """计算特定信号类型的统计"""
        if len(trades_df) == 0:
            return {}
        
        signal_trades = trades_df[trades_df['signal_type'] == signal_type]
        
        if len(signal_trades) == 0:
            return {}
        
        # 只看卖出交易
        sell_trades = signal_trades[signal_trades['action'] == 'SELL']
        buy_trades = trades_df[trades_df['action'] == 'BUY']
        
        trade_returns = []
        for _, sell in sell_trades.iterrows():
            buy = buy_trades[buy_trades['stock_code'] == sell['stock_code']]
            if len(buy) > 0:
                buy = buy.iloc[-1]
                trade_return = (sell['price'] - buy['price']) / buy['price']
                trade_returns.append(trade_return)
        
        if len(trade_returns) == 0:
            return {}
        
        trade_returns = np.array(trade_returns)
        
        return {
            'count': len(trade_returns),
            'win_rate': (trade_returns > 0).sum() / len(trade_returns),
            'avg_return': trade_returns.mean(),
            'max_return': trade_returns.max(),
            'min_return': trade_returns.min(),
        }
