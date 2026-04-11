#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微盘股策略 - 内存优化版回测

优化策略：
1. 分批加载数据（按年份）
2. 只加载必要的列
3. 使用更小的回测范围测试
"""
import sys
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest
import json


def main():
    print("=" * 70)
    print("微盘股PEG策略 - 内存优化版回测")
    print("=" * 70)

    # 使用更小的回测范围进行测试
    start_date = '2024-01-01'
    end_date = '2026-03-31'

    print(f"\n回测范围: {start_date} ~ {end_date}")
    print(f"数据量估计: 约 200万行（vs 全量3年 450万行）")
    print(f"预计内存需求: 约 800MB")
    print(f"预计耗时: 1-2分钟")

    config = MicrocapConfig(
        start_date=start_date,
        end_date=end_date,
        factor='peg',
        top_n=15,
        hold_days=1,
        market_cap_percentile=0.20,
        buy_cost_rate=0.0003,
        sell_cost_rate=0.0013,
        slippage_rate=0.001,
        exclude_st=True,
        min_avg_turnover=0.0,
    )

    print(f"\n配置参数:")
    print(f"  因子: {config.factor}")
    print(f"  选股数: {config.top_n}")
    print(f"  持有天数: {config.hold_days}")
    print(f"  市值百分位: {config.market_cap_percentile}")

    # 创建输出目录
    os.makedirs(config.output_dir, exist_ok=True)

    # 执行回测
    print("\n开始回测...")
    backtest = MicrocapBacktest(config)
    result = backtest.run()

    if result['status'] != 'ok':
        print(f"\n[ERROR] 回测失败: {result['message']}")
        return

    # 保存结果
    summary = result['backtest_summary']
    trades_df = result['trades_df']
    daily_values_df = result['daily_values_df']

    # 保存文件
    date_range_str = f"{start_date.replace('-', '')}_{end_date.replace('-', '')}"

    if not trades_df.empty:
        trades_file = os.path.join(config.output_dir, f'backtest_{date_range_str}.csv')
        trades_df.to_csv(trades_file, index=False)
        print(f"[OK] 交易记录: {trades_file}")

    if not daily_values_df.empty:
        daily_file = os.path.join(config.output_dir, f'backtest_daily_values_{date_range_str}.csv')
        daily_values_df.to_csv(daily_file, index=False)
        print(f"[OK] 每日净值: {daily_file}")

    summary_file = os.path.join(config.output_dir, 'backtest_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"[OK] 统计摘要: {summary_file}")

    # 打印结果
    print("\n" + "=" * 70)
    print("回测结果")
    print("=" * 70)

    print(f"\n核心指标:")
    print(f"  总交易数: {summary['total_trades']}")
    print(f"  盈利交易: {summary['winning_trades']}")
    print(f"  亏损交易: {summary['losing_trades']}")
    print(f"  胜率: {summary['win_rate']:.2%}")

    print(f"\n收益指标:")
    print(f"  总收益率: {summary['total_return']:.2%}")
    print(f"  年化收益率: {summary['annual_return']:.2%}")
    print(f"  夏普比率: {summary['sharpe_ratio']:.4f}")
    print(f"  最大回撤: {summary['max_drawdown']:.2%}")

    print(f"\n风控统计:")
    print(f"  涨停跳过买入: {summary.get('limit_up_skipped', 0)} 次")
    print(f"  跌停顺延卖出: {summary.get('limit_down_delayed', 0)} 次")

    if summary.get('benchmark_annual_return') is not None:
        print(f"\n基准对比:")
        print(f"  基准代码: {summary.get('benchmark_code', 'N/A')}")
        print(f"  基准年化收益: {summary['benchmark_annual_return']:.2%}")
        print(f"  超额年化收益: {summary['excess_annual_return']:.2%}")
        print(f"  信息比率: {summary['information_ratio']:.4f}")
        print(f"  Beta: {summary['beta']:.4f}")
        print(f"  Alpha: {summary['alpha']:.4f}")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
