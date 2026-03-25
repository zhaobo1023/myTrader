# -*- coding: utf-8 -*-
"""
批量ETF与oil_mom_20因子相关性分析

功能:
    选择多个有代表性的ETF，验证与原油因子的相关性
    分段统计俄乌冲突前后的IC变化
    生成对比报告

运行:
    python research/batch_etf_analysis.py
"""
import sys
import os
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False


# ============================================================
# 配置：选择要测试的ETF
# ============================================================

# 基于ETF代码和常识，选择与能源、大宗商品相关的ETF
TEST_ETFS = {
    # 能源化工类
    '159930.SZ': '能源化工ETF',
    '159981.SZ': '能源化工ETF(备用)',

    # 商品类
    '159934.SZ': '黄金ETF',
    '159985.SZ': '豆粕ETF',
    '159980.SZ': '有色ETF',

    # 其他相关
    '159937.SZ': '博时黄金',
    '159941.SZ': '纳指ETF',
    '518880.SH': '黄金ETF(沪)',

    # 对比组：不相关的ETF
    '159901.SZ': '深证100ETF',
    '159915.SZ': '创业板ETF',
    '159919.SZ': '沪深300ETF',
}

FACTOR_CODE = 'oil_mom_20'
ROLLING_WINDOW = 60
SPLIT_DATE = '2022-02-24'


# ============================================================
# 数据加载
# ============================================================

def load_factor_data(factor_code: str) -> pd.Series:
    """加载因子数据"""
    sql = """
        SELECT date, value
        FROM macro_factors
        WHERE indicator = %s
        ORDER BY date ASC
    """
    rows = execute_query(sql, [factor_code], env='online')

    if not rows:
        return pd.Series()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.set_index('date').sort_index()

    return df['value']


def load_etf_data(etf_code: str) -> pd.Series:
    """从 trade_etf_daily 加载ETF数据"""
    sql = """
        SELECT trade_date, close_price
        FROM trade_etf_daily
        WHERE fund_code = %s
        ORDER BY trade_date ASC
    """
    rows = execute_query(sql, [etf_code], env='online')

    if not rows:
        return pd.Series()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
    df = df.set_index('trade_date').sort_index()

    return df['close_price']


# ============================================================
# IC计算
# ============================================================

def calc_rolling_ic_ts(factor: pd.Series,
                       etf_price: pd.Series,
                       window: int = 60) -> pd.Series:
    """计算时序滚动IC"""
    # 对齐日期
    aligned = pd.DataFrame({
        'factor': factor,
        'price': etf_price
    }).dropna()

    if len(aligned) < window:
        return pd.Series()

    # 计算未来收益
    aligned['forward_ret'] = aligned['price'].shift(-window) / aligned['price'] - 1
    aligned = aligned.dropna()

    if len(aligned) < window:
        return pd.Series()

    # 计算滚动IC
    rolling_ic = aligned['factor'].rolling(window=window).corr(aligned['forward_ret'])

    return rolling_ic.dropna()


def analyze_periods(rolling_ic: pd.Series, split_date: str) -> dict:
    """分段统计IC"""
    split_dt = pd.to_datetime(split_date)

    before = rolling_ic[rolling_ic.index < split_dt]
    after = rolling_ic[rolling_ic.index >= split_dt]

    return {
        'before': {
            'mean': before.mean() if len(before) > 0 else None,
            'std': before.std() if len(before) > 0 else None,
            'count': len(before),
        },
        'after': {
            'mean': after.mean() if len(after) > 0 else None,
            'std': after.std() if len(after) > 0 else None,
            'count': len(after),
        },
        'full': {
            'mean': rolling_ic.mean(),
            'std': rolling_ic.std(),
            'count': len(rolling_ic),
        }
    }


# ============================================================
# 批量分析
# ============================================================

