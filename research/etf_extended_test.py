# -*- coding: utf-8 -*-
"""
ETF 扩展测试模块 (ETF Extended Test)

在更多 ETF 上测试 oil_mom_20 因子的表现，验证因子的跨标的泛化能力。

测试目标:
    - 能源化工ETF (159930): 已测，ICIR=-0.69
    - 煤炭ETF (515220): 原油-煤炭替代逻辑
    - 黄金ETF (518880): 应该相关性低
    - 恒生科技ETF (513130): 应该基本无关
    - 电力ETF (159611): 新增
    - 电池ETF (159755): 新增
    - 畜牧ETF (159865): 新增
    - 农产品ETF (159929): 新增

运行:
    python research/etf_extended_test.py
    python research/etf_extended_test.py --factor oil_mom_20
"""
import sys
import os
import argparse
from datetime import date, timedelta
from typing import List, Optional, Dict, Tuple
import warnings

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query, get_connection

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False
    print("警告: matplotlib 或 seaborn 未安装")


# ============================================================
# 配置
# ============================================================

# 扩展 ETF 列表 (使用完整代码格式: 代码.交易所)
EXTENDED_ETFS = {
    # 能源相关
    '159930.SZ': '能源化工ETF',
    '515220.SH': '煤炭ETF',
    '159825.SZ': '有色金属ETF',
    # 新能源相关
    '159871.SZ': '新能源ETF',
    '515030.SH': '新能源ETF',
    '515160.SH': '新能源ETF',
    '159806.SZ': '新能源车ETF',
    '516110.SH': '汽车ETF',
    # 电力相关
    '159611.SZ': '电力ETF',
    '516850.SH': '储能ETF',
    # 光伏/电池相关
    '159755.SZ': '电池ETF',
    '159766.SZ': '光伏ETF',
    '516790.SH': '光伏ETF',
    # 其他
    '518880.SH': '黄金ETF',
    '513130.SH': '恒生科技ETF',
    '159929.SZ': '农产品ETF',
    '159865.SZ': '畜牧ETF',
    '515180.SH': '银行ETF',
}

# 默认测试因子
DEFAULT_FACTOR = 'oil_mom_20'

# 预测窗口
FORWARD_WINDOWS = [5, 10, 20]

# 滚动 IC 窗口
ROLLING_IC_WINDOW = 60


# ============================================================
# 数据加载
# ============================================================

def load_etf_data(etf_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    从数据库加载 ETF 日线数据

    Args:
        etf_code: ETF 代码
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)

    Returns:
        DataFrame: index=date, columns=[close]
    """
    sql = """
        SELECT trade_date, close_price
        FROM trade_etf_daily
        WHERE fund_code = %s
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
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')

    return df[['close_price']].rename(columns={'close_price': 'close'})


