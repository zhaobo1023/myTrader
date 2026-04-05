# -*- coding: utf-8 -*-
"""
宏观数据因子计算模块 (Macro Factor Calculator)

功能:
    1. 从 macro_data 表读取原始宏观数据
    2. 计算宏观因子
    3. 存入 macro_factors 表

因子列表:
    - oil_mom_20: 原油20日涨跌幅
    - gold_mom_20: 黄金20日涨跌幅
    - dxy_mom_20: 美元指数20日变化 (暂无数据源，预留)
    - vix_ma5: VIX 5日均值 (使用QVIX替代)
    - north_flow_5d: 北向资金5日累计净流入

运行:
    python data_analyst/factors/macro_factor_calculator.py
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import get_connection, execute_query, execute_many, execute_dual_many


# ============================================================
# 数据库表结构
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS macro_factors (
    date DATE NOT NULL COMMENT '日期',
    indicator VARCHAR(50) NOT NULL COMMENT '因子代码',
    value DECIMAL(20, 6) COMMENT '因子值',
    PRIMARY KEY (date, indicator),
    INDEX idx_indicator (indicator),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观因子表';
"""


def ensure_table_exists():
    """确保 macro_factors 表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()
    conn.close()


# ============================================================
# 数据加载
# ============================================================

def load_macro_data(indicator: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """
    从数据库加载宏观数据

    Args:
        indicator: 指标代码 (wti_oil, gold, qvix, north_flow)
        start_date: 起始日期 (YYYY-MM-DD)

    Returns:
        DataFrame: index=date, columns=[value]
    """
    if start_date:
        sql = """
            SELECT date, value
            FROM macro_data
            WHERE indicator = %s AND date >= %s
            ORDER BY date ASC
        """
        rows = execute_query(sql, [indicator, start_date])
    else:
        sql = """
            SELECT date, value
            FROM macro_data
            WHERE indicator = %s
            ORDER BY date ASC
        """
        rows = execute_query(sql, [indicator])

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.set_index('date').sort_index()

    return df


def load_all_macro_data(start_date: Optional[str] = None) -> dict:
    """
    加载所有宏观数据

    Args:
        start_date: 起始日期

    Returns:
        dict: {indicator: DataFrame}
    """
    indicators = ['wti_oil', 'gold', 'qvix', 'north_flow']
    result = {}

    for indicator in indicators:
        df = load_macro_data(indicator, start_date)
        if not df.empty:
            result[indicator] = df

    return result


# ============================================================
# 因子计算
# ============================================================

def calc_momentum(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    计算动量因子 (涨跌幅)

    Args:
        df: DataFrame with 'value' column
        window: 窗口期

    Returns:
        DataFrame with 'factor' column
    """
    result = pd.DataFrame(index=df.index)
    result['factor'] = df['value'].pct_change(window)
    return result


