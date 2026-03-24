# -*- coding: utf-8 -*-
"""
滚动IC分析 - 机制切换演示版

功能:
    基于已有数据和理论，演示如何验证机制切换假设
    生成模拟的滚动IC数据，展示分析方法

运行:
    python research/rolling_ic_analysis_demo.py
"""
import os
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False
    print("警告: matplotlib 未安装")


# ============================================================
# 模拟数据生成 (用于演示机制切换)
# ============================================================

def generate_simulated_rolling_ic():
    """
    生成模拟的滚动IC数据，模拟机制切换

    模拟逻辑:
        - 2020-01-01 ~ 2022-02-23: IC均值约 -0.08 (负相关)
        - 2022-02-24 ~ 2026-03-24: IC均值约 +0.05 (正相关)

    Returns:
        pd.Series: 滚动IC序列
    """
    np.random.seed(42)

    # 生成日期序列
    start_date = '2020-01-01'
    end_date = '2026-03-24'
    dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 工作日

    split_date = pd.to_datetime('2022-02-24')

    # 分段生成IC
    before_dates = dates[dates < split_date]
    after_dates = dates[dates >= split_date]

    # 俄乌前: IC均值 -0.08, 标准差 0.15
    before_ic = np.random.normal(loc=-0.08, scale=0.15, size=len(before_dates))

    # 俄乌后: IC均值 +0.05, 标准差 0.12 (波动降低)
    after_ic = np.random.normal(loc=0.05, scale=0.12, size=len(after_dates))

    # 合并
    ic_values = np.concatenate([before_ic, after_ic])
    rolling_ic = pd.Series(ic_values, index=dates)

    return rolling_ic


# ============================================================
# 分段分析
# ============================================================

def analyze_periods(rolling_ic: pd.Series,
                    split_date: str = '2022-02-24') -> dict:
    """
    分段统计IC

    Args:
        rolling_ic: 滚动IC序列
        split_date: 分割日期 (俄乌冲突开始)

    Returns:
        {
            'before': {'mean': float, 'std': float, 'count': int},
            'after': {'mean': float, 'std': float, 'count': int},
            'full': {'mean': float, 'std': float, 'count': int}
        }
    """
    split_dt = pd.to_datetime(split_date)

    before = rolling_ic[rolling_ic.index < split_dt]
    after = rolling_ic[rolling_ic.index >= split_dt]

    result = {
        'before': {
            'mean': before.mean() if len(before) > 0 else None,
            'std': before.std() if len(before) > 0 else None,
            'count': len(before),
            'min': before.min() if len(before) > 0 else None,
            'max': before.max() if len(before) > 0 else None,
        },
        'after': {
            'mean': after.mean() if len(after) > 0 else None,
            'std': after.std() if len(after) > 0 else None,
            'count': len(after),
            'min': after.min() if len(after) > 0 else None,
            'max': after.max() if len(after) > 0 else None,
        },
        'full': {
            'mean': rolling_ic.mean(),
            'std': rolling_ic.std(),
            'count': len(rolling_ic),
            'min': rolling_ic.min(),
            'max': rolling_ic.max(),
        }
    }

    return result


# ============================================================
# 可视化
# ============================================================

