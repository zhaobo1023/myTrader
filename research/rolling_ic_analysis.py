# -*- coding: utf-8 -*-
"""
滚动IC分析 - 验证机制切换假设

功能:
    计算 oil_mom_20 对煤炭ETF(515220)的滚动IC
    分段统计俄乌冲突前后的IC均值
    验证因子有效性是否在2022年后发生切换

运行:
    python research/rolling_ic_analysis.py
"""
import sys
import os
from datetime import datetime
from typing import Tuple

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query, switch_env

# 尝试切换到本地数据库
try:
    switch_env('local')
    print("已切换到本地数据库环境")
except Exception as e:
    print(f"切换数据库环境失败: {e}")

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False
    print("警告: matplotlib 未安装")


# ============================================================
# 数据加载
# ============================================================

def load_factor_data(factor_code: str,
                     start_date: str = None,
                     end_date: str = None) -> pd.Series:
    """
    从数据库加载因子数据

    Returns:
        Series with index=date, values=factor_value
    """
    sql = """
        SELECT date, value
        FROM macro_factors
        WHERE indicator = %s
    """
    params = [factor_code]

    if start_date:
        sql += " AND date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND date <= %s"
        params.append(end_date)

    sql += " ORDER BY date ASC"

    rows = execute_query(sql, params)

    if not rows:
        return pd.Series()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.set_index('date').sort_index()

    return df['value']


def load_etf_data(etf_code: str,
                  start_date: str = None,
                  end_date: str = None) -> pd.Series:
    """
    从数据库加载ETF价格数据

    Returns:
        Series with index=date, values=close_price
    """
    sql = """
        SELECT trade_date, close_price
        FROM etf_daily
        WHERE etf_code = %s
    """
    params = [etf_code]

    if start_date:
        sql += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND trade_date <= %s"
        params.append(end_date)

    sql += " ORDER BY trade_date ASC"

    rows = execute_query(sql, params)

    if not rows:
        return pd.Series()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
    df = df.set_index('trade_date').sort_index()

    return df['close_price']


# ============================================================
# 滚动IC计算
# ============================================================

def calc_rolling_ic_ts(factor: pd.Series,
                       etf_price: pd.Series,
                       window: int = 60) -> pd.Series:
    """
    计算时序滚动IC (Pearson相关系数)

    Args:
        factor: 因子值序列
        etf_price: ETF价格序列
        window: 滚动窗口 (交易日)

    Returns:
        滚动IC序列
    """
    # 对齐日期
    aligned = pd.DataFrame({
        'factor': factor,
        'price': etf_price
    }).dropna()

    if len(aligned) < window:
        print(f"数据不足: {len(aligned)} < {window}")
        return pd.Series()

    # 计算未来收益 (T+1 到 T+window 的累计收益)
    # 这里用window日后的收益作为预测目标
    aligned['forward_ret'] = aligned['price'].shift(-window) / aligned['price'] - 1

    # 移除未来收益为NaN的行
    aligned = aligned.dropna()

    if len(aligned) < window:
        print(f"对齐后数据不足: {len(aligned)} < {window}")
        return pd.Series()

    # 计算滚动IC (滚动窗口内的Pearson相关系数)
    def rolling_corr(x):
        if len(x) < window:
            return np.nan
        # 取窗口内的数据
        window_data = aligned.loc[x.index]
        return window_data['factor'].corr(window_data['forward_ret'], method='pearson')

    # 使用滚动窗口计算
    # 注意: pandas的rolling().corr()需要两个Series
    rolling_ic = aligned['factor'].rolling(window=window).corr(aligned['forward_ret'])

    return rolling_ic.dropna()


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
    ax1.plot(rolling_ic.index, rolling_ic.values, label='Rolling IC', linewidth=1.5)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.8, alpha=0.5)
    ax1.axvline(x=pd.to_datetime(split_date), color='red', linestyle='--',
                linewidth=2, label=f'俄乌冲突 ({split_date})')

    # 标记正负区域
    ax1.fill_between(rolling_ic.index, rolling_ic.values, 0,
                     where=(rolling_ic.values > 0), alpha=0.3, color='green', label='正IC')
    ax1.fill_between(rolling_ic.index, rolling_ic.values, 0,
                     where=(rolling_ic.values < 0), alpha=0.3, color='red', label='负IC')

    ax1.set_title(f'{factor_name} 对 {etf_name} 的滚动IC (60日窗口)',
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
    ax2.set_title('分段IC均值对比', fontsize=14, fontweight='bold')
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
    print("滚动IC分析 - 验证机制切换假设")
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

    # 1. 加载数据
    print("\n加载因子数据...")
    factor = load_factor_data(factor_code)
    print(f"  {len(factor)} 条记录 ({factor.index.min().date()} ~ {factor.index.max().date()})")

    print("\n加载ETF数据...")
    etf_price = load_etf_data(etf_code)
    if len(etf_price) == 0:
        print(f"  警告: 未找到ETF {etf_code} 的数据")
        return
    print(f"  {len(etf_price)} 条记录 ({etf_price.index.min().date()} ~ {etf_price.index.max().date()})")

    # 2. 计算滚动IC
    print("\n计算滚动IC...")
    rolling_ic = calc_rolling_ic_ts(factor, etf_price, window)

    if rolling_ic.empty:
        print("  计算失败，数据不足")
        return

    print(f"  {len(rolling_ic)} 条IC记录")

    # 3. 分段统计
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

    # 4. 分析结论
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

    # 5. 可视化
    if HAS_PLOT:
        print("\n生成可视化...")
        os.makedirs('output', exist_ok=True)
        save_path = f'output/rolling_ic_{etf_code}_{factor_code}_{window}.png'
        plot_rolling_ic(rolling_ic, split_date, factor_code, etf_name, save_path)

    print("\n" + "=" * 70)
    print("分析完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
