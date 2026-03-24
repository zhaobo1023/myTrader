# -*- coding: utf-8 -*-
"""
多因子组合研究模块 (Factor Combination Research)

功能:
    第一步：因子去冗余
        - 计算所有有效因子的相关性矩阵
        - 相关性绝对值 > 0.7 的因子对，保留ICIR更高的那个
        - 输出去冗余后的因子列表

    第二步：组合合成
        - 等权合成：所有因子标准化后等权相加
        - IC加权合成：用历史IC均值作为权重

    第三步：效果验证
        - 用 Alphalens 对合成因子跑完整验证报告
        - 和单因子对比

运行:
    python research/combination.py
    python research/combination.py --etf 159930 --window 5
"""
import sys
import os
import json
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

# 尝试导入 Alphalens
try:
    import alphalens
    from alphalens.utils import get_clean_factor_and_forward_returns
    from alphalens.tears import create_full_tear_sheet
    HAS_ALPHALENS = True
except ImportError:
    HAS_ALPHALENS = False
    print("警告: alphalens 未安装，将跳过 Alphalens 验证")


# ============================================================
# 配置
# ============================================================

# 相关性阈值 - 超过此值的因子对会被去冗余
CORRELATION_THRESHOLD = 0.7

# 默认 ETF 列表
DEFAULT_ETFS = {
    '159930': '能源化工ETF',
}

# 默认宏观因子列表
DEFAULT_FACTORS = {
    'oil_mom_20': '原油20日涨跌幅',
    'gold_mom_20': '黄金20日涨跌幅',
    'vix_ma5': 'VIX 5日均值',
}

# 预测窗口
FORWARD_WINDOW = 5


# ============================================================
# 数据加载
# ============================================================

def load_valid_factors() -> List[str]:
    """
    从 factor_status 表加载有效因子列表

    Returns:
        有效因子代码列表
    """
    sql = """
        SELECT DISTINCT factor_code
        FROM factor_status
        WHERE status = 'valid'
        ORDER BY factor_code
    """
    rows = execute_query(sql)

    if not rows:
        print("  未找到有效因子，使用默认列表")
        return list(DEFAULT_FACTORS.keys())

    return [r['factor_code'] for r in rows]


def load_factor_data(factor_codes: List[str] = None,
                     start_date: str = None,
                     end_date: str = None) -> pd.DataFrame:
    """
    从数据库加载因子数据

    Args:
        factor_codes: 因子代码列表
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        DataFrame: index=date, columns=[factor1, factor2, ...]
    """
    if factor_codes is None:
        factor_codes = list(DEFAULT_FACTORS.keys())

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


