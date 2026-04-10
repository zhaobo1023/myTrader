# -*- coding: utf-8 -*-
"""
Microcap PEG 策略回测 CLI

使用方式：
  python -m strategist.microcap.run_backtest --start 2024-01-01 --end 2025-12-31 --factor peg --top-n 15 --hold-days 1

输出：
  - output/microcap/backtest_<date_range>.csv - 交易记录
  - output/microcap/backtest_daily_values_<date_range>.csv - 每日净值
  - output/microcap/backtest_summary.json - 统计摘要
"""
import os
import sys
import argparse
import json
import logging
from datetime import datetime

import pandas as pd

# 根目录
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest


def _calc_monthly_returns(daily_values_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算月度收益率。

    Args:
        daily_values_df: 每日净值 DataFrame，含 trade_date, nav 列

    Returns:
        月度收益 DataFrame，列 [month, nav_start, nav_end, monthly_return, trade_days]
    """
    df = daily_values_df.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['month'] = df['trade_date'].dt.to_period('M')

    records = []
    for month, group in df.groupby('month'):
        nav_start = group.iloc[0]['nav']
        nav_end = group.iloc[-1]['nav']
        monthly_return = (nav_end / nav_start) - 1.0
        records.append({
            'month': str(month),
            'nav_start': round(float(nav_start), 6),
            'nav_end': round(float(nav_end), 6),
            'monthly_return': round(float(monthly_return), 6),
            'trade_days': len(group),
        })

    return pd.DataFrame(records)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Microcap PEG 策略回测'
    )
    parser.add_argument('--start', type=str, default='2024-01-01',
                       help='回测开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2025-12-31',
                       help='回测结束日期 (YYYY-MM-DD)')
    parser.add_argument('--factor', type=str, default='peg',
                       choices=['peg', 'pe', 'roe', 'ebit_ratio', 'peg_ebit_mv', 'pure_mv'],
                       help='因子类型')
    parser.add_argument('--top-n', type=int, default=15,
                       help='每期选股数量')
    parser.add_argument('--hold-days', type=int, default=1,
                       help='持有天数')
    parser.add_argument('--market-cap-percentile', type=float, default=0.20,
                       help='市值百分位 (0.20 表示后20%%)')
    parser.add_argument('--buy-cost-rate',  type=float, default=0.0003,
                       help='买入费率 (默认0.03%%佣金)')
    parser.add_argument('--sell-cost-rate', type=float, default=0.0013,
                       help='卖出费率 (默认0.03%%佣金+0.10%%印花税)')
    parser.add_argument('--exclude-st', action='store_true', default=True,
                       help='排除 ST/*ST 股票')
    parser.add_argument('--slippage-rate', type=float, default=0.001,
                       help='单边滑点率 (默认0.1%%，微盘股买卖价差+冲击成本)')
    parser.add_argument('--min-turnover', type=float, default=0.0,
                       dest='min_avg_turnover',
                       help='近5日平均成交额最低要求（元），0表示不过滤，实盘建议5000000')

    args = parser.parse_args()

    # 验证日期格式
    try:
        start_date = datetime.strptime(args.start, '%Y-%m-%d').strftime('%Y-%m-%d')
        end_date = datetime.strptime(args.end, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError as e:
        logger.error(f"[ERROR] Invalid date format: {e}")
        sys.exit(1)

    # 创建配置
    config = MicrocapConfig(
        start_date=start_date,
        end_date=end_date,
        factor=args.factor,
        top_n=args.top_n,
        hold_days=args.hold_days,
        market_cap_percentile=args.market_cap_percentile,
        buy_cost_rate=args.buy_cost_rate,
        sell_cost_rate=args.sell_cost_rate,
        slippage_rate=args.slippage_rate,
        exclude_st=args.exclude_st,
        min_avg_turnover=args.min_avg_turnover,
    )

    # 创建输出目录
    os.makedirs(config.output_dir, exist_ok=True)

    # 日期范围字符串
    date_range_str = f"{start_date.replace('-', '')}_{end_date.replace('-', '')}"

    logger.info(f"[OK] Starting backtest with config:")
    logger.info(f"     Start: {start_date}, End: {end_date}")
    logger.info(f"     Factor: {args.factor}, Top-N: {args.top_n}, Hold-Days: {args.hold_days}")
    logger.info(f"     Market Cap Percentile: {args.market_cap_percentile}")
    logger.info(f"     Buy Cost Rate: {args.buy_cost_rate:.4f}, Sell Cost Rate: {args.sell_cost_rate:.4f}")
    logger.info(f"     Slippage Rate: {args.slippage_rate:.4f} (one-way)")

    # 执行回测
    backtest = MicrocapBacktest(config)
    result = backtest.run()

    if result['status'] != 'ok':
        logger.error(f"[ERROR] Backtest failed: {result['message']}")
        sys.exit(1)

    # 保存结果
    summary = result['backtest_summary']
    trades_df = result['trades_df']
    daily_values_df = result['daily_values_df']
    benchmark_df = result.get('benchmark_df', None)

    # 交易记录
    if not trades_df.empty:
        trades_file = os.path.join(config.output_dir, f'backtest_{date_range_str}.csv')
        trades_df.to_csv(trades_file, index=False)
        logger.info(f"[OK] Trades saved to: {trades_file}")

    # 每日净值
    if not daily_values_df.empty:
        daily_file = os.path.join(config.output_dir, f'backtest_daily_values_{date_range_str}.csv')
        daily_values_df.to_csv(daily_file, index=False)
        logger.info(f"[OK] Daily values saved to: {daily_file}")

    # 统计摘要
    summary_file = os.path.join(config.output_dir, 'backtest_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    logger.info(f"[OK] Summary saved to: {summary_file}")

    # NAV 对比 CSV（策略 + 基准）
    if not daily_values_df.empty and benchmark_df is not None and not benchmark_df.empty:
        nav_compare = daily_values_df[['trade_date', 'nav', 'daily_return']].copy()
        nav_compare.columns = ['trade_date', 'strategy_nav', 'strategy_return']
        bench_nav = benchmark_df[['trade_date', 'daily_return']].copy()
        bench_nav.columns = ['trade_date', 'benchmark_return']
        bench_nav['benchmark_nav'] = (1 + bench_nav['benchmark_return']).cumprod()
        # 基准 NAV 基点对齐到 1.0
        if bench_nav['benchmark_nav'].iloc[0] > 0:
            bench_nav['benchmark_nav'] = bench_nav['benchmark_nav'] / bench_nav['benchmark_nav'].iloc[0]
        nav_compare = nav_compare.merge(bench_nav, on='trade_date', how='left')
        nav_compare_file = os.path.join(config.output_dir, f'nav_vs_benchmark_{date_range_str}.csv')
        nav_compare.to_csv(nav_compare_file, index=False)
        logger.info(f"[OK] NAV vs Benchmark saved to: {nav_compare_file}")

    # 打印摘要
    logger.info("[OK] Backtest Summary:")
    logger.info(f"     Total Trades: {summary['total_trades']}")
    logger.info(f"     Winning Trades: {summary['winning_trades']}")
    logger.info(f"     Losing Trades: {summary['losing_trades']}")
    logger.info(f"     Win Rate: {summary['win_rate']:.2%}")
    logger.info(f"     Total Return: {summary['total_return']:.4f}")
    logger.info(f"     Annual Return: {summary['annual_return']:.4f}")
    logger.info(f"     Sharpe Ratio: {summary['sharpe_ratio']:.4f}")
    logger.info(f"     Max Drawdown: {summary['max_drawdown']:.4f}")
    logger.info(f"     Limit-Up Skipped: {summary.get('limit_up_skipped', 0)}")
    logger.info(f"     Limit-Down Delayed: {summary.get('limit_down_delayed', 0)}")
    if summary.get('benchmark_annual_return') is not None:
        logger.info(f"     --- Benchmark ({summary.get('benchmark_code', '')}) ---")
        logger.info(f"     Benchmark Annual Return: {summary['benchmark_annual_return']:.4f}")
        logger.info(f"     Excess Annual Return:    {summary['excess_annual_return']:.4f}")
        logger.info(f"     Information Ratio:       {summary['information_ratio']:.4f}")
        logger.info(f"     Beta:                    {summary['beta']:.4f}")
        logger.info(f"     Alpha (annualized):      {summary['alpha']:.4f}")

    # 月度收益统计
    if not daily_values_df.empty:
        monthly_df = _calc_monthly_returns(daily_values_df)
        if not monthly_df.empty:
            monthly_file = os.path.join(config.output_dir, f'backtest_monthly_{date_range_str}.csv')
            monthly_df.to_csv(monthly_file, index=False)
            logger.info(f"[OK] Monthly returns saved to: {monthly_file}")
            logger.info("[OK] Monthly Returns:")
            logger.info(f"     {'Month':<10} {'Return':>8}  {'NAV Start':>10} {'NAV End':>10}  {'TradeDays':>9}")
            for _, row in monthly_df.iterrows():
                sign = '+' if row['monthly_return'] >= 0 else ''
                logger.info(
                    f"     {row['month']:<10} {sign}{row['monthly_return']:.2%}    "
                    f"{row['nav_start']:>10.4f} {row['nav_end']:>10.4f}  {int(row['trade_days']):>9}"
                )


if __name__ == '__main__':
    main()
