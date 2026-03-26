# -*- coding: utf-8 -*-
"""
估值因子回测模块 (Valuation Factor Backtest)

计算并回测估值相关因子:
- pe_ttm: 市盈率TTM
- pb: 市净率
- ps_ttm: 市销率TTM
- market_cap: 总市值
- circ_market_cap: 流通市值

回测方法:
- IC分析: 因子与未来收益的Spearman相关系数
- 分组回测: 按因子分位数分组，检验各组收益差异
- 多空组合: 最高组vs最低组的收益差

运行:
    python research/valuation_factor_backtest.py
    python research/valuation_factor_backtest.py --start 2024-01-01 --end 2025-12-31
"""
import sys
import os
import argparse
from datetime import date, timedelta
from typing import List, Optional, Dict, Tuple
import warnings

import pandas as pd
import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query, get_connection

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import seaborn as sns
    # 设置中文字体 - 使用系统可用字体
    import platform
    if platform.system() == "Darwin":
        # macOS 尝试多种字体
        matplotlib.rcParams["font.family"] = ["Arial Unicode MS", "Heiti TC", "STHeiti", "sans-serif"]
    elif platform.system() == "Windows":
        matplotlib.rcParams["font.family"] = ["SimHei", "Microsoft YaHei", "sans-serif"]
    else:
        matplotlib.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False
    print("警告: matplotlib 或 seaborn 未安装，将跳过可视化")


# ============================================================
# 配置
# ============================================================

# 估值因子列表 (ps_ttm数据缺失，暂时排除)
VALUATION_FACTORS = {
    'pe_ttm': 'PE_TTM',
    'pb': 'PB',
    'market_cap': 'Market_Cap',
    'circ_market_cap': 'Circ_Market_Cap',
}

# 回测参数
FORWARD_WINDOWS = [5, 10, 20]  # 预测窗口
QUANTILE_GROUPS = 5  # 分组数
MIN_STOCKS_PER_GROUP = 30  # 每组最少股票数

# IC 阈值
IC_SIGNIFICANT_THRESHOLD = 0.03  # IC显著阈值
ICIR_THRESHOLD = 0.4  # ICIR阈值


# ============================================================
# 数据加载
# ============================================================

def load_valuation_factors(start_date: str, end_date: str) -> pd.DataFrame:
    """
    从数据库加载估值因子数据
    """
    sql = f"""
        SELECT stock_code, calc_date as trade_date,
               pe_ttm, pb, ps_ttm, market_cap, circ_market_cap
        FROM trade_stock_valuation_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        ORDER BY calc_date, stock_code
    """
    rows = execute_query(sql)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])

    # 转换数值
    for col in ['pe_ttm', 'pb', 'ps_ttm', 'market_cap', 'circ_market_cap']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.set_index(['trade_date', 'stock_code'])
    return df


def load_price_data(start_date: str, end_date: str) -> pd.DataFrame:
    """
    从数据库加载价格数据
    """
    sql = f"""
        SELECT stock_code, trade_date, close_price
        FROM trade_stock_daily
        WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
        ORDER BY stock_code, trade_date
    """
    rows = execute_query(sql)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')

    df = df.set_index(['trade_date', 'stock_code'])
    return df


def calculate_forward_returns(price_df: pd.DataFrame, windows: List[int]) -> pd.DataFrame:
    """
    计算未来收益率
    """
    result_list = []

    for code, group in price_df.groupby(level='stock_code'):
        group = group.reset_index(level='stock_code', drop=True).sort_index()

        for window in windows:
            group[f'forward_{window}d'] = group['close_price'].shift(-window) / group['close_price'] - 1

        group['stock_code'] = code
        result_list.append(group)

    result_df = pd.concat(result_list)
    result_df = result_df.reset_index().set_index(['trade_date', 'stock_code'])

    return result_df[[f'forward_{w}d' for w in windows]]


# ============================================================
# IC 分析
# ============================================================

def calculate_ic(factor_series: pd.Series, return_series: pd.Series) -> Tuple[float, int]:
    """
    计算单个截面的IC (Spearman相关系数)
    """
    valid_mask = ~(factor_series.isna() | return_series.isna())
    factor_valid = factor_series[valid_mask]
    return_valid = return_series[valid_mask]

    if len(factor_valid) < MIN_STOCKS_PER_GROUP:
        return np.nan, 0

    ic, _ = stats.spearmanr(factor_valid, return_valid)
    return ic, len(factor_valid)


