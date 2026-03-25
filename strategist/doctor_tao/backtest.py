# -*- coding: utf-8 -*-
"""
陶博士策略 - 简单回测框架

回测规则（有意简化，避免过度优化）：
- 入场：信号当周最后一个交易日（周五）收盘价买入
- 挌仓：固定持有 60 个交易日（约3个月）
- 出场：60日后收盘价卖出 OR RPS跌破85（任一先到）
- 不考虑手续费（先看信号质量，后期可加）
- 等权重：每只信号股持仓权重相同
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_fetcher import DoctorTaoDataFetcher
from indicators import IndicatorCalculator


class BacktestEngine:
    """回测引擎"""

    def __init__(self, hold_days: int = 60, rps_exit_threshold: float = 85):
        """
        初始化回测引擎

        Args:
            hold_days: 持仓天数，默认60
            rps_exit_threshold: RPS退出阈值，默认85
        """
        self.hold_days = hold_days
        self.rps_exit_threshold = rps_exit_threshold
        self.fetcher = DoctorTaoDataFetcher(use_cache=True)

    def backtest_signal(
        self,
        signal_date: str,
        stock_code: str,
        signal_type: str,
        price_dict: Dict[str, pd.DataFrame]
    ) -> Optional[Dict]:
        """
        回测单个信号

        Args:
            signal_date: 信号日期
            stock_code: 股票代码
            signal_type: 信号类型（momentum/reversal）
            price_dict: 价格数据字典

        Returns:
            回测结果字典，包含收益、持仓天数等
        """
        try:
            # 获取该股票的价格数据
            if stock_code not in price_dict:
                return None

            price_df = price_dict[stock_code].copy()
            price_df = price_df.sort_values('trade_date')

            # 找到信号日期后的数据
            signal_dt = pd.to_datetime(signal_date)
            future_prices = price_df[price_df['trade_date'] > signal_dt].copy()

            if len(future_prices) == 0:
                return None

            # 入场价格：信号当周最后一个交易日的收盘价
            # 简化处理：使用信号日期的下一个交易日
            entry_date = future_prices.iloc[0]['trade_date']
            entry_price = float(future_prices.iloc[0]['close'])

            # 计算未来60个交易日
            future_prices = future_prices.head(self.hold_days + 20)  # 多取一些，防止RPS退出

            if len(future_prices) < 5:  # 数据不足
                return None

            # 持仓期间每日收益
            future_prices['daily_return'] = future_prices['close'].pct_change()
            future_prices['cum_return'] = (1 + future_prices['daily_return']).cumprod() - 1

            # 计算RPS用于退出判断
            # 简化处理：不重新计算RPS，只根据价格走势判断

            # 持仓天数
            hold_count = 0
            exit_date = None
            exit_price = None
            exit_reason = 'hold_days'

            for idx, row in future_prices.iterrows():
                hold_count += 1

                # 检查是否达到持仓天数
                if hold_count >= self.hold_days:
                    exit_date = row['trade_date']
                    exit_price = float(row['close'])
                    exit_reason = 'hold_days'
                    break

                # 检查RPS退出条件（简化：如果累计收益跌破-15%则提前退出）
                if hold_count > 5 and row['cum_return'] < -0.15:
                    exit_date = row['trade_date']
                    exit_price = float(row['close'])
                    exit_reason = 'stop_loss'
                    break

            if exit_price is None:
                # 如果没有退出，使用最后一个价格
                exit_date = future_prices.iloc[-1]['trade_date']
                exit_price = float(future_prices.iloc[-1]['close'])
                exit_reason = 'data_end'

            # 计算收益率
            total_return = (exit_price - entry_price) / entry_price

            return {
                'stock_code': stock_code,
                'signal_date': signal_date,
                'signal_type': signal_type,
                'entry_date': entry_date,
                'entry_price': entry_price,
                'exit_date': exit_date,
                'exit_price': exit_price,
                'hold_days': hold_count,
                'total_return': total_return,
                'exit_reason': exit_reason
            }

        except Exception as e:
            print(f"回测失败 {stock_code} {signal_date}: {e}")
            return None

    def backtest_all_signals(
        self,
        signals_df: pd.DataFrame,
        price_dict: Dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        回测所有信号

        Args:
            signals_df: 信号DataFrame
            price_dict: 价格数据字典

        Returns:
            回测结果DataFrame
        """
        print(f"\n开始回测 {len(signals_df)} 个信号...")

        results = []
        total = len(signals_df)

        for idx, row in signals_df.iterrows():
            if (idx + 1) % 50 == 0:
                print(f"  进度: {idx+1}/{total}")

            result = self.backtest_signal(
                signal_date=str(row['trade_date'].date()),
                stock_code=row['stock_code'],
                signal_type=row['signal_type'],
                price_dict=price_dict
            )

            if result:
                results.append(result)

        print(f"  完成: {len(results)}/{total}")

        return pd.DataFrame(results)

    def calculate_metrics(self, backtest_df: pd.DataFrame) -> Dict:
        """
        计算回测指标

        Args:
            backtest_df: 回测结果DataFrame

        Returns:
            指标字典
        """
        if len(backtest_df) == 0:
            return {}

        # 基础指标
        total_trades = len(backtest_df)
        win_trades = len(backtest_df[backtest_df['total_return'] > 0])
        lose_trades = len(backtest_df[backtest_df['total_return'] <= 0])

        win_rate = win_trades / total_trades * 100 if total_trades > 0 else 0

        avg_return = backtest_df['total_return'].mean() * 100
        median_return = backtest_df['total_return'].median() * 100
        max_profit = backtest_df['total_return'].max() * 100
        max_loss = backtest_df['total_return'].min() * 100

        # 按信号类型分组
        momentum_df = backtest_df[backtest_df['signal_type'] == 'momentum']
        reversal_df = backtest_df[backtest_df['signal_type'] == 'reversal']

        metrics = {
            '总交易数': total_trades,
            '盈利次数': win_trades,
            '亏损次数': lose_trades,
            '胜率(%)': round(win_rate, 2),
            '平均收益率(%)': round(avg_return, 2),
            '中位数收益率(%)': round(median_return, 2),
            '最大单笔盈利(%)': round(max_profit, 2),
            '最大单笔亏损(%)': round(max_loss, 2),
        }

        # 动量信号统计
        if len(momentum_df) > 0:
            metrics['动量信号数'] = len(momentum_df)
            metrics['动量胜率(%)'] = round(len(momentum_df[momentum_df['total_return'] > 0]) / len(momentum_df) * 100, 2)
            metrics['动量平均收益(%)'] = round(momentum_df['total_return'].mean() * 100, 2)

        # 反转候选统计
        if len(reversal_df) > 0:
            metrics['反转信号数'] = len(reversal_df)
            metrics['反转胜率(%)'] = round(len(reversal_df[reversal_df['total_return'] > 0]) / len(reversal_df) * 100, 2)
            metrics['反转平均收益(%)'] = round(reversal_df['total_return'].mean() * 100, 2)

        return metrics

    def run_backtest(
        self,
        start_date: str = '2020-01-01',
        end_date: str = '2024-12-31',
        sample_interval: int = 20  # 每20个交易日取一次信号
    ) -> Tuple[pd.DataFrame, Dict]:
        """
        运行完整回测

        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期
            sample_interval: 采样间隔（交易日）

        Returns:
            (回测结果DataFrame, 指标字典)
        """
        print("=" * 60)
        print("陶博士策略 - 历史回测")
        print("=" * 60)

        # 1. 获取所有股票的价格数据
        print("\n[1/4] 获取股票价格数据...")
        all_stocks = self.fetcher.fetch_all_stocks()

        # 只取部分股票进行回测（实际使用时可以去掉限制）
        test_stocks = all_stocks[:500]
        print(f"  测试股票数: {len(test_stocks)}")

        price_dict = self.fetcher.fetch_daily_price_batch(
            test_stocks,
            start_date=start_date,
            end_date=end_date
        )

        print(f"  获取到 {len(price_dict)} 只股票的价格数据")

        # 2. 转换价格数据为DataFrame
        print("\n[2/4] 准备价格数据...")
        price_list = []
        for code, df in price_dict.items():
            if len(df) > 0:
                df['stock_code'] = code
                price_list.append(df)

        if not price_list:
            print("无有效价格数据")
            return pd.DataFrame(), {}

        price_df = pd.concat(price_list, ignore_index=True)

        # 3. 计算指标
        print("\n[3/4] 计算指标...")
        indicators_df = IndicatorCalculator.calc_all_indicators(price_df)

        # 4. 生成历史信号
        print("\n[4/4] 生成历史信号...")
        # 获取所有交易日期
        all_dates = sorted(indicators_df['trade_date'].unique())

        # 按采样间隔选择日期
        sample_dates = all_dates[::sample_interval]
        print(f"  采样日期数: {len(sample_dates)}")

        # 为每个采样日期生成信号
        all_signals = []

        for date in sample_dates:
            # 获取该日期的指标数据
            date_df = indicators_df[indicators_df['trade_date'] == date].copy()

            if len(date_df) == 0:
                continue

            # 价格过滤：收盘价 >= 3元
            date_df = date_df[date_df['close'] >= 3.0]

            # 动量信号（文档第3.2节）：
            # RPS >= 95, 股价 > MA20, 股价 > MA250, 60日涨幅排名前30%, 成交量放大
            momentum_mask = (date_df['rps'] >= 95)
            
            if 'ma20' in date_df.columns:
                momentum_mask = momentum_mask & (date_df['close'] > date_df['ma20'])
            
            if 'ma250' in date_df.columns:
                momentum_mask = momentum_mask & (date_df['close'] > date_df['ma250'])
            
            if 'return_60d_rank' in date_df.columns:
                momentum_mask = momentum_mask & (date_df['return_60d_rank'] >= 70)
            
            if 'volume_ratio' in date_df.columns:
                momentum_mask = momentum_mask & (date_df['volume_ratio'] >= 1.2)

            if momentum_mask.sum() > 0:
                momentum_df = date_df[momentum_mask].copy()
                momentum_df['signal_type'] = 'momentum'
                all_signals.append(momentum_df)

            # 反转候选（文档第3.3节）：
            # 价格分位 < 35%, RPS < 90, RPS斜率Z > 1.0, 成交量异动 >= 1.5
            reversal_mask = (date_df['price_percentile'] < 35) & (date_df['rps'] < 90)
            
            if 'rps_slope' in date_df.columns:
                reversal_mask = reversal_mask & (date_df['rps_slope'] > 1.0)
            
            if 'volume_ratio' in date_df.columns:
                reversal_mask = reversal_mask & (date_df['volume_ratio'] >= 1.5)

            if reversal_mask.sum() > 0:
                reversal_df = date_df[reversal_mask].copy()
                reversal_df['signal_type'] = 'reversal'
                all_signals.append(reversal_df)

        if not all_signals:
            print("无有效信号")
            return pd.DataFrame(), {}

        signals_df = pd.concat(all_signals, ignore_index=True)
        print(f"  总信号数: {len(signals_df)}")

        # 5. 回测所有信号
        backtest_df = self.backtest_all_signals(signals_df, price_dict)

        # 6. 计算指标
        metrics = self.calculate_metrics(backtest_df)

        # 7. 打印结果
        print("\n" + "=" * 60)
        print("回测结果:")
        print("=" * 60)
        for key, value in metrics.items():
            print(f"{key}: {value}")

        return backtest_df, metrics


if __name__ == '__main__':
    # 运行回测
    engine = BacktestEngine()
    backtest_df, metrics = engine.run_backtest(
        start_date='2020-01-01',
        end_date='2024-12-31',
        sample_interval=20
    )

    if len(backtest_df) > 0:
        # 保存结果
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)

        output_file = os.path.join(output_dir, f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        backtest_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n回测结果已保存到: {output_file}")
