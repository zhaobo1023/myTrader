# -*- coding: utf-8 -*-
"""
因子有效性验证模块

使用 IC 分析验证因子有效性:
- IC 均值 > 0.03
- ICIR > 0.4

运行: python data_analyst/factors/factor_validator.py
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import date, timedelta
from time import time
import logging
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 因子验证阈值
IC_MEAN_THRESHOLD = 0.03  # IC均值阈值
ICIR_THRESHOLD = 0.4       # ICIR阈值

# 因子列表
FACTORS = [
    'mom_20',
    'mom_60',
    'reversal_5',
    'turnover',
    'vol_ratio',
    'price_vol_diverge',
    'volatility_20'
]


def load_factor_data(start_date='2024-01-01', end_date='2026-03-20'):
    """
    从数据库加载因子数据

    Returns:
        DataFrame: 多级索引 (trade_date, stock_code), 列为因子
    """
    logger.info(f"加载因子数据 ({start_date} ~ {end_date})...")

    sql = f"""
        SELECT stock_code, calc_date as trade_date,
               mom_20, mom_60, reversal_5,
               turnover, vol_ratio, price_vol_diverge, volatility_20, close
        FROM trade_stock_basic_factor
        WHERE calc_date >= '{start_date}' AND calc_date <= '{end_date}'
        ORDER BY calc_date, stock_code
    """

    rows = execute_query(sql)
    if not rows:
        logger.error("未加载到因子数据")
        return None

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])

    # 设置多级索引
    df = df.set_index(['trade_date', 'stock_code'])

    logger.info(f"  加载完成: {len(df):,} 条记录")
    return df


def load_forward_returns(start_date='2024-01-01', end_date='2026-03-20', periods=[1, 5, 10, 20]):
    """
    计算未来收益率

    Args:
        start_date: 开始日期
        end_date: 结束日期
        periods: 收益率周期列表

    Returns:
        DataFrame: 多级索引 (trade_date, stock_code), 列为各周期收益率
    """
    logger.info(f"计算未来收益率 (周期: {periods})...")

    # 加载收盘价数据
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

    # 按股票分组计算未来收益率
    result_list = []

    for code, group in df.groupby('stock_code'):
        group = group.sort_values('trade_date')
        group = group.set_index('trade_date')

        for period in periods:
            # 计算未来收益率
            group[f'forward_{period}d'] = group['close_price'].shift(-period) / group['close_price'] - 1

        group['stock_code'] = code
        result_list.append(group)

    result_df = pd.concat(result_list)
    result_df = result_df.reset_index().set_index(['trade_date', 'stock_code'])

    # 删除 NaN
    result_df = result_df.dropna()

    logger.info(f"  计算完成: {len(result_df):,} 条有效记录")
    return result_df


def calculate_ic(factor_series, forward_return_series):
    """
    计算单个因子的 IC 值

    Args:
        factor_series: 因子值序列
        forward_return_series: 未来收益率序列

    Returns:
        float: IC 值 (Spearman 相关系数)
    """
    # 去除 NaN
    valid_mask = ~(factor_series.isna() | forward_return_series.isna())
    factor_valid = factor_series[valid_mask]
    return_valid = forward_return_series[valid_mask]

    if len(factor_valid) < 30:  # 样本太少
        return np.nan

    # 计算 Spearman 相关系数
    from scipy.stats import spearmanr
    ic, _ = spearmanr(factor_valid, return_valid)

    return ic


def calculate_ic_series(factor_data, forward_returns, factor_name, period=20):
    """
    计算因子 IC 时间序列

    Args:
        factor_data: 因子数据 (trade_date, stock_code 索引)
        forward_returns: 未来收益率数据
        factor_name: 因子名称
        period: 收益率周期

    Returns:
        Series: IC 时间序列
    """
    ic_series = []
    dates = factor_data.index.get_level_values(0).unique().sort_values()

    for date in dates:
        try:
            # 获取当日因子值
            if date not in factor_data.index.get_level_values(0):
                continue

            factor_values = factor_data.loc[date, factor_name]

            # 获取对应的未来收益率
            return_col = f'forward_{period}d'
            if return_col not in forward_returns.columns:
                continue

            if date not in forward_returns.index.get_level_values(0):
                continue

            return_values = forward_returns.loc[date, return_col]

            # 对齐股票代码
            common_stocks = factor_values.index.intersection(return_values.index)
            if len(common_stocks) < 30:
                continue

            factor_aligned = factor_values[common_stocks]
            return_aligned = return_values[common_stocks]

            # 计算 IC
            ic = calculate_ic(factor_aligned, return_aligned)
            ic_series.append({'date': date, 'ic': ic})

        except Exception as e:
            continue

    if not ic_series:
        return None

    ic_df = pd.DataFrame(ic_series)
    ic_df = ic_df.set_index('date')['ic']

    return ic_df


def validate_factor(factor_name, ic_series):
    """
    验证单个因子的有效性

    Args:
        factor_name: 因子名称
        ic_series: IC 时间序列

    Returns:
        dict: 验证结果
    """
    if ic_series is None or len(ic_series) < 20:
        return {
            'factor': factor_name,
            'valid': False,
            'reason': '数据不足',
            'ic_mean': None,
            'icir': None
        }

    # 去除 NaN
    ic_clean = ic_series.dropna()

    if len(ic_clean) < 20:
        return {
            'factor': factor_name,
            'valid': False,
            'reason': '有效IC数据不足',
            'ic_mean': None,
            'icir': None
        }

    # 计算 IC 均值和 ICIR
    ic_mean = ic_clean.mean()
    ic_std = ic_clean.std()
    icir = ic_mean / ic_std if ic_std > 0 else 0

    # 判断有效性
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
    """
    保存验证结果到数据库

    Args:
        results: 验证结果列表
    """
    # 创建表
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='因子有效性验证结果';
    """

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(create_sql)

    # 插入数据
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

    logger.info(f"✅ 验证结果已保存到数据库")


