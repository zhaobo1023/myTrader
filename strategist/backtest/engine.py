# -*- coding: utf-8 -*-
"""
回测引擎模块
"""
from typing import Dict, Optional
import pandas as pd
from datetime import datetime

from .config import BacktestConfig
from .portfolio import Portfolio
from .metrics import MetricsCalculator, BacktestResult


class BacktestEngine:
    """通用回测引擎"""
    
    def __init__(self, config: BacktestConfig):
        """
        初始化回测引擎
        
        Args:
            config: 回测配置
        """
        config.validate()
        self.config = config
        self.portfolio = Portfolio(config.initial_cash)
        self.metrics_calculator = MetricsCalculator()
        
    def run(
        self,
        signals: pd.DataFrame,
        price_data: Dict[str, pd.DataFrame],
        benchmark_data: Optional[pd.DataFrame] = None
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            signals: 信号DataFrame，必须包含列：
                - date: 信号日期
                - stock_code: 股票代码
                - signal_type: 信号类型（momentum/reversal等）
                - weight: 可选，信号权重（0-1），默认1.0
            price_data: 价格数据字典，{stock_code: DataFrame}
                每个DataFrame必须包含：trade_date, open, close
            benchmark_data: 基准数据，包含 date, close
        
        Returns:
            回测结果
        """
        print("=" * 60)
        print("开始回测")
        print("=" * 60)
        print(f"初始资金: {self.config.initial_cash:,.0f}")
        print(f"最大持仓数: {self.config.max_positions}")
        print(f"手续费率: {self.config.commission*100:.3f}%")
        print(f"滑点率: {self.config.slippage*100:.3f}%")
        print(f"印花税率: {self.config.stamp_tax*100:.3f}%")
        
        # 验证信号数据
        required_cols = ['date', 'stock_code', 'signal_type']
        for col in required_cols:
            if col not in signals.columns:
                raise ValueError(f"信号DataFrame缺少必需列: {col}")
        
        # 添加默认权重
        if 'weight' not in signals.columns:
            signals = signals.copy()
            signals['weight'] = 1.0
        
        # 确保日期格式
        signals = signals.copy()
        signals['date'] = pd.to_datetime(signals['date'])
        
        # 准备价格数据索引
        price_data_indexed = {}
        for code, df in price_data.items():
            df = df.copy()
            if 'trade_date' in df.columns:
                df['date'] = pd.to_datetime(df['trade_date'])
                df = df.set_index('date')
            price_data_indexed[code] = df
        
        # 获取所有交易日期
        all_dates = set()
        for df in price_data_indexed.values():
            all_dates.update(df.index)
        all_dates = sorted(list(all_dates))
        
        print(f"\n信号数量: {len(signals)}")
        print(f"交易日期范围: {all_dates[0].date()} ~ {all_dates[-1].date()}")
        print(f"交易天数: {len(all_dates)}")
        
        # 按日期遍历
        print("\n开始逐日回测...")
        for i, date in enumerate(all_dates):
            if (i + 1) % 50 == 0:
                print(f"  进度: {i+1}/{len(all_dates)}")
            
            # 1. 获取当日价格
            current_prices = {}
            for code, df in price_data_indexed.items():
                if date in df.index:
                    current_prices[code] = float(df.loc[date, 'close'])
            
            # 2. 检查并执行退出
            self._process_exits(date, current_prices, price_data_indexed)
            
            # 3. 处理当日信号
            day_signals = signals[signals['date'] == date]
            if len(day_signals) > 0:
                self._process_entries(date, day_signals, current_prices, price_data_indexed)
            
            # 4. 记录每日状态
            self.portfolio.record_daily(date, current_prices)
        
        print(f"  完成: {len(all_dates)}/{len(all_dates)}")
        
        # 计算回测指标
        print("\n计算回测指标...")
        daily_df = self.portfolio.get_daily_df()
        trades_df = self.portfolio.get_trades_df()
        
        result = self.metrics_calculator.calculate(
            daily_df=daily_df,
            trades_df=trades_df,
            initial_cash=self.config.initial_cash,
            benchmark_df=benchmark_data
        )
        
        # 打印结果摘要
        self._print_summary(result)
        
        return result
    
    def _process_exits(
        self,
        date: datetime,
        current_prices: Dict[str, float],
        price_data: Dict[str, pd.DataFrame]
    ):
        """处理退出信号"""
        # 获取当前持仓列表（复制，避免迭代时修改）
        positions_to_check = list(self.portfolio.positions.keys())
        
        for stock_code in positions_to_check:
            if stock_code not in current_prices:
                continue
            
            current_price = current_prices[stock_code]
            
            # 检查退出条件
            exit_reason = self.portfolio.check_exit_conditions(
                stock_code=stock_code,
                current_date=date,
                current_price=current_price,
                config=self.config
            )
            
            if exit_reason:
                # 执行卖出
                self.portfolio.execute_sell(
                    stock_code=stock_code,
                    date=date,
                    price=current_price,
                    config=self.config,
                    exit_reason=exit_reason
                )
    
    def _process_entries(
        self,
        date: datetime,
        day_signals: pd.DataFrame,
        current_prices: Dict[str, float],
        price_data: Dict[str, pd.DataFrame]
    ):
        """处理入场信号"""
        # 检查是否还能开新仓
        if self.portfolio.position_count() >= self.config.max_positions:
            return
        
        # 按信号权重排序（高权重优先）
        day_signals = day_signals.sort_values('weight', ascending=False)
        
        for _, signal in day_signals.iterrows():
            stock_code = signal['stock_code']
            signal_type = signal['signal_type']
            weight = signal['weight']
            
            # 检查是否已持仓
            if self.portfolio.has_position(stock_code):
                continue
            
            # 检查是否达到最大持仓数
            if self.portfolio.position_count() >= self.config.max_positions:
                break
            
            # 获取价格（使用下一个交易日的开盘价）
            # 简化处理：使用当日收盘价
            if stock_code not in current_prices:
                continue
            
            price = current_prices[stock_code]
            
            # 计算仓位大小
            shares = self.portfolio.calculate_position_size(
                stock_code=stock_code,
                price=price,
                config=self.config,
                signal_weight=weight
            )
            
            if shares <= 0:
                continue
            
            # 执行买入
            success = self.portfolio.execute_buy(
                stock_code=stock_code,
                date=date,
                price=price,
                shares=shares,
                config=self.config,
                signal_type=signal_type
            )
            
            if not success:
                continue
    
    def _print_summary(self, result: BacktestResult):
        """打印回测结果摘要"""
        print("\n" + "=" * 60)
        print("回测结果")
        print("=" * 60)
        
        print(f"\n回测区间: {result.start_date} ~ {result.end_date}")
        print(f"交易天数: {result.trading_days}")
        
        print(f"\n收益指标:")
        print(f"  初始资金: {result.initial_cash:,.0f}")
        print(f"  最终净值: {result.final_value:,.0f}")
        print(f"  总收益率: {result.total_return*100:.2f}%")
        print(f"  年化收益率: {result.annual_return*100:.2f}%")
        
        if result.benchmark_return != 0:
            print(f"  基准收益率: {result.benchmark_return*100:.2f}%")
            print(f"  基准年化: {result.benchmark_annual*100:.2f}%")
            print(f"  超额收益: {result.excess_return*100:.2f}%")
        
        print(f"\n风险指标:")
        print(f"  最大回撤: {result.max_drawdown*100:.2f}%")
        print(f"  波动率: {result.volatility*100:.2f}%")
        print(f"  夏普比率: {result.sharpe_ratio:.2f}")
        print(f"  索提诺比率: {result.sortino_ratio:.2f}")
        print(f"  卡玛比率: {result.calmar_ratio:.2f}")
        
        print(f"\n交易统计:")
        print(f"  总交易数: {result.total_trades}")
        print(f"  盈利次数: {result.win_trades}")
        print(f"  亏损次数: {result.lose_trades}")
        print(f"  胜率: {result.win_rate*100:.2f}%")
        print(f"  平均收益/笔: {result.avg_return_per_trade*100:.2f}%")
        print(f"  平均盈利: {result.avg_win*100:.2f}%")
        print(f"  平均亏损: {result.avg_loss*100:.2f}%")
        print(f"  盈亏比: {result.profit_loss_ratio:.2f}")
        print(f"  平均持仓天数: {result.avg_hold_days:.1f}")
        
        # 分类统计
        if result.momentum_stats:
            print(f"\n动量信号统计:")
            print(f"  交易数: {result.momentum_stats.get('count', 0)}")
            print(f"  胜率: {result.momentum_stats.get('win_rate', 0)*100:.2f}%")
            print(f"  平均收益: {result.momentum_stats.get('avg_return', 0)*100:.2f}%")
        
        if result.reversal_stats:
            print(f"\n反转信号统计:")
            print(f"  交易数: {result.reversal_stats.get('count', 0)}")
            print(f"  胜率: {result.reversal_stats.get('win_rate', 0)*100:.2f}%")
            print(f"  平均收益: {result.reversal_stats.get('avg_return', 0)*100:.2f}%")
        
        print("\n" + "=" * 60)