def load_etf_data(etf_code: str,
                  start_date: str = None,
                  end_date: str = None) -> pd.DataFrame:
    """
    从数据库加载 ETF 日线数据

    Args:
        etf_code: ETF 代码
        start_date: 起始日期
        end_date: 结束日期

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


def load_factor_icir(factor_codes: List[str] = None) -> Dict[str, float]:
    """
    从 factor_status 表加载各因子的最新 ICIR

    Args:
        factor_codes: 因子代码列表

    Returns:
        {factor_code: icir}
    """
    if factor_codes is None:
        factor_codes = list(DEFAULT_FACTORS.keys())

    sql = """
        SELECT factor_code, rolling_icir
        FROM factor_status
        WHERE (factor_code, calc_date) IN (
            SELECT factor_code, MAX(calc_date)
            FROM factor_status
            GROUP BY factor_code
        )
        AND factor_code IN ({})
    """.format(','.join(['%s'] * len(factor_codes)))

    rows = execute_query(sql, factor_codes)

    result = {}
    for row in rows:
        icir_val = row.get('rolling_icir')
        if icir_val is not None:
            result[row['factor_code']] = float(icir_val)

    return result


# ============================================================
# 第一步：因子去冗余
# ============================================================

def calculate_correlation_matrix(factors_df: pd.DataFrame) -> pd.DataFrame:
    """
    计算因子相关性矩阵

    Args:
        factors_df: 因子数据 DataFrame

    Returns:
        相关性矩阵
    """
    return factors_df.corr()


def identify_redundant_pairs(corr_matrix: pd.DataFrame,
                             threshold: float = 0.7) -> List[Tuple[str, str, float]]:
    """
    识别高相关的因子对

    Args:
        corr_matrix: 相关性矩阵
        threshold: 相关性阈值

    Returns:
        [(factor1, factor2, corr)] 列表
    """
    redundant_pairs = []
    factors = corr_matrix.columns.tolist()
    n = len(factors)

    for i in range(n):
        for j in range(i + 1, n):
            f1, f2 = factors[i], factors[j]
            corr = corr_matrix.loc[f1, f2]
            if abs(corr) > threshold:
                redundant_pairs.append((f1, f2, corr))

    return redundant_pairs


def remove_redundant_factors(factor_codes: List[str],
                             corr_matrix: pd.DataFrame,
                             icir_dict: Dict[str, float],
                             threshold: float = 0.7) -> List[str]:
    """
    去除冗余因子

    对于相关性 > 阈值的因子对，保留 ICIR 更高的那个

    Args:
        factor_codes: 因子代码列表
        corr_matrix: 相关性矩阵
        icir_dict: 因子 ICIR 字典
        threshold: 相关性阈值

    Returns:
        去冗余后的因子列表
    """
    # 识别高相关因子对
    redundant_pairs = identify_redundant_pairs(corr_matrix, threshold)

    if not redundant_pairs:
        print("  无高相关因子对，无需去冗余")
        return factor_codes

    print(f"  发现 {len(redundant_pairs)} 对高相关因子:")

    # 跟踪要移除的因子
    factors_to_remove = set()

    for f1, f2, corr in redundant_pairs:
        print(f"    {f1} vs {f2}: corr={corr:.3f}")

        # 获取两个因子的 ICIR
        icir1 = icir_dict.get(f1, 0)
        icir2 = icir_dict.get(f2, 0)

        # 保留 ICIR 更高的
        if abs(icir1) >= abs(icir2):
            factors_to_remove.add(f2)
            print(f"      -> 移除 {f2} (ICIR: {icir2:.3f} < {icir1:.3f})")
        else:
            factors_to_remove.add(f1)
            print(f"      -> 移除 {f1} (ICIR: {icir1:.3f} < {icir2:.3f})")

    # 返回剩余因子
    remaining = [f for f in factor_codes if f not in factors_to_remove]
    print(f"  去冗余后保留: {remaining}")

    return remaining


def step1_dereplication(factor_codes: List[str] = None,
                        start_date: str = None,
                        end_date: str = None) -> List[str]:
    """
    第一步：因子去冗余

    Args:
        factor_codes: 因子代码列表
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        去冗余后的因子列表
    """
    print("\n" + "=" * 60)
    print("第一步：因子去冗余")
    print("=" * 60)

    # 加载因子数据
    print("\n加载因子数据...")
    factors_df = load_factor_data(factor_codes, start_date, end_date)

    if factors_df.empty:
        print("  未加载到因子数据")
        return []

    print(f"  加载 {len(factors_df.columns)} 个因子, {len(factors_df)} 条记录")

    # 计算相关性矩阵
    print("\n计算因子相关性矩阵...")
    corr_matrix = calculate_correlation_matrix(factors_df)
    print(corr_matrix.round(3))

    # 加载 ICIR
    print("\n加载因子 ICIR...")
    icir_dict = load_factor_icir(list(factors_df.columns))
    for f, icir in icir_dict.items():
        print(f"  {f}: ICIR={icir:.4f}")

    # 去冗余
    print(f"\n执行去冗余 (阈值: {CORRELATION_THRESHOLD})...")
    remaining_factors = remove_redundant_factors(
        list(factors_df.columns),
        corr_matrix,
        icir_dict,
        CORRELATION_THRESHOLD
    )

    return remaining_factors


# ============================================================
# 第二步：组合合成
# ============================================================

def standardize_factors(factors_df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化因子 (Z-Score)

    Args:
        factors_df: 因子数据

    Returns:
        标准化后的因子数据
    """
    return (factors_df - factors_df.mean()) / (factors_df.std() + 1e-10)


def equal_weight_combination(factors_df: pd.DataFrame) -> pd.Series:
    """
    等权合成

    Args:
        factors_df: 因子数据 (已标准化)

    Returns:
        合成因子序列
    """
    std_factors = standardize_factors(factors_df)
    return std_factors.mean(axis=1)


def ic_weighted_combination(factors_df: pd.DataFrame,
                            icir_dict: Dict[str, float]) -> pd.Series:
    """
    IC 加权合成

    Args:
        factors_df: 因子数据
        icir_dict: 因子 ICIR 字典

    Returns:
        合成因子序列
    """
    std_factors = standardize_factors(factors_df)

    # 计算权重 (使用 ICIR 绝对值)
    weights = {}
    total_icir = sum(abs(icir_dict.get(f, 0)) for f in std_factors.columns)

    for f in std_factors.columns:
        icir = abs(icir_dict.get(f, 0))
        weights[f] = icir / total_icir if total_icir > 0 else 1 / len(std_factors.columns)

    print(f"\n  IC 加权权重:")
    for f, w in weights.items():
        print(f"    {f}: {w:.4f}")

    # 加权求和
    weighted_sum = sum(std_factors[f] * weights[f] for f in std_factors.columns)

    return weighted_sum