def batch_analyze(etf_list: dict, factor_code: str, window: int, split_date: str):
    """批量分析多个ETF"""
    print("=" * 80)
    print(f"批量ETF分析: {factor_code} 因子相关性验证")
    print("=" * 80)
    print(f"滚动窗口: {window} 交易日")
    print(f"分割点: {split_date} (俄乌冲突)")
    print(f"ETF数量: {len(etf_list)}")
    print()

    # 加载因子数据
    print("加载因子数据...")
    factor = load_factor_data(factor_code)
    if factor.empty:
        print("  错误: 未找到因子数据")
        return None

    print(f"  {len(factor)} 条记录 ({factor.index.min().date()} ~ {factor.index.max().date()})")

    # 批量分析ETF
    results = []

    for etf_code, etf_name in etf_list.items():
        print(f"\n分析 {etf_code} ({etf_name})...")

        # 加载ETF数据
        etf_price = load_etf_data(etf_code)
        if etf_price.empty:
            print(f"  跳过: 无数据")
            continue

        print(f"  {len(etf_price)} 条价格记录")

        # 计算滚动IC
        rolling_ic = calc_rolling_ic_ts(factor, etf_price, window)
        if rolling_ic.empty:
            print(f"  跳过: 计算失败")
            continue

        # 分段统计
        stats = analyze_periods(rolling_ic, split_date)

        print(f"  全样本IC: {stats['full']['mean']:.4f}")
        before_ic_str = f"{stats['before']['mean']:.4f}" if stats['before']['mean'] is not None else 'N/A'
        after_ic_str = f"{stats['after']['mean']:.4f}" if stats['after']['mean'] is not None else 'N/A'
        print(f"  俄乌前IC: {before_ic_str}")
        print(f"  俄乌后IC: {after_ic_str}")

        # 计算IC变化
        ic_change = None
        if stats['before']['mean'] and stats['after']['mean']:
            ic_change = stats['after']['mean'] - stats['before']['mean']
            print(f"  IC变化: {ic_change:+.4f}")

        results.append({
            'etf_code': etf_code,
            'etf_name': etf_name,
            'full_ic': stats['full']['mean'],
            'full_std': stats['full']['std'],
            'full_count': stats['full']['count'],
            'before_ic': stats['before']['mean'],
            'before_count': stats['before']['count'],
            'after_ic': stats['after']['mean'],
            'after_count': stats['after']['count'],
            'ic_change': ic_change,
        })

    return pd.DataFrame(results)


def generate_report(results_df: pd.DataFrame, output_dir: str = 'output'):
    """生成分析报告"""
    if results_df.empty:
        print("无结果数据")
        return

    print("\n" + "=" * 80)
    print("分析结果汇总")
    print("=" * 80)

    # 按全样本IC绝对值排序
    results_df = results_df.sort_values('full_ic', key=abs, ascending=False)

    print(f"\n{'ETF代码':<12} {'名称':<20} {'全样本IC':<10} {'俄乌前IC':<10} {'俄乌后IC':<10} {'IC变化':<10}")
    print("-" * 80)

    for _, row in results_df.iterrows():
        before_ic = f"{row['before_ic']:.4f}" if row['before_ic'] else 'N/A'
        after_ic = f"{row['after_ic']:.4f}" if row['after_ic'] else 'N/A'
        ic_change = f"{row['ic_change']:+.4f}" if row['ic_change'] else 'N/A'

        print(f"{row['etf_code']:<12} {row['etf_name']:<20} "
              f"{row['full_ic']:>10.4f} {before_ic:>10} {after_ic:>10} {ic_change:>10}")

    print("-" * 80)

    # 保存结果
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, 'batch_etf_analysis.csv')
    results_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n结果已保存: {csv_path}")

    # 可视化
    if HAS_PLOT and len(results_df) > 0:
        plot_results(results_df, output_dir)


def plot_results(results_df: pd.DataFrame, output_dir: str):
    """可视化结果"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # 子图1: IC对比柱状图
    etf_names = results_df['etf_name'].tolist()
    x = np.arange(len(etf_names))
    width = 0.35

    before_ics = [row['before_ic'] if row['before_ic'] else 0 for _, row in results_df.iterrows()]
    after_ics = [row['after_ic'] if row['after_ic'] else 0 for _, row in results_df.iterrows()]

    ax1.bar(x - width/2, before_ics, width, label='俄乌前 (2020-2022.02)', alpha=0.8)
    ax1.bar(x + width/2, after_ics, width, label='俄乌后 (2022.02-2026)', alpha=0.8)

    ax1.set_xlabel('ETF', fontsize=12)
    ax1.set_ylabel('IC均值', fontsize=12)
    ax1.set_title('oil_mom_20 对各ETF的IC对比 (分段)', fontsize=14, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(etf_names, rotation=45, ha='right', fontsize=9)
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.8)

    # 子图2: IC变化柱状图
    ic_changes = [row['ic_change'] if row['ic_change'] else 0 for _, row in results_df.iterrows()]
    colors = ['green' if x > 0 else 'red' for x in ic_changes]

    ax2.bar(x, ic_changes, color=colors, alpha=0.7)
    ax2.set_xlabel('ETF', fontsize=12)
    ax2.set_ylabel('IC变化 (俄乌后 - 俄乌前)', fontsize=12)
    ax2.set_title('机制切换: IC变化量', fontsize=14, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(etf_names, rotation=45, ha='right', fontsize=9)
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)

    plt.tight_layout()

    save_path = os.path.join(output_dir, 'batch_etf_analysis.png')
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"图表已保存: {save_path}")
    plt.close()


# ============================================================
# 主函数
# ============================================================

def main():
    print("\n批量ETF与oil_mom_20因子相关性分析")
    print("=" * 80)

    # 批量分析
    results_df = batch_analyze(TEST_ETFS, FACTOR_CODE, ROLLING_WINDOW, SPLIT_DATE)

    # 生成报告
    if results_df is not None and not results_df.empty:
        generate_report(results_df)

    print("\n" + "=" * 80)
    print("分析完成!")
    print("=" * 80)


if __name__ == "__main__":
    main()
