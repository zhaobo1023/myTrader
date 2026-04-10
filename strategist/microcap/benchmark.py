# -*- coding: utf-8 -*-
"""
基准指数数据加载器

支持的基准：
  399303 - 国证2000（微盘股代表性指数，等权，日频再平衡）
  000852 - 中证1000
  000905 - 中证500
  000300 - 沪深300

数据来源：AKShare index_zh_a_hist
缓存策略：按日期范围缓存到 output/microcap/benchmark_{code}_{start}_{end}.csv，
          避免重复调用 API（同一日期范围直接读本地）。
"""
import os
import logging
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 常用基准代码
BENCHMARK_399303 = '399303'  # 国证2000（推荐：与微盘策略最接近）
BENCHMARK_000852 = '000852'  # 中证1000
BENCHMARK_000905 = '000905'  # 中证500
BENCHMARK_000300 = '000300'  # 沪深300

DEFAULT_BENCHMARK = BENCHMARK_399303


def load_benchmark(benchmark_code: str, start_date: str, end_date: str,
                   cache_dir: Optional[str] = None) -> pd.DataFrame:
    """
    加载基准指数日线数据，优先读取本地缓存，否则从 AKShare 拉取。

    Args:
        benchmark_code: 指数代码，如 '399303'
        start_date: 开始日期 'YYYY-MM-DD'
        end_date:   结束日期 'YYYY-MM-DD'
        cache_dir:  缓存目录，None 则使用 output/microcap/

    Returns:
        DataFrame，列：trade_date(str), close, daily_return
        trade_date 格式 'YYYY-MM-DD'，按日期升序排列
    """
    if cache_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cache_dir = os.path.join(root, 'output', 'microcap')
    os.makedirs(cache_dir, exist_ok=True)

    start_compact = start_date.replace('-', '')
    end_compact   = end_date.replace('-', '')
    cache_file = os.path.join(cache_dir, f'benchmark_{benchmark_code}_{start_compact}_{end_compact}.csv')

    if os.path.exists(cache_file):
        logger.info(f"[CACHE] 读取基准缓存: {cache_file}")
        df = pd.read_csv(cache_file)
        df['trade_date'] = df['trade_date'].astype(str)
        return df

    logger.info(f"[FETCH] 从 AKShare 拉取基准 {benchmark_code}: {start_date} ~ {end_date}")
    try:
        import akshare as ak
        raw = ak.index_zh_a_hist(
            symbol=benchmark_code,
            period='daily',
            start_date=start_compact,
            end_date=end_compact,
        )
    except Exception as e:
        logger.error(f"[ERROR] AKShare 拉取基准失败: {e}")
        return pd.DataFrame(columns=['trade_date', 'close', 'daily_return'])

    if raw is None or raw.empty:
        logger.warning(f"[WARN] 基准 {benchmark_code} 返回空数据")
        return pd.DataFrame(columns=['trade_date', 'close', 'daily_return'])

    df = raw[['日期', '收盘']].copy()
    df.columns = ['trade_date', 'close']
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
    df = df.sort_values('trade_date').reset_index(drop=True)
    df['close'] = df['close'].astype(float)
    df['daily_return'] = df['close'].pct_change().fillna(0.0)

    df.to_csv(cache_file, index=False)
    logger.info(f"[OK] 基准数据已缓存: {cache_file}，共 {len(df)} 条")
    return df


def calc_benchmark_metrics(strategy_daily_returns: pd.Series,
                            benchmark_daily_returns: pd.Series) -> Dict:
    """
    计算策略相对基准的超额收益指标。

    Args:
        strategy_daily_returns:  策略日收益率 Series（索引为日期字符串）
        benchmark_daily_returns: 基准日收益率 Series（索引为日期字符串）

    Returns:
        dict，含以下字段：
          benchmark_annual_return  基准年化收益
          excess_annual_return     超额年化收益（策略 - 基准）
          information_ratio        信息比率 = mean(excess) / std(excess) * sqrt(250)
          beta                     策略相对基准的 beta
          alpha                    Jensen alpha（年化）
    """
    import numpy as np

    # 对齐日期
    common_dates = strategy_daily_returns.index.intersection(benchmark_daily_returns.index)
    if len(common_dates) < 10:
        logger.warning(f"[WARN] 策略与基准对齐后仅 {len(common_dates)} 个交易日，指标可能不可靠")

    strat_r  = strategy_daily_returns.loc[common_dates].values
    bench_r  = benchmark_daily_returns.loc[common_dates].values
    n = len(strat_r)

    if n == 0:
        return {
            'benchmark_annual_return': 0.0,
            'excess_annual_return': 0.0,
            'information_ratio': 0.0,
            'beta': 0.0,
            'alpha': 0.0,
            'benchmark_coverage_days': 0,
        }

    # 基准年化收益
    bench_nav_final = float((1 + pd.Series(bench_r)).cumprod().iloc[-1])
    years = n / 250.0
    bench_annual = float(bench_nav_final ** (1.0 / years) - 1) if years > 0 else 0.0

    # 策略年化收益
    strat_nav_final = float((1 + pd.Series(strat_r)).cumprod().iloc[-1])
    strat_annual = float(strat_nav_final ** (1.0 / years) - 1) if years > 0 else 0.0

    # 超额日收益
    excess_r = strat_r - bench_r
    excess_mean = float(np.mean(excess_r))
    excess_std  = float(np.std(excess_r, ddof=1)) if n > 1 else 0.0

    # 信息比率
    ir = float(excess_mean / excess_std * (250 ** 0.5)) if excess_std > 0 else 0.0

    # Beta（OLS: cov(strat, bench) / var(bench)）
    bench_var = float(np.var(bench_r, ddof=1)) if n > 1 else 0.0
    beta = float(np.cov(strat_r, bench_r)[0, 1] / bench_var) if bench_var > 0 else 0.0

    # Jensen Alpha（年化）
    alpha = strat_annual - beta * bench_annual

    return {
        'benchmark_annual_return': round(bench_annual, 6),
        'excess_annual_return':    round(strat_annual - bench_annual, 6),
        'information_ratio':       round(ir, 4),
        'beta':                    round(beta, 4),
        'alpha':                   round(alpha, 6),
        'benchmark_coverage_days': n,
    }
