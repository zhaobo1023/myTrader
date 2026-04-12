#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Microcap v3.0 并行回测管理器

使用多进程并行运行所有因子和持有天数组合的回测。
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# 根目录
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def run_single_backtest(year: str, factor: str, hold_days: int,
                        start_date: str, end_date: str,
                        log_dir: str) -> dict:
    """
    运行单个回测任务。

    Args:
        year: 年份 (2025/2026)
        factor: 因子类型
        hold_days: 持有天数
        start_date: 开始日期
        end_date: 结束日期
        log_dir: 日志目录

    Returns:
        回测结果字典
    """
    log_file = os.path.join(log_dir, f"{year}_{factor}_{hold_days}d.log")

    cmd = [
        "python", "-m", "strategist.microcap.run_backtest",
        "--start", start_date,
        "--end", end_date,
        "--factor", factor,
        "--top-n", "15",
        "--hold-days", str(hold_days),
        "--market-cap-percentile", "0.20",
        "--min-turnover", "5000000"
    ]

    start_time = datetime.now()

    try:
        # 执行回测
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30分钟超时
        )

        # 写入日志
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== Microcap Backtest: {year} | {factor} | {hold_days}d ===\n")
            f.write(f"Time Range: {start_date} ~ {end_date}\n")
            f.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration: {(datetime.now() - start_time).total_seconds():.1f}s\n")
            f.write("\n=== STDOUT ===\n")
            f.write(result.stdout)
            f.write("\n=== STDERR ===\n")
            f.write(result.stderr)
            f.write(f"\n=== Return Code: {result.returncode} ===\n")

        # 读取生成的统计文件
        output_dir = "output/microcap"
        summary_file = os.path.join(
            output_dir,
            f"backtest_summary_{start_date.replace('-', '')}_{end_date.replace('-', '')}.json"
        )

        summary = {}
        if os.path.exists(summary_file):
            with open(summary_file, 'r') as f:
                summary = json.load(f)

        return {
            "year": year,
            "factor": factor,
            "hold_days": hold_days,
            "start_date": start_date,
            "end_date": end_date,
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "log_file": log_file,
            "summary": summary,
            "duration": (datetime.now() - start_time).total_seconds()
        }

    except subprocess.TimeoutExpired:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n=== TIMEOUT (>1800s) ===\n")

        return {
            "year": year,
            "factor": factor,
            "hold_days": hold_days,
            "success": False,
            "error": "timeout",
            "log_file": log_file
        }

    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n=== ERROR: {str(e)} ===\n")

        return {
            "year": year,
            "factor": factor,
            "hold_days": hold_days,
            "success": False,
            "error": str(e),
            "log_file": log_file
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Microcap v3.0 并行回测')
    parser.add_argument('--workers', type=int, default=4,
                       help='并行进程数（默认4）')
    parser.add_argument('--year', type=str, default='all',
                       choices=['2025', '2026', 'all'],
                       help='回测年份')
    parser.add_argument('--factor', type=str, default='all',
                       help='指定因子（默认全部）')
    args = parser.parse_args()

    # 配置
    FACTORS = ["peg", "pe", "pure_mv", "pure_mv_mom", "peg_ebit_mv"]
    HOLD_DAYS = [1, 5, 10, 20]

    # 过滤因子
    if args.factor != 'all':
        FACTORS = [args.factor]

    # 时间范围
    date_ranges = {
        "2025": ("2025-01-01", "2025-12-31"),
        "2026": ("2026-01-01", "2026-04-10")
    }

    # 过滤年份
    years = [args.year] if args.year != 'all' else ["2025", "2026"]

    # 创建日志目录
    log_dir = os.path.join(ROOT, "output/microcap/logs")
    os.makedirs(log_dir, exist_ok=True)

    # 生成任务列表
    tasks = []
    for year in years:
        start_date, end_date = date_ranges[year]
        for factor in FACTORS:
            for hold_days in HOLD_DAYS:
                tasks.append((year, factor, hold_days, start_date, end_date, log_dir))

    total_tasks = len(tasks)

    print("=" * 60)
    print("Microcap v3.0 并行回测矩阵")
    print("=" * 60)
    print(f"时间范围: {', '.join(years)}")
    print(f"因子数量: {len(FACTORS)} ({', '.join(FACTORS)})")
    print(f"持有天数: {len(HOLD_DAYS)} 种 ({', '.join(map(str, HOLD_DAYS))})")
    print(f"总任务数: {total_tasks}")
    print(f"并行进程: {args.workers}")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # 执行并行回测
    results = []
    completed = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # 提交所有任务
        future_to_task = {
            executor.submit(run_single_backtest, *task): task
            for task in tasks
        }

        # 收集结果
        for future in as_completed(future_to_task):
            completed += 1
            progress = completed / total_tasks * 100

            try:
                result = future.result()
                results.append(result)

                status = "[OK]" if result['success'] else "[FAIL]"
                print(f"{status} 进度 {completed}/{total_tasks} ({progress:.1f}%) | "
                      f"{result['year']} {result['factor']} {result['hold_days']}d | "
                      f"耗时 {result.get('duration', 0):.1f}s")

            except Exception as e:
                task = future_to_task[future]
                print(f"[ERROR] 任务失败: {task} | 错误: {e}")

    print()
    print("=" * 60)
    print("回测完成！生成汇总报告...")
    print("=" * 60)

    # 生成汇总报告
    summary_data = []
    for r in results:
        row = {
            "year": r['year'],
            "factor": r['factor'],
            "hold_days": r['hold_days'],
            "success": r['success'],
            "duration": r.get('duration', 0)
        }

        # 添加统计指标
        if r.get('summary'):
            s = r['summary']
            row.update({
                "total_trades": s.get('total_trades', 0),
                "win_rate": s.get('win_rate', 0),
                "total_return": s.get('total_return', 0),
                "annual_return": s.get('annual_return', 0),
                "sharpe_ratio": s.get('sharpe_ratio', 0),
                "max_drawdown": s.get('max_drawdown', 0),
            })

        summary_data.append(row)

    # 保存汇总表
    if summary_data:
        import pandas as pd

        df = pd.DataFrame(summary_data)
        df = df.sort_values(['year', 'sharpe_ratio'], ascending=[True, False])

        # 保存 CSV
        summary_file = os.path.join(ROOT, "output/microcap/all_backtests_summary.csv")
        df.to_csv(summary_file, index=False, encoding='utf-8-sig')

        # 保存 Markdown
        md_file = os.path.join(ROOT, "output/microcap/all_backtests_summary.md")
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write("# Microcap v3.0 全量回测汇总\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**总任务数**: {total_tasks}\n")
            f.write(f"**成功完成**: {len([r for r in results if r['success']])}\n")
            f.write(f"**失败任务**: {len([r for r in results if not r['success']])}\n\n")

            # 按 Sharpe 排序的 Top 10
            f.write("## Top 10 策略（按 Sharpe 排序）\n\n")
            top10 = df.nlargest(10, 'sharpe_ratio')
            for _, row in top10.iterrows():
                f.write(f"- {row['year']} | {row['factor']} | {row['hold_days']}d | "
                       f"Sharpe: {row['sharpe_ratio']:.3f} | "
                       f"年化收益: {row['annual_return']*100:.2f}% | "
                       f"胜率: {row['win_rate']*100:.2f}%\n")

            f.write("\n## 完整结果\n\n")
            f.write(df.to_markdown(index=False))

        print(f"CSV 汇总: {summary_file}")
        print(f"Markdown 汇总: {md_file}")
        print()

        # 打印 Top 10
        print("Top 10 策略（按 Sharpe 排序）：")
        print("-" * 80)
        top10 = df.nlargest(10, 'sharpe_ratio')
        for idx, row in top10.iterrows():
            print(f"{row['year']} | {row['factor']:12} | {row['hold_days']:2}d | "
                 f"Sharpe: {row['sharpe_ratio']:6.3f} | "
                 f"收益: {row['annual_return']*100:6.2f}% | "
                 f"胜率: {row['win_rate']*100:5.2f}%")
        print("-" * 80)

    print()
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"日志目录: {log_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