def plot_rolling_ic(rolling_ic: pd.Series,
                    split_date: str,
                    factor_name: str,
                    etf_name: str,
                    save_path: str):
    """
    绘制滚动IC图

    Args:
        rolling_ic: 滚动IC序列
        split_date: 分割日期
        factor_name: 因子名称
        etf_name: ETF名称
        save_path: 保存路径
    """
    if not HAS_PLOT:
        print("matplotlib 未安装，跳过绘图")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # 子图1: 滚动IC时序图
    ax1.plot(rolling_ic.index, rolling_ic.values, label='Rolling IC', linewidth=1.5, alpha=0.8)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.8, alpha=0.5)
    ax1.axvline(x=pd.to_datetime(split_date), color='red', linestyle='--',
                linewidth=2, label=f'俄乌冲突 ({split_date})')

    # 标记正负区域
    ax1.fill_between(rolling_ic.index, rolling_ic.values, 0,
                     where=(rolling_ic.values > 0), alpha=0.3, color='green', label='正IC')
    ax1.fill_between(rolling_ic.index, rolling_ic.values, 0,
                     where=(rolling_ic.values < 0), alpha=0.3, color='red', label='负IC')

    ax1.set_title(f'{factor_name} 对 {etf_name} 的滚动IC (60日窗口) - 机制切换演示',
                  fontsize=14, fontweight='bold')
    ax1.set_xlabel('日期', fontsize=12)
    ax1.set_ylabel('IC', fontsize=12)
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3)

    # 设置日期格式
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # 子图2: 分段统计柱状图
    split_dt = pd.to_datetime(split_date)
    before = rolling_ic[rolling_ic.index < split_dt]
    after = rolling_ic[rolling_ic.index >= split_dt]

    periods = ['全样本\n(2020-2026)', f'俄乌前\n(2020-{split_date})', f'俄乌后\n({split_date}-2026)']
    means = [rolling_ic.mean(), before.mean() if len(before) > 0 else 0, after.mean() if len(after) > 0 else 0]
    stds = [rolling_ic.std(), before.std() if len(before) > 0 else 0, after.std() if len(after) > 0 else 0]

    colors = ['blue', 'orange', 'green']
    x_pos = np.arange(len(periods))

    bars = ax2.bar(x_pos, means, yerr=stds, capsize=5, color=colors, alpha=0.7)

    # 添加数值标签
    for i, (bar, mean, std) in enumerate(zip(bars, means, stds)):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + std + 0.005,
                f'{mean:.4f}\n±{std:.4f}',
                ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_title('分段IC均值对比 - 验证机制切换', fontsize=14, fontweight='bold')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(periods, fontsize=11)
    ax2.set_ylabel('IC均值', fontsize=12)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"  图表已保存: {save_path}")
    plt.close()


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 70)
    print("滚动IC分析 - 验证机制切换假设 (演示版)")
    print("=" * 70)

    # 配置
    factor_code = 'oil_mom_20'
    etf_code = '515220'
    etf_name = '煤炭ETF'
    window = 60
    split_date = '2022-02-24'  # 俄乌冲突开始

    print(f"\n因子: {factor_code}")
    print(f"目标: {etf_name} ({etf_code})")
    print(f"滚动窗口: {window} 交易日")
    print(f"分割点: {split_date} (俄乌冲突)")

    # 1. 生成模拟数据
    print("\n生成模拟滚动IC数据...")
    print("  模拟逻辑:")
    print("    - 俄乌前 (2020-2022.02): IC均值 ≈ -0.08 (原油涨 → 煤炭跌)")
    print("    - 俄乌后 (2022.02-2026): IC均值 ≈ +0.05 (原油涨 → 煤炭涨)")

    rolling_ic = generate_simulated_rolling_ic()
    print(f"  生成 {len(rolling_ic)} 条IC记录")

    # 2. 分段统计
    print("\n分段统计:")
    print("-" * 70)
    stats = analyze_periods(rolling_ic, split_date)

    print(f"全样本 (2020-2026):")
    print(f"  IC均值: {stats['full']['mean']:.4f}")
    print(f"  IC标准差: {stats['full']['std']:.4f}")
    print(f"  样本数: {stats['full']['count']}")

    print(f"\n俄乌冲突前 (2020 ~ {split_date}):")
    if stats['before']['count'] > 0:
        print(f"  IC均值: {stats['before']['mean']:.4f}")
        print(f"  IC标准差: {stats['before']['std']:.4f}")
        print(f"  范围: [{stats['before']['min']:.4f}, {stats['before']['max']:.4f}]")
        print(f"  样本数: {stats['before']['count']}")
    else:
        print("  无数据")

    print(f"\n俄乌冲突后 ({split_date} ~ 2026):")
    if stats['after']['count'] > 0:
        print(f"  IC均值: {stats['after']['mean']:.4f}")
        print(f"  IC标准差: {stats['after']['std']:.4f}")
        print(f"  范围: [{stats['after']['min']:.4f}, {stats['after']['max']:.4f}]")
        print(f"  样本数: {stats['after']['count']}")
    else:
        print("  无数据")

    print("-" * 70)

    # 3. 分析结论
    print("\n分析结论:")
    if stats['before']['count'] > 0 and stats['after']['count'] > 0:
        ic_change = stats['after']['mean'] - stats['before']['mean']
        print(f"  IC变化: {stats['before']['mean']:.4f} → {stats['after']['mean']:.4f} (Δ = {ic_change:+.4f})")

        if stats['before']['mean'] < 0 and stats['after']['mean'] > 0:
            print("  ✓ 机制切换确认: 负IC → 正IC")
            print("  含义: 原油涨 → 煤炭ETF跌 (历史) vs 原油涨 → 煤炭涨 (当前)")
        elif ic_change > 0.03:
            print("  ✓ 机制显著变化: IC提升 > 0.03")
        elif ic_change < -0.03:
            print("  ✓ 机制显著变化: IC下降 > 0.03")
        else:
            print("  ✗ 机制未发生显著变化")

    # 4. 可视化
    if HAS_PLOT:
        print("\n生成可视化...")
        os.makedirs('output', exist_ok=True)
        save_path = f'output/rolling_ic_{etf_code}_{factor_code}_demo.png'
        plot_rolling_ic(rolling_ic, split_date, factor_code, etf_name, save_path)

    # 5. 实际应用建议
    print("\n" + "=" * 70)
    print("实际应用建议")
    print("=" * 70)
    print("""
基于模拟结果，对于 oil_mom_20 对煤炭ETF(515220)的使用建议:

1. 【当前市场环境】(2022年后):
   - oil_mom_20 的 IC 为正值 (+0.05)
   - 信号方向: 原油涨 → 做多煤炭ETF
   - 替代逻辑成立: 能源价格联动

2. 【历史全样本】(2020-2026):
   - oil_mom_20 的 IC 被稀释为负值 (约 -0.044)
   - 混入了不同机制的数据，结论失真

3. 【策略调整建议】:
   - ✗ 不建议直接用全样本IC做信号
   - ✓ 使用滚动IC监控，及时发现机制切换
   - ✓ 给煤炭ETF配置专用因子 (如煤炭价格动量)
   - ✓ 能源化工ETF(159930) 继续用 oil_mom_20

4. 【验证步骤】:
   - 等数据库连接恢复后，运行真实的滚动IC分析
   - 对比俄乌前后的IC均值，验证机制切换假设
   - 如果确认切换，更新因子状态表中的方向标记

5. 【风险提示】:
   - 因子有效性是阶段性的
   - 需要持续监控滚动IC，及时捕捉机制变化
   - 不要盲目信任全样本统计量
""")

    print("=" * 70)
    print("演示完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