def calculate_ic_series(
    factor_df: pd.DataFrame,
    return_df: pd.DataFrame,
    factor_name: str,
    window: int
) -> pd.DataFrame:
    """
    计算IC时间序列
    """
    return_col = f'forward_{window}d'

    if return_col not in return_df.columns:
        return pd.DataFrame()

    ic_list = []
    dates = factor_df.index.get_level_values(0).unique().sort_values()

    for trade_date in dates:
        try:
            if trade_date not in factor_df.index.get_level_values(0):
                continue
            if trade_date not in return_df.index.get_level_values(0):
                continue

            factor_values = factor_df.loc[trade_date, factor_name]
            return_values = return_df.loc[trade_date, return_col]

            ic, sample_cnt = calculate_ic(factor_values, return_values)

            ic_list.append({
                'date': trade_date,
                'ic': ic,
                'sample_count': sample_cnt
            })
        except Exception:
            continue

    if not ic_list:
        return pd.DataFrame()

    return pd.DataFrame(ic_list).set_index('date')


def calculate_ic_stats(ic_df: pd.DataFrame) -> Dict:
    """
    计算IC统计指标
    """
    if ic_df.empty:
        return {}

    ic_series = ic_df['ic'].dropna()

    if len(ic_series) < 20:
        return {}

    ic_mean = ic_series.mean()
    ic_std = ic_series.std()
    icir = ic_mean / ic_std if ic_std > 0 else 0

    return {
        'ic_mean': ic_mean,
        'ic_std': ic_std,
        'icir': icir,
        'ic_positive_ratio': (ic_series > 0).mean(),
        'ic_count': len(ic_series),
        't_stat': ic_mean / (ic_std / np.sqrt(len(ic_series))) if ic_std > 0 else 0
    }


# ============================================================
# 分组回测
# ============================================================

def calculate_quantile_returns(
    factor_series: pd.Series,
    return_series: pd.Series,
    n_groups: int = 5
) -> Tuple[pd.Series, Dict]:
    """
    按因子分位数分组，计算各组收益
    """
    valid_mask = ~(factor_series.isna() | return_series.isna())
    factor_valid = factor_series[valid_mask]
    return_valid = return_series[valid_mask]

    if len(factor_valid) < MIN_STOCKS_PER_GROUP * n_groups:
        return pd.Series(), {}

    # 分组
    try:
        labels = [f'Q{i+1}' for i in range(n_groups)]
        quantiles = pd.qcut(factor_valid, n_groups, labels=labels, duplicates='drop')
    except Exception:
        return pd.Series(), {}

    # 计算各组收益
    group_returns = return_valid.groupby(quantiles).mean()

    stats_dict = {
        'spread': group_returns.get('Q5', 0) - group_returns.get('Q1', 0) if len(group_returns) >= 2 else 0,
        'monotonic': all(group_returns.diff().dropna() > 0) or all(group_returns.diff().dropna() < 0),
        'max_ret': group_returns.max(),
        'min_ret': group_returns.min()
    }

    return group_returns, stats_dict


def backtest_quantile_strategy(
    factor_df: pd.DataFrame,
    return_df: pd.DataFrame,
    factor_name: str,
    window: int,
    n_groups: int = 5
) -> pd.DataFrame:
    """
    分组回测
    """
    return_col = f'forward_{window}d'

    if return_col not in return_df.columns:
        return pd.DataFrame()

    results = []
    dates = factor_df.index.get_level_values(0).unique().sort_values()

    for trade_date in dates:
        try:
            if trade_date not in factor_df.index.get_level_values(0):
                continue
            if trade_date not in return_df.index.get_level_values(0):
                continue

            factor_values = factor_df.loc[trade_date, factor_name]
            return_values = return_df.loc[trade_date, return_col]

            group_returns, _ = calculate_quantile_returns(factor_values, return_values, n_groups)

            if len(group_returns) > 0:
                row = {'date': trade_date}
                for q, ret in group_returns.items():
                    row[str(q)] = ret
                results.append(row)
        except Exception:
            continue

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results).set_index('date')


# ============================================================
# 可视化
# ============================================================

