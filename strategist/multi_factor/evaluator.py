# -*- coding: utf-8 -*-
"""
IC 评估模块

复用 factor_validator.py 的 Spearman IC 逻辑，支持:
- 单因子 IC 时间序列
- 合成得分 IC
- 汇总报告
"""

import logging

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .config import FACTORS, FACTOR_LABELS, FACTOR_DIRECTIONS, IC_FORWARD_PERIOD, \
    IC_MIN_SAMPLES, IC_MIN_DATES

logger = logging.getLogger(__name__)


def calculate_ic(factor_values: pd.Series, return_values: pd.Series) -> float:
    """
    计算 Spearman Rank IC。

    Returns:
        IC value or NaN if insufficient data
    """
    valid = ~(factor_values.isna() | return_values.isna())
    fv = factor_values[valid]
    rv = return_values[valid]

    if len(fv) < IC_MIN_SAMPLES:
        return np.nan

    ic, _ = spearmanr(fv, rv)
    return ic


def calculate_ic_series(factor_panel: pd.DataFrame, forward_returns: pd.DataFrame,
                        factor_name: str, period: int = IC_FORWARD_PERIOD) -> pd.Series:
    """
    计算因子 IC 时间序列。

    Args:
        factor_panel: MultiIndex (trade_date, stock_code)
        forward_returns: MultiIndex (trade_date, stock_code), has column f'forward_{period}d'
        factor_name: column name in factor_panel

    Returns:
        Series indexed by trade_date, values = daily IC
    """
    ret_col = f'forward_{period}d'
    if ret_col not in forward_returns.columns:
        logger.error(f"Forward return column '{ret_col}' not found")
        return pd.Series(dtype=float)

    if factor_name not in factor_panel.columns:
        logger.error(f"Factor column '{factor_name}' not found")
        return pd.Series(dtype=float)

    dates = sorted(set(factor_panel.index.get_level_values(0))
                   & set(forward_returns.index.get_level_values(0)))

    ic_list = []
    for dt in dates:
        try:
            fv = factor_panel.loc[dt, factor_name]
            rv = forward_returns.loc[dt, ret_col]
            # 对齐股票
            common = fv.index.intersection(rv.index)
            if len(common) < IC_MIN_SAMPLES:
                continue
            ic = calculate_ic(fv[common], rv[common])
            if not np.isnan(ic):
                ic_list.append({'date': dt, 'ic': ic})
        except Exception:
            continue

    if not ic_list:
        return pd.Series(dtype=float)

    return pd.DataFrame(ic_list).set_index('date')['ic']


def evaluate_single_factor(factor_panel: pd.DataFrame,
                           forward_returns: pd.DataFrame,
                           factor_name: str,
                           period: int = IC_FORWARD_PERIOD) -> dict:
    """
    评估单个因子的 IC 表现。

    Returns:
        dict with keys: factor, ic_mean, ic_std, icir, ic_count, positive_ratio, rank_ic_mean
    """
    ic_series = calculate_ic_series(factor_panel, forward_returns, factor_name, period)

    if ic_series is None or len(ic_series) < IC_MIN_DATES:
        return {
            'factor': factor_name,
            'label': FACTOR_LABELS.get(factor_name, factor_name),
            'ic_mean': np.nan,
            'ic_std': np.nan,
            'icir': np.nan,
            'ic_count': len(ic_series) if ic_series is not None else 0,
            'positive_ratio': np.nan,
            'rank_ic_mean': np.nan,
            'status': 'insufficient_data',
        }

    ic_clean = ic_series.dropna()
    ic_mean = ic_clean.mean()
    ic_std = ic_clean.std()
    icir = ic_mean / ic_std if ic_std > 1e-10 else 0.0
    pos_ratio = (ic_clean > 0).mean()

    # 根据 direction 判断方向是否正确
    direction = FACTOR_DIRECTIONS.get(factor_name, 1)
    expected_sign = direction  # +1 means high value -> high return, so positive IC expected
    # 但实际上 IC 是 factor 与 future_return 的相关性
    # direction=+1 (high value good) -> 期望正 IC
    # direction=-1 (low value good) -> 期望负 IC, 我们用绝对值评估

    # 用原始 IC 的方向性判断
    if direction == -1:
        # 低值更好: 期望负 IC，取反后评估
        eval_ic_mean = -ic_mean
        eval_icir = -icir
    else:
        eval_ic_mean = ic_mean
        eval_icir = icir

    status = 'valid' if (abs(eval_ic_mean) >= 0.02 and abs(eval_icir) >= 0.3) else 'weak'

    return {
        'factor': factor_name,
        'label': FACTOR_LABELS.get(factor_name, factor_name),
        'ic_mean': round(ic_mean, 4),
        'ic_std': round(ic_std, 4),
        'icir': round(icir, 4),
        'ic_count': len(ic_clean),
        'positive_ratio': round(pos_ratio, 4),
        'eval_ic_mean': round(eval_ic_mean, 4),
        'eval_icir': round(eval_icir, 4),
        'status': status,
    }


def evaluate_all_factors(factor_panel: pd.DataFrame,
                         forward_returns: pd.DataFrame,
                         period: int = IC_FORWARD_PERIOD) -> list:
    """
    评估所有因子 + 合成得分。

    Returns:
        list of dicts, one per factor
    """
    results = []

    # 评估每个单因子
    for f in FACTORS:
        if f in factor_panel.columns:
            logger.info(f"Evaluating factor: {f} ({FACTOR_LABELS.get(f, f)})")
            result = evaluate_single_factor(factor_panel, forward_returns, f, period)
            results.append(result)

    return results


def format_ic_report(results: list) -> str:
    """
    格式化 IC 评估报告为 Markdown。

    Returns:
        str, markdown report
    """
    lines = []
    lines.append("# Multi-Factor IC Evaluation Report\n")
    lines.append(f"Evaluated {len(results)} factors\n")

    # 汇总表
    lines.append("## IC Summary\n")
    lines.append("| Factor | Label | IC Mean | ICIR | IC Count | Positive % | Status |")
    lines.append("|--------|-------|---------|------|----------|------------|--------|")

    for r in results:
        status_mark = "[OK]" if r['status'] == 'valid' else "[WARN]"
        lines.append(
            f"| {r['factor']} | {r['label']} | {r['ic_mean']:.4f} | "
            f"{r['icir']:.4f} | {r['ic_count']} | {r['positive_ratio']:.2%} | {status_mark} |"
        )

    # 有效因子
    valid = [r for r in results if r['status'] == 'valid']
    weak = [r for r in results if r['status'] == 'weak']
    insufficient = [r for r in results if r['status'] == 'insufficient_data']

    lines.append(f"\n**Valid factors**: {len(valid)}")
    lines.append(f"**Weak factors**: {len(weak)}")
    lines.append(f"**Insufficient data**: {len(insufficient)}")

    if valid:
        lines.append("\n## Valid Factors\n")
        for r in valid:
            lines.append(f"- **{r['label']}** ({r['factor']}): IC={r['ic_mean']:.4f}, ICIR={r['icir']:.4f}")

    if weak:
        lines.append("\n## Weak Factors\n")
        for r in weak:
            lines.append(f"- **{r['label']}** ({r['factor']}): IC={r['ic_mean']:.4f}, ICIR={r['icir']:.4f}")

    return '\n'.join(lines)
