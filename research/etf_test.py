# -*- coding: utf-8 -*-
"""
ETF 因子测试模块 (ETF Factor Test)

功能:
    1. 测试宏观因子对 ETF 的预测力
    2. 使用时序 IC (Pearson 相关系数)，    3. 输出相关性矩阵热力图和滚动 IC 图

输入:
    - ETF 代码列表
    - 因子名称列表
    - 测试区间

输出:
    - 每个 (ETF, 因子) 组合的 IC 值、 ICIR
    - 相关性矩阵热力图
    - 滚动 IC 折线图

运行:
    python research/etf_test.py

注意:
    这里使用的是时序 IC (单标的的时间序列相关)，不是截面 IC
"""
import sys
import os
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
    print("警告: matplotlib 或 seaborn 未安装，请运行 pip install matplotlib seaborn")


# ============================================================
# 配置
# ============================================================

# 默认 ETF 列表
DEFAULT_ETFS = {
    '159930': '能源化工ETF',
    '515220': '煤炭ETF',
    '518880': '黄金ETF',
    '513130': '恒生科技ETF',
}

# 默认宏观因子列表
DEFAULT_FACTORS = {
    'oil_mom_20': '原油20日涨跌幅',
    'gold_mom_20': '黄金20日涨跌幅',
    'vix_ma5': 'VIX 5日均值',
    'north_flow_5d': '北向资金5日累计净流入',
}

# 测试窗口
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
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date')
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')

    return df[['close_price']].rename(columns={'close_price': 'close'})


