#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Microcap v3.0 高级策略回测
- pure_mv_mom 因子 + 日历择时 + 动态止盈
"""

import os
import sys
import subprocess
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def run_advanced_backtest(year: str, hold_days: int, use_calendar: bool,
                          use_dynamic_exit: bool, log_dir: str) -> dict:
    """运行高级策略回测"""
    start_date = f"{year}-01-01"
    end_date = "2026-04-10" if year == "2026" else f"{year}-12-31"

    # 构建参数
    args = [
        "python", "-m", "strategist.microcap.run_backtest",
        "--start", start_date,
        "--end", end_date,
        "--factor", "pure_mv_mom",
        "--top-n", "15",
        "--hold-days", str(hold_days),
        "--market-cap-percentile", "0.20",
        "--min-turnover", "5000000"
    ]

    # 日历择时
    if use_calendar:
        args.extend([
            "--calendar-timing",
            "--weak-months", "1", "4", "12",
            "--weak-month-ratio", "0.5"
        ])

    # 动态止盈
    if use_dynamic_exit:
        args.extend([
            "--dynamic-cap-exit",
            "--cap-exit-percentile", "0.25"
        ])

    log_file = os.path.join(log_dir, f"adv_{year}_{hold_days}d_cal{use_calendar}_dyn{use_dynamic_exit}.log")

    start_time = datetime.now()

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=1800
        )

        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== Advanced Backtest: {year} | {hold_days}d ===\n")
            f.write(f"Calendar Timing: {use_calendar}\n")
            f.write(f"Dynamic Exit: {use_dynamic_exit}\n")
            f.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration: {(datetime.now() - start_time).total_seconds():.1f}s\n")
            f.write("\n=== STDOUT ===\n")
            f.write(result.stdout)

        return {
            "year": year,
            "hold_days": hold_days,
            "calendar": use_calendar,
            "dynamic_exit": use_dynamic_exit,
            "success": result.returncode == 0,
            "duration": (datetime.now() - start_time).total_seconds()
        }

    except Exception as e:
        return {
            "year": year,
            "hold_days": hold_days,
            "success": False,
            "error": str(e)
        }


def main():
    log_dir = os.path.join(ROOT, "output/microcap/logs")
    os.makedirs(log_dir, exist_ok=True)

    # 高级策略矩阵
    tasks = []
    for year in ["2025", "2026"]:
        for hold_days in [1, 5, 10, 20]:
            # 基准：pure_mv_mom
            tasks.append((year, hold_days, False, False, log_dir))

            # + 日历择时
            tasks.append((year, hold_days, True, False, log_dir))

            # + 动态止盈
            tasks.append((year, hold_days, False, True, log_dir))

            # + 日历择时 + 动态止盈
            tasks.append((year, hold_days, True, True, log_dir))

    total = len(tasks)

    print("=" * 60)
    print("Microcap v3.0 高级策略回测")
    print("=" * 60)
    print(f"总任务数: {total}")
    print(f"策略: pure_mv_mom + 日历择时 + 动态止盈")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = []
    completed = 0

    with ProcessPoolExecutor(max_workers=4) as executor:
        future_to_task = {
            executor.submit(run_advanced_backtest, *task): task
            for task in tasks
        }

        for future in as_completed(future_to_task):
            completed += 1
            progress = completed / total * 100

            try:
                result = future.result()
                results.append(result)

                status = "[OK]" if result['success'] else "[FAIL]"
                cal = " cal" if result.get('calendar') else ""
                dyn = " dyn" if result.get('dynamic_exit') else ""

                print(f"{status} {completed}/{total} ({progress:.1f}%) | "
                      f"{result['year']} {result['hold_days']}d{cal}{dyn}")

            except Exception as e:
                print(f"[ERROR] 任务失败: {e}")

    print()
    print("=" * 60)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"成功: {len([r for r in results if r['success']])}/{total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
