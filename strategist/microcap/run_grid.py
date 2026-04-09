# -*- coding: utf-8 -*-
"""
微盘股策略网格测试

对多种因子 × 持有周期组合进行回测，输出对比汇总表和月度收益明细。

用法：
  DB_ENV=online python -m strategist.microcap.run_grid \
    --start 2022-01-01 --end 2026-03-24

  # 指定要测试的因子和持有天数
  DB_ENV=online python -m strategist.microcap.run_grid \
    --start 2022-01-01 --end 2026-03-24 \
    --factors peg pe roe \
    --hold-days 1 3 5 10
"""
import os
import sys
import json
import logging
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, date

import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(ROOT, 'output', 'microcap')


def calc_monthly_returns(daily_values_df: pd.DataFrame) -> pd.DataFrame:
    df = daily_values_df.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['month'] = df['trade_date'].dt.to_period('M')
    records = []
    for month, group in df.groupby('month'):
        nav_start = float(group.iloc[0]['nav'])
        nav_end = float(group.iloc[-1]['nav'])
        records.append({
            'month': str(month),
            'monthly_return': round((nav_end / nav_start) - 1.0, 6),
        })
    return pd.DataFrame(records)


def run_one(factor: str, hold_days: int, start_date: str, end_date: str,
            top_n: int = 15, slippage_rate: float = 0.001) -> dict:
    """运行单个策略组合，返回汇总结果。"""
    label = f"{factor}_h{hold_days}"
    logger.info(f"[RUN] {label}  {start_date} ~ {end_date}")

    config = MicrocapConfig(
        start_date=start_date,
        end_date=end_date,
        factor=factor,
        top_n=top_n,
        hold_days=hold_days,
        market_cap_percentile=0.20,
        buy_cost_rate=0.0003,
        sell_cost_rate=0.0013,
        slippage_rate=slippage_rate,
        exclude_st=True,
    )

    backtest = MicrocapBacktest(config)
    result = backtest.run()

    if result['status'] != 'ok':
        logger.error(f"[ERROR] {label} failed: {result['message']}")
        return {'label': label, 'factor': factor, 'hold_days': hold_days, 'status': 'error'}

    summary = result['backtest_summary']
    daily_df = result['daily_values_df']

    # 保存每日净值
    date_str = f"{start_date.replace('-','')}_{end_date.replace('-','')}"
    daily_file = os.path.join(OUTPUT_DIR, f'grid_{label}_{date_str}_daily.csv')
    daily_df.to_csv(daily_file, index=False)

    # 月度收益
    monthly_df = calc_monthly_returns(daily_df)
    monthly_file = os.path.join(OUTPUT_DIR, f'grid_{label}_{date_str}_monthly.csv')
    monthly_df.to_csv(monthly_file, index=False)

    row = {
        'label':         label,
        'factor':        factor,
        'hold_days':     hold_days,
        'status':        'ok',
        'total_return':  round(summary['total_return'], 4),
        'annual_return': round(summary['annual_return'], 4),
        'sharpe':        round(summary['sharpe_ratio'], 3),
        'max_drawdown':  round(summary['max_drawdown'], 4),
        'win_rate':      round(summary['win_rate'], 4),
        'total_trades':  summary['total_trades'],
        'daily_file':    daily_file,
        'monthly_file':  monthly_file,
    }

    logger.info(
        f"[OK] {label}: total={row['total_return']:+.2%}, "
        f"annual={row['annual_return']:+.2%}, sharpe={row['sharpe']:.3f}, "
        f"maxdd={row['max_drawdown']:.2%}, winrate={row['win_rate']:.1%}"
    )
    return row


def print_summary_table(results: list):
    """打印汇总对比表。"""
    ok_rows = [r for r in results if r.get('status') == 'ok']
    if not ok_rows:
        logger.warning("No successful results to display.")
        return

    df = pd.DataFrame(ok_rows)[
        ['label', 'factor', 'hold_days', 'total_return', 'annual_return',
         'sharpe', 'max_drawdown', 'win_rate', 'total_trades']
    ].sort_values(['factor', 'hold_days'])

    print("\n" + "=" * 90)
    print("微盘股策略网格测试 - 汇总对比")
    print("=" * 90)
    print(f"{'策略':<18} {'因子':<8} {'持有天':<7} {'总收益':>8} {'年化':>8} "
          f"{'Sharpe':>7} {'最大回撤':>8} {'胜率':>7} {'交易笔数':>8}")
    print("-" * 90)
    for _, row in df.iterrows():
        sign = '+' if row['total_return'] >= 0 else ''
        asign = '+' if row['annual_return'] >= 0 else ''
        print(
            f"{row['label']:<18} {row['factor']:<8} {int(row['hold_days']):<7} "
            f"{sign}{row['total_return']:.2%}   {asign}{row['annual_return']:.2%}   "
            f"{row['sharpe']:>7.3f}   {row['max_drawdown']:.2%}   "
            f"{row['win_rate']:.1%}   {int(row['total_trades']):>8}"
        )
    print("=" * 90)


