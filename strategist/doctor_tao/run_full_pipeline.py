# -*- coding: utf-8 -*-
"""
完整流程：全量筛选 + 回测 + 生成报告
"""
import sys
import os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from signal_screener import SignalScreener
from backtest import BacktestEngine
import pandas as pd
from datetime import datetime

print("=" * 80)
print("陶博士策略 - 完整流程")
print("=" * 80)

# Step 1: 全量信号筛选
print("\n[Step 1] 全量信号筛选...")
print("预计耗时: 5-10分钟（5000+只股票）")

screener = SignalScreener()
signals_df = screener.run_screener(output_csv=True)

if len(signals_df) == 0:
    print("\n⚠️ 未筛选出符合条件的股票")
    print("原因可能是：")
    print("  1. 当前市场环境不满足策略条件")
    print("  2. RPS阈值过高（可降低到85）")
    print("  3. 价格分位阈值过低（可提高到40）")
    print("\n建议：调整参数后重新筛选")
else:
    print(f"\n✓ 筛选完成！共 {len(signals_df)} 只股票")
    print(f"  动量信号: {len(signals_df[signals_df['signal_type']=='momentum'])} 只")
    print(f"  反转候选: {len(signals_df[signals_df['signal_type']=='reversal'])} 只")

    # Step 2: 历史回测
    print("\n[Step 2] 历史回测验证...")
    print("回测期间: 2020-2024（5年）")
    print("预计耗时: 10-15分钟")

    engine = BacktestEngine(hold_days=60, rps_exit_threshold=85)

    backtest_df, metrics = engine.run_backtest(
        start_date='2020-01-01',
        end_date='2024-12-31',
        sample_interval=20  # 每20个交易日采样一次
    )

    if len(backtest_df) > 0:
        # Step 3: 生成报告
        print("\n[Step 3] 生成回测报告...")

        output_dir = os.path.join(ROOT, 'output', 'doctor_tao')
        os.makedirs(output_dir, exist_ok=True)

        report_file = os.path.join(output_dir, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("陶博士策略 - 回测报告\n")
            f.write("=" * 80 + "\n\n")

            f.write("回测期间: 2020-01-01 至 2024-12-31\n")
            f.write(f"总信号数: {len(backtest_df)}\n\n")

            f.write("核心指标:\n")
            f.write("-" * 80 + "\n")
            for key, value in metrics.items():
                f.write(f"{key}: {value}\n")

            f.write("\n" + "=" * 80 + "\n")
            f.write("策略评估:\n")
            f.write("=" * 80 + "\n")

            win_rate = metrics.get('胜率(%)', 0)
            avg_return = metrics.get('平均收益率(%)', 0)
            max_loss = metrics.get('最大单笔亏损(%)', 0)

            if win_rate >= 60:
                f.write(f"✓ 胜率优秀 (≥60%): {win_rate:.2f}%\n")
            elif win_rate >= 55:
                f.write(f"✓ 胜率良好 (≥55%): {win_rate:.2f}%\n")
            elif win_rate >= 50:
                f.write(f"⚠ 胜率可用 (≥50%): {win_rate:.2f}%\n")
            else:
                f.write(f"✗ 胜率不足 (<50%): {win_rate:.2f}%\n")

            if avg_return >= 10:
                f.write(f"✓ 平均收益优秀 (≥10%): {avg_return:.2f}%\n")
            elif avg_return >= 6:
                f.write(f"✓ 平均收益良好 (≥6%): {avg_return:.2f}%\n")
            elif avg_return >= 3:
                f.write(f"⚠ 平均收益可用 (≥3%): {avg_return:.2f}%\n")
            else:
                f.write(f"✗ 平均收益不足 (<3%): {avg_return:.2f}%\n")

            if max_loss > -15:
                f.write(f"✓ 风控优秀 (最大亏损>-15%): {max_loss:.2f}%\n")
            elif max_loss > -20:
                f.write(f"✓ 风控良好 (最大亏损>-20%): {max_loss:.2f}%\n")
            elif max_loss > -30:
                f.write(f"⚠ 风控可用 (最大亏损>-30%): {max_loss:.2f}%\n")
            else:
                f.write(f"✗ 风控不足 (最大亏损≤-30%): {max_loss:.2f}%\n")

        print(f"\n✓ 报告已生成: {report_file}")

        # 打印关键指标
        print("\n" + "=" * 80)
        print("关键指标总结:")
        print("=" * 80)
        print(f"总交易数: {metrics.get('总交易数', 0)}")
        print(f"胜率: {metrics.get('胜率(%)', 0):.2f}%")
        print(f"平均收益率: {metrics.get('平均收益率(%)', 0):.2f}%")
        print(f"最大单笔亏损: {metrics.get('最大单笔亏损(%)', 0):.2f}%")

        if '动量胜率(%)' in metrics:
            print(f"\n动量信号:")
            print(f"  胜率: {metrics.get('动量胜率(%)', 0):.2f}%")
            print(f"  平均收益: {metrics.get('动量平均收益(%)', 0):.2f}%")

        if '反转胜率(%)' in metrics:
            print(f"\n反转候选:")
            print(f"  胜率: {metrics.get('反转胜率(%)', 0):.2f}%")
            print(f"  平均收益: {metrics.get('反转平均收益(%)', 0):.2f}%")

        print("=" * 80)

print("\n✓ 完整流程执行完毕！")