def load_factor_data(factor_code: str, start_date: str = None, end_date: str = None) -> pd.Series:
    """
    从数据库加载因子数据

    Args:
        factor_code: 因子代码
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        Series: index=date, values=factor_value
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
    df = df.set_index('date')

    return df['value']


# ============================================================
# IC 计算
# ============================================================

def calc_forward_returns(prices: pd.Series, window: int) -> pd.Series:
    """
    计算未来 N 日收益率

    Args:
        prices: 价格序列
        window: 窗口期

    Returns:
        Series: 未来 N 日收益率
    """
    forward_ret = prices.shift(-window) / prices - 1
    return forward_ret


def calc_time_series_ic(factor: pd.Series, forward_ret: pd.Series) -> Tuple[float, float, int]:
    """
    计算时序 IC (Pearson 相关系数)

    Args:
        factor: 因子值序列
        forward_ret: 未来收益率序列

    Returns:
        (IC, ICIR, 样本数)
    """
    # 对齐日期
    aligned = pd.DataFrame({'factor': factor, 'ret': forward_ret}).dropna()

    if len(aligned) < 10:
        return np.nan, np.nan, 0

    # 计算 IC (Pearson 相关系数)
    ic = aligned['factor'].corr(aligned['ret'], method='pearson')

    # 计算滚动 ICIR
    rolling_ic = aligned['factor'].rolling(ROLLING_IC_WINDOW).corr(aligned['ret'])
    icir = rolling_ic.mean() / (rolling_ic.std() + 1e-10)

    return ic, icir, len(aligned)


# ============================================================
# 测试单个 ETF
# ============================================================

def test_single_etf(
    etf_code: str,
    etf_name: str,
    factor_code: str,
    forward_windows: List[int] = None,
    start_date: str = None,
    end_date: str = None
) -> List[Dict]:
    """
    测试单个 ETF 与因子的相关性

    Args:
        etf_code: ETF 代码
        etf_name: ETF 名称
        factor_code: 因子代码
        forward_windows: 预测窗口列表
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        测试结果列表
    """
    if forward_windows is None:
        forward_windows = FORWARD_WINDOWS

    print(f"\n测试: {etf_name} ({etf_code})")

    # 加载 ETF 数据
    etf_df = load_etf_data(etf_code, start_date, end_date)
    if etf_df.empty:
        print(f"  [警告] 未找到 ETF 数据")
        return []

    print(f"  ETF 数据: {len(etf_df)} 条, {etf_df.index.min().date()} ~ {etf_df.index.max().date()}")

    # 加载因子数据
    factor = load_factor_data(factor_code, start_date, end_date)
    if factor.empty:
        print(f"  [警告] 未找到因子数据")
        return []

    print(f"  因子数据: {len(factor)} 条, {factor.index.min().date()} ~ {factor.index.max().date()}")

    results = []

    # 对每个预测窗口
    for fwd_window in forward_windows:
        # 计算未来收益
        forward_ret = calc_forward_returns(etf_df['close'], fwd_window)

        # 计算 IC
        ic, icir, sample_cnt = calc_time_series_ic(factor, forward_ret)

        result = {
            'etf_code': etf_code,
            'etf_name': etf_name,
            'factor_code': factor_code,
            'forward_window': fwd_window,
            'ic': ic,
            'icir': icir,
            'sample_count': sample_cnt
        }
        results.append(result)

        status = "✓" if not np.isnan(ic) else "✗"
        print(f"  {status} T+{fwd_window}: IC={ic:.4f}, ICIR={icir:.4f}, N={sample_cnt}")

    return results


# ============================================================
# 测试所有 ETF
# ============================================================

def test_all_etfs(
    etf_codes: List[str] = None,
    factor_code: str = DEFAULT_FACTOR,
    forward_windows: List[int] = None,
    start_date: str = None,
    end_date: str = None
) -> List[Dict]:
    """
    测试所有 ETF 与因子的相关性

    Args:
        etf_codes: ETF 代码列表
        factor_code: 因子代码
        forward_windows: 预测窗口列表
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        测试结果列表
    """
    if etf_codes is None:
        etf_codes = list(EXTENDED_ETFS.keys())
    if forward_windows is None:
        forward_windows = FORWARD_WINDOWS

    all_results = []

    for etf_code in etf_codes:
        etf_name = EXTENDED_ETFS.get(etf_code, etf_code)
        results = test_single_etf(
            etf_code, etf_name, factor_code,
            forward_windows, start_date, end_date
        )
        all_results.extend(results)

    return all_results


# ============================================================
# 结果汇总
# ============================================================

def generate_summary_table(all_results: List[Dict]) -> pd.DataFrame:
    """
    生成汇总表格

    Args:
        all_results: 测试结果列表

    Returns:
        DataFrame: 汇总表格
    """
    rows = []
    for result in all_results:
        rows.append({
            'ETF': result['etf_name'],
            '预测窗口': f"T+{result['forward_window']}",
            'IC': result['ic'],
            'ICIR': result['icir'],
            '样本数': result['sample_count'],
        })

    df = pd.DataFrame(rows)
    return df.sort_values('ICIR', key=lambda x: abs(x), ascending=False)


def generate_pivot_table(all_results: List[Dict]) -> pd.DataFrame:
    """
    生成透视表 (ETF x 预测窗口)

    Args:
        all_results: 测试结果列表

    Returns:
        DataFrame: 透视表
    """
    rows = []
    for result in all_results:
        rows.append({
            'ETF': result['etf_name'],
            '预测窗口': f"T+{result['forward_window']}",
            'IC': result['ic'],
            'ICIR': result['icir'],
        })

    df = pd.DataFrame(rows)

    # 透视表 - IC
    ic_pivot = df.pivot_table(index='ETF', columns='预测窗口', values='IC')

    return ic_pivot


# ============================================================
# 可视化
# ============================================================

def plot_ic_comparison(all_results: List[Dict], save_path: str = None):
    """
    绘制 IC 对比图

    Args:
        all_results: 测试结果列表
        save_path: 保存路径
    """
    if not HAS_PLOT:
        return

    # 准备数据
    etf_names = list(set(r['etf_name'] for r in all_results))
    windows = sorted(set(r['forward_window'] for r in all_results))

    fig, axes = plt.subplots(1, len(windows), figsize=(15, 6), sharey=True)

    if len(windows) == 1:
        axes = [axes]

    for idx, window in enumerate(windows):
        ax = axes[idx]

        # 过滤当前窗口的数据
        window_results = [r for r in all_results if r['forward_window'] == window]

        etfs = [r['etf_name'] for r in window_results]
        ics = [r['ic'] for r in window_results]
        icirs = [r['icir'] for r in window_results]

        # 绘制条形图
        colors = ['green' if ic < 0 else 'red' for ic in ics]
        bars = ax.barh(etfs, ics, color=colors, alpha=0.7)

        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('IC')
        ax.set_title(f'T+{window}')

        # 添加数值标签
        for bar, ic, icir in zip(bars, ics, icirs):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f'{ic:.3f}\n(ICIR:{icir:.2f})',
                   ha='left' if width > 0 else 'right',
                   va='center', fontsize=8)

    plt.suptitle(f'{all_results[0]["factor_code"]} 因子在多个 ETF 上的 IC 对比')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  图表已保存: {save_path}")

    plt.close()


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='ETF 扩展测试')
    parser.add_argument('--etf', type=str, nargs='+', help='ETF 代码列表')
    parser.add_argument('--factor', type=str, default=DEFAULT_FACTOR, help='因子代码')
    parser.add_argument('--start', type=str, help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    args = parser.parse_args()

    print("=" * 70)
    print("ETF 扩展测试模块")
    print("=" * 70)

    # 参数
    etf_codes = args.etf if args.etf else list(EXTENDED_ETFS.keys())

    print(f"\n测试参数:")
    print(f"  ETF: {etf_codes}")
    print(f"  因子: {args.factor}")
    print(f"  区间: {args.start or '最早'} ~ {args.end or '最新'}")

    # 执行测试
    print("\n" + "-" * 70)
    all_results = test_all_etfs(
        etf_codes=etf_codes,
        factor_code=args.factor,
        start_date=args.start,
        end_date=args.end
    )

    if not all_results:
        print("测试结果为空")
        return

    # 生成汇总表
    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    summary_df = generate_summary_table(all_results)
    print("\n" + summary_df.to_string(index=False))

    # 生成透视表
    print("\n" + "-" * 70)
    print("IC 透视表 (ETF x 预测窗口)")
    print("-" * 70)
    ic_pivot = generate_pivot_table(all_results)
    print(ic_pivot.round(4).to_string())

    # 创建输出目录
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    # 保存汇总表
    summary_path = os.path.join(output_dir, f'{args.factor}_etf_test_summary.csv')
    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    print(f"\n汇总表已保存: {summary_path}")

    # 绘图
    if HAS_PLOT:
        print("\n生成可视化图表...")
        plot_path = os.path.join(output_dir, f'{args.factor}_etf_ic_comparison.png')
        try:
            plot_ic_comparison(all_results, save_path=plot_path)
        except Exception as e:
            print(f"  图表生成失败: {e}")

    # 分析结论
    print("\n" + "=" * 70)
    print("分析结论")
    print("=" * 70)

    # 找出显著 IC 的 ETF
    significant_results = [r for r in all_results if abs(r.get('ic', 0)) > 0.03]

    if significant_results:
        print(f"\n显著 IC (|IC| > 0.03) 的 ETF:")
        for r in sorted(significant_results, key=lambda x: abs(x.get('ic', 0)), reverse=True):
            print(f"  - {r['etf_name']} (T+{r['forward_window']}): IC={r['ic']:.4f}, ICIR={r['icir']:.4f}")
    else:
        print("\n无显著 IC 的 ETF")

    print("\n" + "=" * 70)
    print("✅ 测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