def load_macro_factors(factor_codes: List[str] = None, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    从数据库加载宏观因子数据

    Args:
        factor_codes: 因子代码列表
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        DataFrame: index=date, columns=[factor1, factor2, ...]
    """
    if factor_codes is None:
        factor_codes = list(DEFAULT_FACTORS.keys())

    # 加载所有因子
    sql = """
        SELECT date, indicator, value
        FROM macro_factors
        WHERE indicator IN ({})
    """.format(','.join(['%s'] * len(factor_codes)))

    params = list(factor_codes)

    if start_date:
        sql += " AND date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND date <= %s"
        params.append(end_date)

    sql += " ORDER BY date ASC"

    rows = execute_query(sql, params)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')

    # 透视表
    df = df.pivot_table(index='date', columns='indicator', values='value')

    return df


# ============================================================
# 因子测试核心逻辑
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
    # 未来收益 = (P_t+N - P_t) / P_t
    forward_ret = prices.shift(-window) / prices - 1
    return forward_ret


def calc_time_series_ic(factor: pd.Series, forward_ret: pd.Series) -> Tuple[float, int]:
    """
    计算时序 IC (Pearson 相关系数)

    Args:
        factor: 因子值序列
        forward_ret: 未来收益率序列

    Returns:
        (IC值, 样本数)
    """
    # 对齐日期
    aligned = pd.DataFrame({'factor': factor, 'ret': forward_ret}).dropna()

    if len(aligned) < 10:
        return np.nan, 0

    # 计算 Pearson 相关系数
    ic = aligned['factor'].corr(aligned['ret'], method='pearson')

    return ic, len(aligned)


def calc_rolling_ic(factor: pd.Series, forward_ret: pd.Series, window: int = 60) -> pd.Series:
    """
    计算滚动 IC

    Args:
        factor: 因子值序列
        forward_ret: 未来收益率序列
        window: 滚动窗口

    Returns:
        Series: 滚动 IC 序列
    """
    # 对齐日期
    aligned = pd.DataFrame({'factor': factor, 'ret': forward_ret}).dropna()

    if len(aligned) < window:
        return pd.Series()

    # 滚动计算相关系数
    def rolling_corr(x):
        if len(x) < 2:
            return np.nan
        return x['factor'].corr(x['ret'])

    # 使用滚动窗口
    rolling_ic = aligned.rolling(window=window).apply(
        lambda x: pd.Series(x).corr(aligned.loc[pd.Series(x).index, 'ret'])
        if len(x) >= 2 else np.nan,
        raw=False
    )

    # 更简单的方法
    rolling_ic = pd.Series(index=aligned.index, dtype=float)
    for i in range(window, len(aligned)):
        subset = aligned.iloc[i-window:i]
        if len(subset) >= 2:
            rolling_ic.iloc[i] = subset['factor'].corr(subset['ret'])

    return rolling_ic.dropna()


def calc_icir(rolling_ic: pd.Series) -> float:
    """
    计算 ICIR (IC均值 / IC标准差)

    Args:
        rolling_ic: 滚动 IC 序列

    Returns:
        ICIR 值
    """
    if rolling_ic.empty or len(rolling_ic) < 2:
        return np.nan

    ic_mean = rolling_ic.mean()
    ic_std = rolling_ic.std()

    if ic_std == 0 or np.isnan(ic_std):
        return np.nan

    return ic_mean / ic_std


# ============================================================
# 测试单个 ETF
# ============================================================

def test_etf_factors(
    etf_code: str,
    factor_codes: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    forward_windows: List[int] = None,
    rolling_window: int = 60
) -> Dict:
    """
    测试单个 ETF 与所有因子的相关性

    Args:
        etf_code: ETF 代码
        factor_codes: 因子代码列表
        start_date: 起始日期
        end_date: 结束日期
        forward_windows: 未来收益窗口列表
        rolling_window: 滚动 IC 窗口

    Returns:
        测试结果字典
    """
    if factor_codes is None:
        factor_codes = list(DEFAULT_FACTORS.keys())
    if forward_windows is None:
        forward_windows = FORWARD_WINDOWS

    etf_name = DEFAULT_ETFS.get(etf_code, etf_code)

    print(f"\n测试 ETF: {etf_name} ({etf_code})")

    # 加载 ETF 数据
    etf_df = load_etf_data(etf_code, start_date, end_date)
    if etf_df.empty:
        print(f"  未找到 ETF 数据")
        return {}

    print(f"  ETF 数据: {len(etf_df)} 条, {etf_df.index.min()} ~ {etf_df.index.max()}")

    # 加载因子数据
    factors_df = load_macro_factors(factor_codes, start_date, end_date)
    if factors_df.empty:
        print(f"  未找到因子数据")
        return {}

    print(f"  因子数据: {len(factors_df)} 条, {factors_df.index.min()} ~ {factors_df.index.max()}")

    results = {}

    # 对每个预测窗口
    for fwd_window in forward_windows:
        # 计算未来收益
        forward_ret = calc_forward_returns(etf_df['close'], fwd_window)

        # 对每个因子
        for factor_code in factor_codes:
            if factor_code not in factors_df.columns:
                continue

            factor = factors_df[factor_code]

            # 计算时序 IC
            ic, sample_cnt = calc_time_series_ic(factor, forward_ret)

            # 计算滚动 IC
            rolling_ic = calc_rolling_ic(factor, forward_ret, rolling_window)

            # 计算 ICIR
            icir = calc_icir(rolling_ic)

            # IC 均值
            ic_mean = rolling_ic.mean() if not rolling_ic.empty else np.nan

            key = (etf_code, factor_code, fwd_window)
            results[key] = {
                'etf_code': etf_code,
                'etf_name': etf_name,
                'factor_code': factor_code,
                'factor_name': DEFAULT_FACTORS.get(factor_code, factor_code),
                'forward_window': fwd_window,
                'ic': ic,
                'ic_mean': ic_mean,
                'icir': icir,
                'sample_count': sample_cnt,
                'rolling_ic': rolling_ic,
            }

            status = "✓" if not np.isnan(ic) else "✗"
            print(f"  {status} {factor_code} (T+{fwd_window}): IC={ic:.4f}, ICIR={icir:.4f}, N={sample_cnt}")

    return results


# ============================================================
# 测试所有 ETF
# ============================================================

def test_all_etfs(
    etf_codes: List[str] = None,
    factor_codes: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    forward_windows: List[int] = None,
    rolling_window: int = 60
) -> Dict:
    """
    测试所有 ETF 与所有因子的相关性

    Args:
        etf_codes: ETF 代码列表
        factor_codes: 因子代码列表
        start_date: 起始日期
        end_date: 结束日期
        forward_windows: 未来收益窗口列表
        rolling_window: 滚动 IC 窗口

    Returns:
        测试结果字典
    """
    if etf_codes is None:
        etf_codes = list(DEFAULT_ETFS.keys())
    if factor_codes is None:
        factor_codes = list(DEFAULT_FACTORS.keys())
    if forward_windows is None:
        forward_windows = FORWARD_WINDOWS

    all_results = {}

    for etf_code in etf_codes:
        results = test_etf_factors(
            etf_code, factor_codes, start_date, end_date,
            forward_windows, rolling_window
        )
        all_results.update(results)

    return all_results


# ============================================================
# 结果汇总与可视化
# ============================================================

def generate_summary_table(all_results: Dict) -> pd.DataFrame:
    """
    生成汇总表格

    Args:
        all_results: 测试结果字典

    Returns:
        DataFrame: 汇总表格
    """
    rows = []
    for key, result in all_results.items():
        rows.append({
            'ETF': result['etf_name'],
            '因子': result['factor_name'],
            '预测窗口': f"T+{result['forward_window']}",
            'IC': result['ic'],
            'IC均值': result['ic_mean'],
            'ICIR': result['icir'],
            '样本数': result['sample_count'],
        })

    df = pd.DataFrame(rows)
    return df.sort_values('IC', key=lambda x: abs(x), ascending=False)


def plot_ic_heatmap(all_results: Dict, forward_window: int = 5, save_path: str = None):
    """
    绘制 IC 热力图

    Args:
        all_results: 测试结果字典
        forward_window: 预测窗口
        save_path: 保存路径
    """
    if not HAS_PLOT:
        print("无法绘图: matplotlib 未安装")
        return

    # 过滤指定窗口的结果
    filtered = {k: v for k, v in all_results.items() if v['forward_window'] == forward_window}

    if not filtered:
        print(f"无 T+{forward_window} 的数据")
        return

    # 构建矩阵
    etf_names = list(set(v['etf_name'] for v in filtered.values()))
    factor_names = list(set(v['factor_name'] for v in filtered.values()))

    ic_matrix = pd.DataFrame(index=etf_names, columns=factor_names, dtype=float)

    for result in filtered.values():
        ic_matrix.loc[result['etf_name'], result['factor_name']] = result['ic']

    # 绘图
    plt.figure(figsize=(10, 6))
    sns.heatmap(ic_matrix.astype(float), annot=True, fmt='.3f', cmap='RdYlGn_r',
                center=0, vmin=-0.3, vmax=0.3)
    plt.title(f'宏观因子与 ETF 未来 {forward_window} 日收益 IC 热力图')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"热力图已保存: {save_path}")
    else:
        plt.show()

    plt.close()


def plot_rolling_ic(all_results: Dict, etf_code: str, factor_code: str, save_path: str = None):
    """
    绘制滚动 IC 折线图

    Args:
        all_results: 测试结果字典
        etf_code: ETF 代码
        factor_code: 因子代码
        save_path: 保存路径
    """
    if not HAS_PLOT:
        print("无法绘图: matplotlib 未安装")
        return

    # 查找对应结果
    key = None
    for k, v in all_results.items():
        if v['etf_code'] == etf_code and v['factor_code'] == factor_code:
            key = k
            break

    if key is None:
        print(f"未找到 {etf_code} - {factor_code} 的结果")
        return

    result = all_results[key]
    rolling_ic = result['rolling_ic']

    if rolling_ic.empty:
        print("无滚动 IC 数据")
        return

    plt.figure(figsize=(12, 5))
    plt.plot(rolling_ic.index, rolling_ic.values, 'b-', alpha=0.7, label='Rolling IC')
    plt.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    plt.axhline(y=rolling_ic.mean(), color='r', linestyle='--', label=f'Mean IC: {rolling_ic.mean():.3f}')

    plt.fill_between(rolling_ic.index, rolling_ic.values, 0, where=rolling_ic.values > 0,
                     color='green', alpha=0.3)
    plt.fill_between(rolling_ic.index, rolling_ic.values, 0, where=rolling_ic.values < 0,
                     color='red', alpha=0.3)

    plt.title(f"{result['etf_name']} - {result['factor_name']} 滚动 IC (60日)")
    plt.xlabel('日期')
    plt.ylabel('IC')
    plt.legend()
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"滚动 IC 图已保存: {save_path}")
    else:
        plt.show()

    plt.close()


# ============================================================
# 主函数
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='ETF 因子测试')
    parser.add_argument('--etf', type=str, nargs='+', help='ETF 代码列表')
    parser.add_argument('--factor', type=str, nargs='+', help='因子代码列表')
    parser.add_argument('--start', type=str, help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    args = parser.parse_args()

    print("=" * 70)
    print("ETF 因子测试模块")
    print("=" * 70)

    # 参数
    etf_codes = args.etf if args.etf else list(DEFAULT_ETFS.keys())
    factor_codes = args.factor if args.factor else list(DEFAULT_FACTORS.keys())

    print(f"\n测试参数:")
    print(f"  ETF: {etf_codes}")
    print(f"  因子: {factor_codes}")
    print(f"  区间: {args.start or '最早'} ~ {args.end or '最新'}")

    # 执行测试
    print("\n" + "-" * 70)
    all_results = test_all_etfs(
        etf_codes=etf_codes,
        factor_codes=factor_codes,
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

    # 创建输出目录
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    # 保存汇总表
    summary_path = os.path.join(output_dir, 'etf_factor_test_summary.csv')
    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    print(f"\n汇总表已保存: {summary_path}")

    # 绘图
    if HAS_PLOT:
        print("\n生成可视化图表...")

        # IC 热力图
        for fwd in [5, 10, 20]:
            heatmap_path = os.path.join(output_dir, f'ic_heatmap_t{fwd}.png')
            try:
                plot_ic_heatmap(all_results, forward_window=fwd, save_path=heatmap_path)
            except Exception as e:
                print(f"  热力图 (T+{fwd}) 生成失败: {e}")

        # 滚动 IC 图 (选择 IC 最高的组合)
        best_result = max(all_results.values(), key=lambda x: abs(x.get('ic', 0)))
        if best_result:
            rolling_ic_path = os.path.join(output_dir, f"rolling_ic_{best_result['etf_code']}_{best_result['factor_code']}.png")
            try:
                plot_rolling_ic(all_results, best_result['etf_code'], best_result['factor_code'],
                              save_path=rolling_ic_path)
            except Exception as e:
                print(f"  滚动 IC 图生成失败: {e}")

    print("\n" + "=" * 70)
    print("✅ 测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
