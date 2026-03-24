# -*- coding: utf-8 -*-
"""
宏观数据拉取器 (Macro Data Fetcher)

功能:
    1. 使用 AkShare 拉取外部宏观数据
    2. 支持增量更新
    3. 存入 MySQL 的 macro_data 表

数据源:
    - WTI原油价格: futures_foreign_hist(symbol='CL')
    - 黄金价格: futures_foreign_hist(symbol='XAU')
    - 中国波指(类VIX): index_option_50etf_qvix()
    - 北向资金: stock_hsgt_hist_em(symbol='北向资金')

运行:
    python data_analyst/fetchers/macro_fetcher.py

环境:
    pip install akshare
"""
import sys
import os
from datetime import date, timedelta
from typing import Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import get_connection, execute_query, execute_many

# 尝试导入 akshare
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("警告: AKShare 未安装，请运行 pip install akshare")


# ============================================================
# 配置
# ============================================================
MACRO_DATA_START = '20200101'  # 默认起始日期


# ============================================================
# 数据源配置
# ============================================================
# 每个指标的配置: (名称, 数据源类型, 参数)
MACRO_INDICATORS = {
    'wti_oil': {
        'name': 'WTI原油',
        'source': 'futures_foreign_hist',
        'params': {'symbol': 'CL'},
        'value_column': 'close',  # 取收盘价
        'date_column': 'date',
    },
    'gold': {
        'name': '黄金',
        'source': 'futures_foreign_hist',
        'params': {'symbol': 'XAU'},
        'value_column': 'close',
        'date_column': 'date',
    },
    'qvix': {
        'name': '中国波指(50ETF期权VIX)',
        'source': 'index_option_50etf_qvix',
        'params': {},
        'value_column': 'close',
        'date_column': 'date',
    },
    'north_flow': {
        'name': '北向资金净流入',
        'source': 'stock_hsgt_hist_em',
        'params': {'symbol': '北向资金'},
        'value_column': '当日成交净买额',
        'date_column': '日期',
    },
}


# ============================================================
# 数据库操作
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS macro_data (
    date DATE NOT NULL COMMENT '日期',
    indicator VARCHAR(50) NOT NULL COMMENT '指标代码',
    value DECIMAL(20, 4) COMMENT '数值',
    PRIMARY KEY (date, indicator),
    INDEX idx_indicator (indicator),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观数据表';
"""


def ensure_table_exists():
    """确保 macro_data 表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()
    conn.close()


def get_latest_date(indicator: str) -> Optional[str]:
    """
    获取某个指标在数据库中的最新日期

    Args:
        indicator: 指标代码

    Returns:
        最新日期字符串 (YYYY-MM-DD) 或 None
    """
    rows = execute_query(
        "SELECT MAX(date) as max_date FROM macro_data WHERE indicator = %s",
        (indicator,)
    )
    if rows and rows[0]['max_date']:
        return rows[0]['max_date'].strftime('%Y-%m-%d')
    return None


# ============================================================
# 数据拉取函数
# ============================================================

def fetch_wti_oil(start_date: str) -> pd.DataFrame:
    """
    拉取 WTI 原油价格

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.futures_foreign_hist(symbol='CL')
    if df is None or df.empty:
        return pd.DataFrame()

    # 确保日期格式一致
    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'close']].rename(columns={'close': 'value'})

    # 过滤日期
    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_gold(start_date: str) -> pd.DataFrame:
    """
    拉取黄金价格

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.futures_foreign_hist(symbol='XAU')
    if df is None or df.empty:
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'close']].rename(columns={'close': 'value'})

    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_qvix(start_date: str) -> pd.DataFrame:
    """
    拉取中国波指(50ETF期权波动率指数)

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.index_option_50etf_qvix()
    if df is None or df.empty:
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'close']].rename(columns={'close': 'value'})

    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_north_flow(start_date: str) -> pd.DataFrame:
    """
    拉取北向资金净流入

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.stock_hsgt_hist_em(symbol='北向资金')
    if df is None or df.empty:
        return pd.DataFrame()

    df['日期'] = pd.to_datetime(df['日期'])
    df = df[['日期', '当日成交净买额']].rename(columns={'日期': 'date', '当日成交净买额': 'value'})

    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


# ============================================================
# 数据拉取映射
# ============================================================
FETCH_FUNCTIONS = {
    'wti_oil': fetch_wti_oil,
    'gold': fetch_gold,
    'qvix': fetch_qvix,
    'north_flow': fetch_north_flow,
}


# ============================================================
# 保存数据
# ============================================================

INSERT_SQL = """
    INSERT INTO macro_data (date, indicator, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value)
"""