def plot_ic_series(ic_df: pd.DataFrame, factor_name: str, save_path: str = None):
    """绘制IC时间序列"""
    if not HAS_PLOT or ic_df.empty:
        return

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    # IC时间序列
    ax1 = axes[0]
    colors = ['green' if x > 0 else 'red' for x in ic_df['ic']]
    ax1.bar(ic_df.index, ic_df['ic'], color=colors, alpha=0.7)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax1.axhline(y=0.03, color='blue', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.axhline(y=-0.03, color='blue', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.set_title(f'{factor_name} IC Time Series')
    ax1.set_ylabel('IC')

    # IC累积
    ax2 = axes[1]
    ic_cumsum = ic_df['ic'].cumsum()
    ax2.plot(ic_df.index, ic_cumsum, color='blue', linewidth=1.5)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_title(f'{factor_name} Cumulative IC')
    ax2.set_ylabel('Cumulative IC')
    ax2.set_xlabel('Date')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  图表已保存: {save_path}")

    plt.close()


def plot_quantile_returns(group_returns_df: pd.DataFrame, factor_name: str, save_path: str = None):
    """绘制分组收益"""
    if not HAS_PLOT or group_returns_df.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # 各组累积收益
    ax1 = axes[0]
    cum_returns = (1 + group_returns_df).cumprod()
    for col in cum_returns.columns:
        ax1.plot(cum_returns.index, cum_returns[col], label=col, linewidth=1.5)
    ax1.set_title(f'{factor_name} Cumulative Returns by Quantile')
    ax1.set_ylabel('Cumulative Return')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 平均收益柱状图
    ax2 = axes[1]
    mean_returns = group_returns_df.mean() * 100  # 转为百分比
    colors = ['red' if x < 0 else 'green' for x in mean_returns]
    bars = ax2.bar(mean_returns.index, mean_returns, color=colors, alpha=0.7)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_title(f'{factor_name} Average Returns by Quantile')
    ax2.set_ylabel('Average Return (%)')

    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}%', ha='center', va='bottom' if height > 0 else 'top', fontsize=9)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  图表已保存: {save_path}")

    plt.close()


def plot_factor_comparison(results: List[Dict], save_path: str = None):
    """绘制因子对比图"""
    if not HAS_PLOT or not results:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # IC均值对比
    ax1 = axes[0]
    factors = [r['factor_name'] for r in results]
    ic_means = [r.get('ic_mean_20d', 0) or 0 for r in results]
    colors = ['green' if x > 0 else 'red' for x in ic_means]
    bars = ax1.barh(factors, ic_means, color=colors, alpha=0.7)
    ax1.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    ax1.axvline(x=0.03, color='blue', linestyle='--', linewidth=0.5, alpha=0.5)
    ax1.set_xlabel('IC Mean (20d)')
    ax1.set_title('Valuation Factors IC Comparison')

    for bar, ic in zip(bars, ic_means):
        ax1.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f'{ic:.4f}', ha='left' if ic > 0 else 'right', va='center', fontsize=9)

    # ICIR对比
    ax2 = axes[1]
    icirs = [r.get('icir_20d', 0) or 0 for r in results]
    colors = ['green' if x > 0.4 else 'orange' if x > 0 else 'red' for x in icirs]
    bars = ax2.barh(factors, icirs, color=colors, alpha=0.7)
    ax2.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    ax2.axvline(x=0.4, color='blue', linestyle='--', linewidth=0.5, alpha=0.5)
    ax2.set_xlabel('ICIR (20d)')
    ax2.set_title('Valuation Factors ICIR Comparison')

    for bar, icir in zip(bars, icirs):
        ax2.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                f'{icir:.4f}', ha='left' if icir > 0 else 'right', va='center', fontsize=9)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  图表已保存: {save_path}")

    plt.close()


# ============================================================
# 单因子回测
# ============================================================