def main():
    """主函数 - 验证所有因子"""
    logger.info("=" * 60)
    logger.info("因子有效性验证")
    logger.info(f"验证阈值: IC均值 >= {IC_MEAN_THRESHOLD}, ICIR >= {ICIR_THRESHOLD}")
    logger.info("=" * 60)

    # 1. 加载因子数据
    logger.info("\n[1] 加载因子数据...")
    t0 = time()
    factor_data = load_factor_data()
    if factor_data is None:
        return
    logger.info(f"  耗时: {time()-t0:.1f}s")

    # 2. 计算未来收益率
    logger.info("\n[2] 计算未来收益率...")
    t0 = time()
    forward_returns = load_forward_returns(periods=[5, 10, 20])
    if forward_returns is None:
        return
    logger.info(f"  耗时: {time()-t0:.1f}s")

    # 3. 验证每个因子
    logger.info("\n[3] 验证因子有效性...")
    results = []

    for factor_name in FACTORS:
        logger.info(f"\n--- 验证因子: {factor_name} ---")
        t0 = time()

        if factor_name not in factor_data.columns:
            logger.warning(f"  因子 {factor_name} 不存在")
            continue

        # 计算 IC 时间序列
        ic_series = calculate_ic_series(factor_data, forward_returns, factor_name, period=20)

        # 验证因子
        result = validate_factor(factor_name, ic_series)
        results.append(result)

        # 打印结果
        status = "✅ 有效" if result['valid'] else "❌ 无效"
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
        logger.info(f"  ✅ {r['factor']}: IC均值={r['ic_mean']:.4f}, ICIR={r['icir']:.4f}")

    logger.info(f"\n无效因子 ({len(invalid_factors)}):")
    for r in invalid_factors:
        logger.info(f"  ❌ {r['factor']}: {r.get('reason', '')}")

    # 5. 保存到数据库
    logger.info("\n[4] 保存验证结果到数据库...")
    save_validation_results(results)

    logger.info("\n" + "=" * 60)
    logger.info("✅ 因子有效性验证完成!")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    main()