def save_data(indicator: str, df: pd.DataFrame) -> int:
    """
    保存数据到数据库

    Args:
        indicator: 指标代码
        df: DataFrame with columns: [date, value]

    Returns:
        写入的记录数
    """
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        value = float(row['value']) if pd.notna(row['value']) else None
        rows.append((date_str, indicator, value))

    if rows:
        execute_many(INSERT_SQL, rows)

    return len(rows)


# ============================================================
# 主拉取函数
# ============================================================

def fetch_indicator(indicator: str) -> Tuple[bool, int, str]:
    """
    拉取单个指标数据

    Args:
        indicator: 指标代码

    Returns:
        (是否成功, 写入记录数, 错误信息)
    """
    if indicator not in FETCH_FUNCTIONS:
        return False, 0, f"未知指标: {indicator}"

    config = MACRO_INDICATORS.get(indicator, {})
    indicator_name = config.get('name', indicator)

    try:
        # 获取数据库中最新日期
        latest_date = get_latest_date(indicator)
        if latest_date:
            # 增量更新：从最新日期的下一天开始
            start_dt = pd.to_datetime(latest_date) + timedelta(days=1)
            start_date = start_dt.strftime('%Y%m%d')
        else:
            # 全量拉取
            start_date = MACRO_DATA_START

        # 检查是否需要拉取
        if latest_date:
            today = date.today().strftime('%Y-%m-%d')
            if latest_date >= today:
                return True, 0, "已是最新"

        # 拉取数据
        fetch_func = FETCH_FUNCTIONS[indicator]
        df = fetch_func(start_date)

        if df.empty:
            return True, 0, "无新数据"

        # 保存数据
        count = save_data(indicator, df)

        return True, count, None

    except Exception as e:
        return False, 0, str(e)


def fetch_all_indicators() -> dict:
    """
    拉取所有宏观数据指标

    Returns:
        结果字典 {indicator: (success, count, error)}
    """
    results = {}

    for indicator in FETCH_FUNCTIONS.keys():
        success, count, error = fetch_indicator(indicator)
        results[indicator] = {
            'success': success,
            'count': count,
            'error': error,
            'name': MACRO_INDICATORS.get(indicator, {}).get('name', indicator),
        }

    return results


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("宏观数据采集 (AkShare -> MySQL)")
    print("=" * 60)

    if not HAS_AKSHARE:
        print("\n错误: AKShare 未安装，请运行 pip install akshare")
        return

    # 确保表存在
    print("\n检查数据库表...")
    ensure_table_exists()
    print("  macro_data 表就绪")

    # 拉取所有指标
    print("\n开始拉取宏观数据...")
    results = fetch_all_indicators()

    # 打印结果
    print("\n" + "-" * 60)
    print("拉取结果:")
    total_count = 0
    success_count = 0
    fail_count = 0

    for indicator, result in results.items():
        status = "✓" if result['success'] else "✗"
        name = result['name']
        count = result['count']
        error = result['error']

        if result['success']:
            success_count += 1
            total_count += count
            print(f"  {status} {name} ({indicator}): {count} 条记录")
            if error:
                print(f"      备注: {error}")
        else:
            fail_count += 1
            print(f"  {status} {name} ({indicator}): 失败 - {error}")

    print("\n" + "=" * 60)
    print(f"采集完成! 成功: {success_count}, 失败: {fail_count}, 总写入: {total_count} 条")

    # 打印数据库概况
    _print_summary()


def _print_summary():
    """打印数据库概况"""
    summary = execute_query("""
        SELECT
            COUNT(DISTINCT indicator) as indicator_cnt,
            COUNT(*) as row_cnt,
            MIN(date) as min_date,
            MAX(date) as max_date
        FROM macro_data
    """)

    if summary:
        row = summary[0]
        print(f"\n数据库 macro_data 概况:")
        print(f"  {row['indicator_cnt']} 个指标, {row['row_cnt']:,} 条记录")
        print(f"  日期范围: {row['min_date']} ~ {row['max_date']}")

    # 各指标详情
    details = execute_query("""
        SELECT
            indicator,
            COUNT(*) as cnt,
            MIN(date) as min_date,
            MAX(date) as max_date
        FROM macro_data
        GROUP BY indicator
        ORDER BY indicator
    """)

    if details:
        print("\n  各指标详情:")
        for d in details:
            name = MACRO_INDICATORS.get(d['indicator'], {}).get('name', d['indicator'])
            print(f"    - {name}: {d['cnt']} 条, {d['min_date']} ~ {d['max_date']}")

    print("=" * 60)


if __name__ == "__main__":
    main()