def backtest_single_factor(
    factor_df: pd.DataFrame,
    return_df: pd.DataFrame,
    factor_name: str,
    output_dir: str
) -> Dict:
    """
    回测单个因子
    """
    factor_desc = VALUATION_FACTORS.get(factor_name, factor_name)
    print(f"\n--- 回测因子: {factor_desc} ({factor_name}) ---")

    results = {
        'factor_name': factor_name,
        'factor_desc': factor_desc
    }

    # 对每个预测窗口计算IC
    for window in FORWARD_WINDOWS:
        print(f"  计算T+{window} IC...")
        ic_df = calculate_ic_series(factor_df, return_df, factor_name, window)

        if ic_df.empty:
            print(f"    [警告] IC计算失败")
            continue

        ic_stats = calculate_ic_stats(ic_df)

        if ic_stats:
            results[f'ic_mean_{window}d'] = ic_stats['ic_mean']
            results[f'ic_std_{window}d'] = ic_stats['ic_std']
            results[f'icir_{window}d'] = ic_stats['icir']
            results[f'ic_positive_ratio_{window}d'] = ic_stats['ic_positive_ratio']
            results[f'ic_count_{window}d'] = ic_stats['ic_count']
            results[f'valid_{window}d'] = abs(ic_stats['ic_mean']) >= IC_SIGNIFICANT_THRESHOLD and abs(ic_stats['icir']) >= ICIR_THRESHOLD

            print(f"    IC均值: {ic_stats['ic_mean']:.4f}")
            print(f"    ICIR: {ic_stats['icir']:.4f}")
            print(f"    正向IC占比: {ic_stats['ic_positive_ratio']:.2%}")
            print(f"    有效: {'是' if results[f'valid_{window}d'] else '否'}")

        # 绘制IC图 (只对20日窗口)
        if window == 20 and HAS_PLOT:
            plot_path = os.path.join(output_dir, f'{factor_name}_ic_series.png')
            plot_ic_series(ic_df, factor_desc, plot_path)

    # 分组回测 (只对20日窗口)
    window = 20
    print(f"  分组回测 (T+{window})...")
    group_returns_df = backtest_quantile_strategy(factor_df, return_df, factor_name, window)

    if not group_returns_df.empty:
        # 计算多空收益
        if 'Q5' in group_returns_df.columns and 'Q1' in group_returns_df.columns:
            long_short = group_returns_df['Q5'] - group_returns_df['Q1']
            results['long_short_mean'] = long_short.mean()
            results['long_short_std'] = long_short.std()
            results['long_short_sharpe'] = long_short.mean() / (long_short.std() + 1e-10) * np.sqrt(252)
            print(f"    多空年化收益: {long_short.mean() * 252 * 100:.2f}%")
            print(f"    多空Sharpe: {results['long_short_sharpe']:.2f}")

        # 绘制分组收益图
        if HAS_PLOT:
            plot_path = os.path.join(output_dir, f'{factor_name}_quantile_returns.png')
            plot_quantile_returns(group_returns_df, factor_desc, plot_path)

    return results


# ============================================================
# 保存结果到数据库
# ============================================================