def step2_combination(factor_codes: List[str],
                      start_date: str = None,
                      end_date: str = None) -> Dict[str, pd.Series]:
    """
    第二步：组合合成

    Args:
        factor_codes: 因子代码列表
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        {合成方式: 合成因子序列}
    """
    print("\n" + "=" * 60)
    print("第二步：组合合成")
    print("=" * 60)

    # 加载因子数据
    print("\n加载因子数据...")
    factors_df = load_factor_data(factor_codes, start_date, end_date)

    if factors_df.empty:
        print("  未加载到因子数据")
        return {}

    print(f"  使用因子: {list(factors_df.columns)}")

    # 加载 ICIR
    icir_dict = load_factor_icir(factor_codes)

    results = {}

    # 1. 等权合成
    print("\n等权合成...")
    equal_weight_factor = equal_weight_combination(factors_df)
    results['equal_weight'] = equal_weight_factor
    print(f"  等权合成因子: {len(equal_weight_factor)} 条记录")

    # 2. IC 加权合成
    print("\nIC 加权合成...")
    ic_weighted_factor = ic_weighted_combination(factors_df, icir_dict)
    results['ic_weighted'] = ic_weighted_factor
    print(f"  IC 加权合成因子: {len(ic_weighted_factor)} 条记录")

    return results


# ============================================================
# 第三步：效果验证
# ============================================================

