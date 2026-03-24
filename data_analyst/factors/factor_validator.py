# -*- coding: utf-8 -*-
"""
因子有效性验证模块

验证所有因子:
- IC均值 > 0.03
- ICIR > 0.4

运行: python data_analyst/factors/factor_validator.py
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import date
from time import time
import logging
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 因子验证阈值
IC_MEAN_THRESHOLD = 0.03
ICIR_THRESHOLD = 0.4

# 因子列表
FACTORS = [
    # 基础因子 (trade_stock_basic_factor)
    'mom_20', 'mom_60', 'reversal_5', 'turnover', 'vol_ratio', 'price_vol_diverge', 'volatility_20',
    # 扩展因子 (trade_stock_extended_factor)
    'mom_5', 'mom_10', 'reversal_1', 'turnover_20_mean', 'amihud_illiquidity', 'high_low_ratio', 'volume_ratio_20',
    'roe_ttm', 'gross_margin', 'net_profit_growth', 'revenue_growth',
    # 估值因子 (trade_stock_valuation_factor)
    'pe_ttm', 'pb', 'ps_ttm',
    # 质量因子 (trade_stock_quality_factor)
    'cash_flow_ratio', 'accrual', 'current_ratio', 'roa', 'debt_ratio',
]


def load_factor_data(start_date='2024-01-01', end_date='2026-03-24'):
    """从数据库加载因子数据"""
    logger.info(f"加载因子数据 ({start_date} ~ {end_date})...")

    all_data = []

    # 基础因子
    basic_sql = f"""
        SELECT stock_code, calc_date as trade_date,
               mom_20, mom_60, reversal_5, turnover, vol_ratio, price_vol_diverge, volatility_20, close
        FROM trade_stock_basic_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        ORDER BY calc_date, stock_code
    """
    rows_basic = execute_query(basic_sql)

    # 扩展因子
    extended_sql = f"""
        SELECT stock_code, calc_date as trade_date,
               mom_5, mom_10, reversal_1, turnover_20_mean,
               amihud_illiquidity, high_low_ratio, volume_ratio_20,
               roe_ttm, gross_margin, net_profit_growth, revenue_growth
        FROM trade_stock_extended_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        ORDER BY calc_date, stock_code
    """
    rows_extended = execute_query(extended_sql)

    # 估值因子
    valuation_sql = f"""
        SELECT stock_code, calc_date as trade_date,
               pe_ttm, pb, ps_ttm
        FROM trade_stock_valuation_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        ORDER BY calc_date, stock_code
    """
    rows_valuation = execute_query(valuation_sql)

    # 质量因子
    quality_sql = f"""
        SELECT stock_code, calc_date as trade_date,
               cash_flow_ratio, accrual, current_ratio, roa, debt_ratio
        FROM trade_stock_quality_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        ORDER BY calc_date, stock_code
    """
    rows_quality = execute_query(quality_sql)

    if not rows_basic and not rows_extended and not rows_valuation and not rows_quality:
        logger.error("未加载到因子数据")
        return None

    df_basic = pd.DataFrame(rows_basic) if rows_basic else pd.DataFrame()
    df_extended = pd.DataFrame(rows_extended) if rows_extended else pd.DataFrame()
    df_valuation = pd.DataFrame(rows_valuation) if rows_valuation else pd.DataFrame()
    df_quality = pd.DataFrame(rows_quality) if rows_quality else pd.DataFrame()

    # 合并所有因子数据
    dfs_to_merge = [df for df in [df_basic, df_extended, df_valuation, df_quality] if not df.empty]
    if not dfs_to_merge:
        logger.error("未加载到因子数据")
        return None

    df = dfs_to_merge[0]
    for other_df in dfs_to_merge[1:]:
        if 'trade_date' not in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
        if 'trade_date' not in other_df.columns:
            other_df['trade_date'] = pd.to_datetime(other_df['trade_date'])
        df = pd.merge(df, other_df, on=['trade_date', 'stock_code'], how='outer')

    if 'trade_date' not in df.columns:
        df['trade_date'] = pd.to_datetime(df['trade_date'])

    df = df.set_index(['trade_date', 'stock_code'])
    logger.info(f"  加载完成: {len(df):,} 条记录")
    return df


def load_forward_returns(start_date='2024-01-01', end_date='2026-03-24', periods=[5, 10, 20]):
    """计算未来收益率"""
    logger.info(f"计算未来收益率 (周期: {periods})...")

    sql = f"""
        SELECT stock_code, trade_date, close_price
        FROM trade_stock_daily
        WHERE trade_date >= '{start_date}' AND trade_date <= '{end_date}'
        ORDER BY stock_code, trade_date
    """
    rows = execute_query(sql)
    if not rows:
        logger.error("未加载到价格数据")
        return None

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')

    result_list = []
    for code, group in df.groupby('stock_code'):
        group = group.sort_values('trade_date')
        group = group.set_index('trade_date')
        for period in periods:
            group[f'forward_{period}d'] = group['close_price'].shift(-period) / group['close_price'] - 1
        group['stock_code'] = code
        result_list.append(group)

    result_df = pd.concat(result_list)
    result_df = result_df.reset_index().set_index(['trade_date', 'stock_code'])
    result_df = result_df.dropna()
    logger.info(f"  计算完成: {len(result_df):,} 条有效记录")
    return result_df


def calculate_ic(factor_series, forward_return_series):
    """计算单个因子的 IC 值 (Spearman 相关系数)"""
    valid_mask = ~(factor_series.isna() | forward_return_series.isna())
    factor_valid = factor_series[valid_mask]
    return_valid = forward_return_series[valid_mask]

    if len(factor_valid) < 30:
        return np.nan

    ic, _ = spearmanr(factor_valid, return_valid)
    return ic


def calculate_ic_series(factor_data, forward_returns, factor_name, period=20):
    """计算因子 IC 时间序列"""
    ic_series = []
    dates = factor_data.index.get_level_values(0).unique().sort_values()

    for trade_date in dates:
        try:
            if trade_date not in factor_data.index.get_level_values(0):
                continue
            factor_values = factor_data.loc[trade_date, factor_name]

            return_col = f'forward_{period}d'
            if return_col not in forward_returns.columns:
                continue
            if trade_date not in forward_returns.index.get_level_values(0):
                continue
            return_values = forward_returns.loc[trade_date, return_col]

            common_stocks = factor_values.index.intersection(return_values.index)
            if len(common_stocks) < 30:
                continue

            factor_aligned = factor_values[common_stocks]
            return_aligned = return_values[common_stocks]

            ic = calculate_ic(factor_aligned, return_aligned)
            ic_series.append({'date': trade_date, 'ic': ic})
        except Exception:
            continue

    if not ic_series:
        return None

    ic_df = pd.DataFrame(ic_series)
    ic_df = ic_df.set_index('date')['ic']
    return ic_df


def validate_factor(factor_name, ic_series):
    """验证单个因子的有效性"""
    if ic_series is None or len(ic_series) < 20:
        return {
            'factor': factor_name,
            'valid': False,
            'reason': '数据不足',
            'ic_mean': None,
            'icir': None
        }

    ic_clean = ic_series.dropna()
    if len(ic_clean) < 20:
        return {
            'factor': factor_name,
            'valid': False,
            'reason': '有效IC数据不足',
            'ic_mean': None,
            'icir': None
        }

    ic_mean = ic_clean.mean()
    ic_std = ic_clean.std()
    icir = ic_mean / ic_std if ic_std > 0 else 0

    is_valid = abs(ic_mean) >= IC_MEAN_THRESHOLD and abs(icir) >= ICIR_THRESHOLD

    result = {
        'factor': factor_name,
        'valid': is_valid,
        'ic_mean': round(ic_mean, 4),
        'ic_std': round(ic_std, 4),
        'icir': round(icir, 4),
        'ic_count': len(ic_clean),
        'positive_ratio': round((ic_clean > 0).mean(), 4) if len(ic_clean) > 0 else 0
    }

    if not is_valid:
        if abs(ic_mean) < IC_MEAN_THRESHOLD:
            result['reason'] = f'IC均值({ic_mean:.4f})低于阈值({IC_MEAN_THRESHOLD})'
        else:
            result['reason'] = f'ICIR({icir:.4f})低于阈值({ICIR_THRESHOLD})'
    else:
        result['reason'] = '因子有效'

    return result


def save_validation_results(results):
    """保存验证结果到数据库"""
    create_sql = """
    CREATE TABLE IF NOT EXISTS trade_factor_validation (
        id INT AUTO_INCREMENT PRIMARY KEY,
        factor_name VARCHAR(50) NOT NULL COMMENT '因子名称',
        validate_date DATE NOT NULL COMMENT '验证日期',
        is_valid TINYINT(1) NOT NULL COMMENT '是否有效',
        ic_mean DOUBLE COMMENT 'IC均值',
        ic_std DOUBLE COMMENT 'IC标准差',
        icir DOUBLE COMMENT '信息比率',
        ic_count INT COMMENT 'IC样本数',
        positive_ratio DOUBLE COMMENT '正向IC占比',
        reason VARCHAR(200) COMMENT '原因说明',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_factor_date (factor_name, validate_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='因子有效性验证结果'
    """

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(create_sql)

    insert_sql = """
        REPLACE INTO trade_factor_validation
        (factor_name, validate_date, is_valid, ic_mean, ic_std, icir, ic_count, positive_ratio, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    today = date.today().strftime('%Y-%m-%d')

    for r in results:
        cursor.execute(insert_sql, (
            r['factor'],
            today,
            1 if r['valid'] else 0,
            r.get('ic_mean'),
            r.get('ic_std'),
            r.get('icir'),
            r.get('ic_count'),
            r.get('positive_ratio'),
            r.get('reason', '')
        ))

    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"验证结果已保存到数据库")


def main():
    """主函数 - 验证所有因子"""
    logger.info("=" * 60)
    logger.info("因子有效性验证")
    logger.info(f"验证阈值: IC均值 >= {IC_MEAN_THRESHOLD}, ICIR >= {ICIR_THRESHOLD}")
    logger.info(f"验证因子数: {len(FACTORS)}")
    logger.info("=" * 60)

    # 1. 加载因子数据
    logger.info(f"\n[1] 加载因子数据...")
    t0 = time()
    factor_data = load_factor_data()
    if factor_data is None:
        return
    logger.info(f"  耗时: {time()-t0:.1f}s")

    # 2. 计算未来收益率
    logger.info(f"\n[2] 计算未来收益率...")
    t0 = time()
    forward_returns = load_forward_returns()
    if forward_returns is None:
        return
    logger.info(f"  耗时: {time()-t0:.1f}s")

    # 3. 验证每个因子
    logger.info(f"\n[3] 验证因子有效性...")
    results = []

    for factor_name in FACTORS:
        logger.info(f"\n--- 验证因子: {factor_name} ---")
        t0 = time()

        if factor_name not in factor_data.columns:
            logger.warning(f"  因子 {factor_name} 不存在")
            continue

        ic_series = calculate_ic_series(factor_data, forward_returns, factor_name, period=20)
        result = validate_factor(factor_name, ic_series)
        results.append(result)

        status = "有效" if result['valid'] else "无效"
        logger.info(f"  状态: {status}")
        logger.info(f"  IC均值: {result.get('ic_mean', 'N/A')}")
        logger.info(f"  ICIR: {result.get('icir', 'N/A')}")
        logger.info(f"  IC样本数: {result.get('ic_count', 'N/A')}")
        logger.info(f"  正向IC占比: {result.get('positive_ratio', 'N/A')}")
        if not result['valid']:
            logger.info(f"  原因: {result.get('reason', 'N/A')}")

    # 4. 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("验证结果汇总")
    logger.info("=" * 60)

    valid_factors = [r for r in results if r['valid']]
    invalid_factors = [r for r in results if not r['valid']]

    logger.info(f"\n有效因子 ({len(valid_factors)}):")
    for r in valid_factors:
        logger.info(f"  {r['factor']}: IC均值={r['ic_mean']:.4f}, ICIR={r['icir']:.4f}")

    logger.info(f"\n无效因子 ({len(invalid_factors)}):")
    for r in invalid_factors:
        logger.info(f"  {r['factor']}: {r.get('reason', '')}")

    # 5. 保存到数据库
    logger.info(f"\n[4] 保存验证结果到数据库...")
    save_validation_results(results)

    logger.info("\n" + "=" * 60)
    logger.info("因子有效性验证完成!")
    logger.info(f"  有效因子: {len(valid_factors)}/{len(results)}")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    main()