def calc_ma(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    计算移动平均

    Args:
        df: DataFrame with 'value' column
        window: 窗口期

    Returns:
        DataFrame with 'factor' column
    """
    result = pd.DataFrame(index=df.index)
    result['factor'] = df['value'].rolling(window=window).mean()
    return result


def calc_cumsum(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    计算滚动累计和

    Args:
        df: DataFrame with 'value' column
        window: 窗口期

    Returns:
        DataFrame with 'factor' column
    """
    result = pd.DataFrame(index=df.index)
    result['factor'] = df['value'].rolling(window=window).sum()
    return result


# ============================================================
# 因子计算映射
# ============================================================
FACTOR_CONFIG = {
    'oil_mom_20': {
        'source': 'wti_oil',
        'calc_func': calc_momentum,
        'calc_params': {'window': 20},
        'name': '原油20日涨跌幅',
    },
    'gold_mom_20': {
        'source': 'gold',
        'calc_func': calc_momentum,
        'calc_params': {'window': 20},
        'name': '黄金20日涨跌幅',
    },
    'dxy_mom_20': {
        'source': None,  # 暂无数据源
        'calc_func': None,
        'calc_params': {},
        'name': '美元指数20日变化',
    },
    'vix_ma5': {
        'source': 'qvix',
        'calc_func': calc_ma,
        'calc_params': {'window': 5},
        'name': 'VIX 5日均值',
    },
    # 替换为 market_sentiment (市场情绪因子)
    'market_sentiment': {
        'source': None,  # 待实现
        'calc_func': None,
        'calc_params': {},
        'name': '市场情绪因子 (待实现)',
    },
    # 替换为 turnover_ma5 (5日成交量均值)
    'turnover_ma5': {
        'source': None,  # 待实现
        'calc_func': None,
        'calc_params': {},
        'name': '5日成交量均值 (待实现)',
    },
}


def calculate_single_factor(factor_code: str, macro_data: dict) -> pd.DataFrame:
    """
    计算单个宏观因子

    Args:
        factor_code: 因子代码
        macro_data: 原始宏观数据字典

    Returns:
        DataFrame: index=date, columns=[value]
    """
    config = FACTOR_CONFIG.get(factor_code)
    if not config:
        print(f"  未知因子: {factor_code}")
        return pd.DataFrame()

    source = config['source']
    if source is None or source not in macro_data:
        print(f"  {factor_code}: 数据源 {source} 不可用")
        return pd.DataFrame()

    calc_func = config['calc_func']
    calc_params = config['calc_params']

    source_df = macro_data[source]
    result_df = calc_func(source_df, **calc_params)

    # 重命名列
    result_df = result_df.rename(columns={'factor': 'value'})

    # 移除 NaN
    result_df = result_df.dropna()

    return result_df


def calculate_all_factors(start_date: Optional[str] = None) -> dict:
    """
    计算所有宏观因子

    Args:
        start_date: 数据起始日期

    Returns:
        dict: {factor_code: DataFrame}
    """
    print("加载宏观数据...")
    macro_data = load_all_macro_data(start_date)

    if not macro_data:
        print("  未加载到宏观数据")
        return {}

    print(f"  加载指标: {list(macro_data.keys())}")

    results = {}
    for factor_code in FACTOR_CONFIG.keys():
        df = calculate_single_factor(factor_code, macro_data)
        if not df.empty:
            results[factor_code] = df
            name = FACTOR_CONFIG[factor_code]['name']
            print(f"  ✓ {factor_code} ({name}): {len(df)} 条记录")

    return results


# ============================================================
# 保存数据
# ============================================================

INSERT_SQL = """
    INSERT INTO macro_factors (date, indicator, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value)
"""


def save_factors(factor_code: str, df: pd.DataFrame) -> int:
    """
    保存因子数据到数据库

    Args:
        factor_code: 因子代码
        df: DataFrame with index=date, columns=[value]

    Returns:
        int: 保存记录数
    """
    if df.empty:
        return 0

    rows = []
    for trade_date, row in df.iterrows():
        date_str = trade_date.strftime('%Y-%m-%d')
        value = float(row['value']) if pd.notna(row['value']) else None
        rows.append((date_str, factor_code, value))

    if rows:
        execute_dual_many(INSERT_SQL, rows)

    return len(rows)


def save_all_factors(all_factors: dict) -> int:
    """
    保存所有因子

    Args:
        all_factors: {factor_code: DataFrame}

    Returns:
        int: 总保存记录数
    """
    total = 0
    for factor_code, df in all_factors.items():
        count = save_factors(factor_code, df)
        total += count
    return total


# ============================================================
# 增量更新
# ============================================================

def get_latest_factor_date(factor_code: str) -> Optional[str]:
    """
    获取某个因子在数据库中的最新日期

    Args:
        factor_code: 因子代码

    Returns:
        最新日期字符串 (YYYY-MM-DD) 或 None
    """
    rows = execute_query(
        "SELECT MAX(date) as max_date FROM macro_factors WHERE indicator = %s",
        (factor_code,)
    )
    if rows and rows[0]['max_date']:
        return rows[0]['max_date'].strftime('%Y-%m-%d')
    return None


def incremental_update():
    """
    增量更新所有宏观因子

    只计算数据库中最新日期之后的数据
    """
    print("=" * 60)
    print("宏观因子增量更新")
    print("=" * 60)

    # 获取每个因子的最新日期
    latest_dates = {}
    for factor_code in FACTOR_CONFIG.keys():
        latest = get_latest_factor_date(factor_code)
        if latest:
            latest_dates[factor_code] = latest
            print(f"  {factor_code}: 最新日期 {latest}")
        else:
            print(f"  {factor_code}: 无历史数据，将全量计算")

    # 如果有历史数据，从最早的日期开始加载原始数据
    if latest_dates:
        earliest = min(latest_dates.values())
        # 往前多加载30天，确保窗口计算正确
        start_dt = pd.to_datetime(earliest) - timedelta(days=30)
        start_date = start_dt.strftime('%Y-%m-%d')
    else:
        start_date = '2020-01-01'

    # 计算因子
    print(f"\n计算因子 (从 {start_date} 开始)...")
    all_factors = calculate_all_factors(start_date)

    # 过滤只保留新增数据
    print("\n过滤增量数据...")
    filtered_factors = {}
    for factor_code, df in all_factors.items():
        if factor_code in latest_dates:
            latest = pd.to_datetime(latest_dates[factor_code])
            df = df[df.index > latest]
        if not df.empty:
            filtered_factors[factor_code] = df
            print(f"  {factor_code}: {len(df)} 条新数据")

    if not filtered_factors:
        print("\n无新增数据")
        return

    # 保存
    print("\n保存到数据库...")
    total = save_all_factors(filtered_factors)
    print(f"  保存 {total} 条记录")

    _print_summary()


# ============================================================
# 主函数
# ============================================================

def main(backfill: bool = False, start_date: str = '2020-01-01'):
    """
    主函数

    Args:
        backfill: 是否回填历史数据
        start_date: 回填起始日期
    """
    print("=" * 60)
    print("宏观因子计算入库程序")
    print("=" * 60)

    # 确保表存在
    print("\n检查数据库表...")
    ensure_table_exists()
    print("  macro_factors 表就绪")

    if backfill:
        # 全量回填
        print(f"\n[回填模式] 从 {start_date} 开始计算...")
        all_factors = calculate_all_factors(start_date)

        if not all_factors:
            print("  计算结果为空")
            return

        print("\n保存到数据库...")
        total = save_all_factors(all_factors)
        print(f"  保存 {total} 条记录")
    else:
        # 增量更新
        incremental_update()
        return

    _print_summary()


def _print_summary():
    """打印数据库概况"""
    print("\n" + "=" * 60)
    print("数据库概况:")

    summary = execute_query("""
        SELECT
            COUNT(DISTINCT indicator) as indicator_cnt,
            COUNT(*) as row_cnt,
            MIN(date) as min_date,
            MAX(date) as max_date
        FROM macro_factors
    """)

    if summary:
        row = summary[0]
        print(f"  {row['indicator_cnt']} 个因子, {row['row_cnt']:,} 条记录")
        print(f"  日期范围: {row['min_date']} ~ {row['max_date']}")

    # 各因子详情
    details = execute_query("""
        SELECT
            indicator,
            COUNT(*) as cnt,
            MIN(date) as min_date,
            MAX(date) as max_date
        FROM macro_factors
        GROUP BY indicator
        ORDER BY indicator
    """)

    if details:
        print("\n  各因子详情:")
        for d in details:
            name = FACTOR_CONFIG.get(d['indicator'], {}).get('name', d['indicator'])
            print(f"    - {name} ({d['indicator']}): {d['cnt']} 条, {d['min_date']} ~ {d['max_date']}")

    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='宏观因子计算')
    parser.add_argument('--backfill', action='store_true', help='回填历史数据')
    parser.add_argument('--start', type=str, default='2020-01-01', help='回填起始日期')
    args = parser.parse_args()

    main(backfill=args.backfill, start_date=args.start)