def print_monthly_comparison(results: list):
    """打印月度收益对比矩阵。"""
    ok_rows = [r for r in results if r.get('status') == 'ok']
    if not ok_rows:
        return

    monthly_dfs = {}
    for row in ok_rows:
        mdf = pd.read_csv(row['monthly_file'])
        monthly_dfs[row['label']] = dict(zip(mdf['month'], mdf['monthly_return']))

    # 获取所有月份并排序
    all_months = sorted({m for d in monthly_dfs.values() for m in d.keys()})

    labels = [r['label'] for r in ok_rows]
    col_w = 10

    print("\n" + "=" * (14 + col_w * len(labels)))
    print("月度收益对比矩阵")
    print("=" * (14 + col_w * len(labels)))

    # 表头
    header = f"{'月份':<14}"
    for lbl in labels:
        header += f"{lbl:>{col_w}}"
    print(header)
    print("-" * (14 + col_w * len(labels)))

    pos_counts = {lbl: 0 for lbl in labels}
    neg_counts = {lbl: 0 for lbl in labels}

    for month in all_months:
        line = f"{month:<14}"
        for lbl in labels:
            val = monthly_dfs[lbl].get(month)
            if val is None:
                line += f"{'N/A':>{col_w}}"
            else:
                sign = '+' if val >= 0 else ''
                line += f"{sign}{val:.2%}".rjust(col_w)
                if val > 0:
                    pos_counts[lbl] += 1
                else:
                    neg_counts[lbl] += 1
        print(line)

    print("-" * (14 + col_w * len(labels)))
    pos_line = f"{'正收益月份':<14}"
    neg_line = f"{'负收益月份':<14}"
    for lbl in labels:
        pos_line += f"{pos_counts[lbl]:>{col_w}}"
        neg_line += f"{neg_counts[lbl]:>{col_w}}"
    print(pos_line)
    print(neg_line)
    print("=" * (14 + col_w * len(labels)))


def _run_one_task(args_tuple):
    """进程池 worker，解包参数后调用 run_one。"""
    factor, hold_days, start, end, top_n, slippage_rate = args_tuple
    return run_one(factor, hold_days, start, end, top_n, slippage_rate)


def main():
    parser = argparse.ArgumentParser(description='微盘股策略网格测试')
    parser.add_argument('--start', default='2022-01-01')
    parser.add_argument('--end',   default='2026-03-24')
    parser.add_argument('--factors',   nargs='+', default=['peg', 'pe', 'roe', 'peg_ebit_mv', 'pure_mv'],
                        choices=['peg', 'pe', 'roe', 'ebit_ratio', 'peg_ebit_mv', 'pure_mv'])
    parser.add_argument('--hold-days', nargs='+', type=int, default=[1, 3, 5, 10],
                        dest='hold_days')
    parser.add_argument('--top-n', type=int, default=15, dest='top_n')
    parser.add_argument('--workers', type=int, default=1,
                        help='并行进程数（默认1，顺序执行）')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    combos = [
        (f, h, args.start, args.end, args.top_n, 0.001)
        for f in args.factors
        for h in args.hold_days
    ]
    total = len(combos)

    logger.info("=" * 60)
    logger.info(f"网格测试: factors={args.factors}, hold_days={args.hold_days}")
    logger.info(f"日期范围: {args.start} ~ {args.end}, top_n={args.top_n}")
    logger.info(f"并行进程: {args.workers}, 总组合数: {total}")
    logger.info("=" * 60)

    results = []

    if args.workers <= 1:
        for i, combo in enumerate(combos, 1):
            logger.info(f"\n[{i}/{total}] 开始: factor={combo[0]}, hold_days={combo[1]}")
            results.append(_run_one_task(combo))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_run_one_task, combo): combo for combo in combos}
            done_count = 0
            for future in as_completed(futures):
                combo = futures[future]
                done_count += 1
                try:
                    row = future.result()
                    results.append(row)
                    logger.info(f"[{done_count}/{total}] 完成: {combo[0]}_h{combo[1]}")
                except Exception as e:
                    logger.error(f"[{done_count}/{total}] 失败: {combo[0]}_h{combo[1]}: {e}")
                    results.append({'label': f"{combo[0]}_h{combo[1]}", 'status': 'error'})

    # 按 factor + hold_days 排序
    results.sort(key=lambda r: (r.get('factor', ''), r.get('hold_days', 0)))

    # 保存结果
    date_str = f"{args.start.replace('-','')}_{args.end.replace('-','')}"
    result_file = os.path.join(OUTPUT_DIR, f'grid_summary_{date_str}.json')
    with open(result_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"\n[OK] 结果已保存: {result_file}")

    # 打印汇总
    print_summary_table(results)
    print_monthly_comparison(results)


if __name__ == '__main__':
    main()