def save_backtest_results_to_db(results: List[Dict]) -> bool:
    """
    将回测结果保存到数据库

    保存到 trade_factor_validation 表
    """
    if not results:
        return False

    print("\n[3] 保存回测结果到数据库...")

    # 先添加缺失的列
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE trade_factor_validation ADD COLUMN long_short_return DOUBLE")
    except:
        pass  # 列已存在

    try:
        cursor.execute("ALTER TABLE trade_factor_validation ADD COLUMN long_short_sharpe DOUBLE")
    except:
        pass  # 列已存在

    cursor.close()
    conn.close()

    today = date.today().strftime('%Y-%m-%d')
    saved_count = 0

    for r in results:
        factor_name = r.get('factor_name', '')
        ic_mean = r.get('ic_mean_20d')
        ic_std = r.get('ic_std_20d')
        icir = r.get('icir_20d')
        ic_count = r.get('ic_count_20d', 0)
        positive_ratio = r.get('ic_positive_ratio_20d')
        is_valid = r.get('valid_20d', False)
        ls_return = r.get('long_short_mean')
        ls_sharpe = r.get('long_short_sharpe')

        # 构建原因说明
        if is_valid:
            reason = 'Factor Valid'
        elif ic_mean is not None and abs(ic_mean) < IC_SIGNIFICANT_THRESHOLD:
            reason = f'IC Mean ({ic_mean:.4f}) < Threshold ({IC_SIGNIFICANT_THRESHOLD})'
        elif icir is not None and abs(icir) < ICIR_THRESHOLD:
            reason = f'ICIR ({icir:.4f}) < Threshold ({ICIR_THRESHOLD})'
        else:
            reason = 'Insufficient Data'

        sql = """
            REPLACE INTO trade_factor_validation
            (factor_name, validate_date, is_valid, ic_mean, ic_std, icir, ic_count, positive_ratio, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (
                factor_name,
                today,
                1 if is_valid else 0,
                ic_mean,
                ic_std,
                icir,
                ic_count,
                positive_ratio,
                reason
            ))
            conn.commit()
            cursor.close()
            conn.close()
            saved_count += 1
        except Exception as e:
            print(f"  Save {factor_name} failed: {e}")

    print(f"  Saved {saved_count} factors validation results")
    return True


# ============================================================
# 主流程
# ============================================================

def run_backtest(start_date: str, end_date: str, output_dir: str) -> List[Dict]:
    """
    运行所有估值因子的回测
    """
    print("=" * 70)
    print("估值因子回测")
    print("=" * 70)
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"预测窗口: {FORWARD_WINDOWS}")
    print(f"分组数: {QUANTILE_GROUPS}")

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 加载数据
    print("\n[1] 加载数据...")
    print("  加载估值因子...")
    factor_df = load_valuation_factors(start_date, end_date)
    if factor_df.empty:
        print("  [错误] 无法加载估值因子数据")
        return []
    print(f"    加载完成: {len(factor_df):,} 条记录")

    print("  加载价格数据...")
    price_df = load_price_data(start_date, end_date)
    if price_df.empty:
        print("  [错误] 无法加载价格数据")
        return []
    print(f"    加载完成: {len(price_df):,} 条记录")

    print("  计算未来收益...")
    return_df = calculate_forward_returns(price_df, FORWARD_WINDOWS)
    print(f"    计算完成: {len(return_df):,} 条记录")

    # 回测每个因子
    print("\n[2] 回测因子...")
    all_results = []

    for factor_name in VALUATION_FACTORS.keys():
        result = backtest_single_factor(factor_df, return_df, factor_name, output_dir)
        all_results.append(result)

    # 汇总结果
    print("\n" + "=" * 70)
    print("回测结果汇总")
    print("=" * 70)

    # 打印汇总表
    print(f"\n{'因子':<20} {'IC均值(20d)':>12} {'ICIR(20d)':>10} {'正向IC占比':>10} {'有效':>6}")
    print("-" * 70)

    for r in all_results:
        ic_mean = r.get('ic_mean_20d', np.nan)
        icir = r.get('icir_20d', np.nan)
        pos_ratio = r.get('ic_positive_ratio_20d', np.nan)
        valid = r.get('valid_20d', False)

        ic_mean_str = f"{ic_mean:.4f}" if not np.isnan(ic_mean) else "N/A"
        icir_str = f"{icir:.4f}" if not np.isnan(icir) else "N/A"
        pos_str = f"{pos_ratio:.2%}" if not np.isnan(pos_ratio) else "N/A"

        print(f"{r['factor_desc']:<20} {ic_mean_str:>12} {icir_str:>10} {pos_str:>10} {'是' if valid else '否':>6}")

    # 绘制因子对比图
    if HAS_PLOT:
        plot_path = os.path.join(output_dir, 'valuation_factors_comparison.png')
        plot_factor_comparison(all_results, plot_path)

    # 保存结果到CSV
    summary_df = pd.DataFrame(all_results)
    summary_path = os.path.join(output_dir, 'valuation_factors_backtest_summary.csv')
    summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    print(f"\n汇总结果已保存: {summary_path}")

    # 保存回测结果到数据库
    save_backtest_results_to_db(all_results)

    # 分析结论
    print("\n" + "=" * 70)
    print("分析结论")
    print("=" * 70)

    valid_factors = [r for r in all_results if r.get('valid_20d', False)]

    if valid_factors:
        print(f"\n有效因子 (|IC均值| >= {IC_SIGNIFICANT_THRESHOLD} 且 |ICIR| >= {ICIR_THRESHOLD}):")
        for r in sorted(valid_factors, key=lambda x: abs(x.get('icir_20d', 0)), reverse=True):
            print(f"  - {r['factor_desc']}: IC={r.get('ic_mean_20d', 0):.4f}, ICIR={r.get('icir_20d', 0):.4f}")
    else:
        print(f"\n无有效因子")

    # 多空组合分析
    print("\n多空组合表现 (Q5 - Q1):")
    for r in all_results:
        ls_mean = r.get('long_short_mean', np.nan)
        ls_sharpe = r.get('long_short_sharpe', np.nan)
        if not np.isnan(ls_mean):
            print(f"  - {r['factor_desc']}: 年化收益={ls_mean*252*100:.2f}%, Sharpe={ls_sharpe:.2f}")

    print("\n" + "=" * 70)
    print("回测完成!")
    print("=" * 70)

    return all_results


def main():
    parser = argparse.ArgumentParser(description='估值因子回测')
    parser.add_argument('--start', type=str, default='2024-01-01', help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2026-03-23', help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    args = parser.parse_args()

    run_backtest(args.start, args.end, args.output)


if __name__ == "__main__":
    main()