def calc_time_series_ic(factor: pd.Series, forward_ret: pd.Series) -> Tuple[float, float, int]:
    """
    计算时序 IC

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
    rolling_ic = aligned['factor'].rolling(60).corr(aligned['ret'])
    icir = rolling_ic.mean() / (rolling_ic.std() + 1e-10)

    return ic, icir, len(aligned)


def validate_with_alphalens(factor: pd.Series,
                            prices: pd.Series,
                            factor_name: str,
                            output_dir: str):
    """
    使用 Alphalens 验证因子

    Args:
        factor: 因子序列
        prices: 价格序列
        factor_name: 因子名称
        output_dir: 输出目录
    """
    if not HAS_ALPHALENS:
        print(f"  Alphalens 未安装，跳过 {factor_name} 验证")
        return

    print(f"\n  Alphalens 验证: {factor_name}")

    try:
        # 构造 Alphalens 需要的格式
        # factor: Series with MultiIndex (date, asset) - 需要堆叠成多资产格式
        # prices: DataFrame (index=date, columns=[asset1, asset2, ...])

        asset_id = 'ETF'

        # 因子数据: 需要是带 MultiIndex 的 Series
        factor_series = pd.Series(
            factor.values,
            index=pd.MultiIndex.from_arrays([
                factor.index,
                [asset_id] * len(factor)
            ], names=['date', 'asset'])
        )

        # 价格数据: 需要是 DataFrame，列名是资产
        prices_df = pd.DataFrame({
            asset_id: prices.values
        }, index=prices.index)

        # 清理数据
        factor_data = get_clean_factor_and_forward_returns(
            factor_series,
            prices_df,
            quantiles=5,
            periods=[1, 5, 10]
        )

        # 生成报告
        os.makedirs(output_dir, exist_ok=True)

        # 保存图表
        import matplotlib
        matplotlib.use('Agg')

        output_path = os.path.join(output_dir, f'alphalens_{factor_name}.png')

        # 创建 tear sheet
        create_full_tear_sheet(factor_data, long_short=False)

        plt.savefig(output_path)
        plt.close()

        print(f"    Alphalens 报告已保存: {output_path}")

    except Exception as e:
        import traceback
        print(f"    Alphalens 验证失败: {e}")
        traceback.print_exc()


def step3_validation(combined_factors: Dict[str, pd.Series],
                     etf_code: str = '159930',
                     forward_window: int = 5,
                     start_date: str = None,
                     end_date: str = None,
                     output_dir: str = 'output'):
    """
    第三步：效果验证

    Args:
        combined_factors: 合成因子字典
        etf_code: ETF 代码
        forward_window: 预测窗口
        start_date: 起始日期
        end_date: 结束日期
        output_dir: 输出目录
    """
    print("\n" + "=" * 60)
    print("第三步：效果验证")
    print("=" * 60)

    # 加载 ETF 数据
    print(f"\n加载 ETF 数据: {etf_code}")
    etf_df = load_etf_data(etf_code, start_date, end_date)

    if etf_df.empty:
        print("  未加载到 ETF 数据")
        return

    print(f"  ETF 数据: {len(etf_df)} 条")

    # 计算未来收益
    forward_ret = etf_df['close'].shift(-forward_window) / etf_df['close'] - 1

    results = []

    # 验证合成因子
    for method, factor in combined_factors.items():
        print(f"\n验证合成因子: {method}")

        ic, icir, sample_cnt = calc_time_series_ic(factor, forward_ret)

        print(f"  IC: {ic:.4f}, ICIR: {icir:.4f}, 样本数: {sample_cnt}")

        results.append({
            'type': 'combined',
            'method': method,
            'factor_name': f'combined_{method}',
            'ic': ic,
            'icir': icir,
            'sample_count': sample_cnt
        })

        # Alphalens 验证
        if HAS_ALPHALENS:
            try:
                validate_with_alphalens(
                    factor,
                    etf_df['close'],
                    f'combined_{method}',
                    output_dir
                )
            except Exception as e:
                print(f"  Alphalens 验证出错: {e}")

    # 验证单因子 (对比)
    print("\n对比单因子效果...")
    factor_codes = list(DEFAULT_FACTORS.keys())
    single_factors_df = load_factor_data(factor_codes, start_date, end_date)

    for factor_code in factor_codes:
        if factor_code not in single_factors_df.columns:
            continue

        factor = single_factors_df[factor_code]
        ic, icir, sample_cnt = calc_time_series_ic(factor, forward_ret)

        print(f"  {factor_code}: IC={ic:.4f}, ICIR={icir:.4f}")

        results.append({
            'type': 'single',
            'method': factor_code,
            'factor_name': factor_code,
            'ic': ic,
            'icir': icir,
            'sample_count': sample_cnt
        })

    # 生成对比报告
    print("\n" + "-" * 60)
    print("因子效果对比:")
    print("-" * 60)
    print(f"{'类型':<10} {'名称':<25} {'IC':<10} {'ICIR':<10}")
    print("-" * 60)

    for r in sorted(results, key=lambda x: abs(x.get('ic', 0)), reverse=True):
        type_str = "合成" if r['type'] == 'combined' else "单因子"
        print(f"{type_str:<10} {r['factor_name']:<25} {r['ic']:>10.4f} {r['icir']:>10.4f}")

    print("-" * 60)

    # 保存结果
    os.makedirs(output_dir, exist_ok=True)
    result_path = os.path.join(output_dir, 'combination_comparison.json')

    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n对比结果已保存: {result_path}")


# ============================================================
# 可视化
# ============================================================

def plot_correlation_heatmap(corr_matrix: pd.DataFrame, save_path: str = None):
    """绘制相关性热力图"""
    if not HAS_PLOT:
        return

    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdYlBu_r',
                center=0, vmin=-1, vmax=1)
    plt.title('因子相关性矩阵')
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
        print(f"  相关性热力图已保存: {save_path}")

    plt.close()


# ============================================================
# 主函数
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='多因子组合研究')
    parser.add_argument('--etf', type=str, default='159930', help='ETF 代码')
    parser.add_argument('--window', type=int, default=5, help='预测窗口')
    parser.add_argument('--start', type=str, help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    parser.add_argument('--factors', type=str, nargs='+', help='因子代码列表')
    args = parser.parse_args()

    print("=" * 60)
    print("多因子组合研究")
    print("=" * 60)
    print(f"ETF: {args.etf}")
    print(f"预测窗口: T+{args.window}")
    print(f"输出目录: {args.output}")

    factor_codes = args.factors if args.factors else list(DEFAULT_FACTORS.keys())

    # 第一步：因子去冗余
    remaining_factors = step1_dereplication(
        factor_codes,
        args.start,
        args.end
    )

    if not remaining_factors:
        print("去冗余后无有效因子")
        return

    # 第二步：组合合成
    combined_factors = step2_combination(
        remaining_factors,
        args.start,
        args.end
    )

    if not combined_factors:
        print("组合合成失败")
        return

    # 第三步：效果验证
    step3_validation(
        combined_factors,
        etf_code=args.etf,
        forward_window=args.window,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output
    )

    print("\n" + "=" * 60)
    print("多因子组合研究完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
