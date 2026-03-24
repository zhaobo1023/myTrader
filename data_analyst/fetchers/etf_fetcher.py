# -*- coding: utf-8 -*-
"""
ETF 数据拉取器 (ETF Data Fetcher)

功能:
    1. 使用 AkShare 拉取 ETF 日线数据
    2. 支持增量更新
    3. 存入 MySQL 的 etf_daily 表

运行:
    python data_analyst/fetchers/etf_fetcher.py

环境:
    pip install akshare
"""
import sys
import os
from datetime import date, timedelta
from typing import List, Optional, Tuple

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

# 默认 ETF 列表
DEFAULT_ETFS = {
    '159930': '能源化工ETF',
    '515220': '煤炭ETF',
    '518880': '黄金ETF',
    '513130': '恒生科技ETF',
}

ETF_DATA_START = '20200101'


# ============================================================
# 数据库表结构
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS etf_daily (
    id INT AUTO_INCREMENT PRIMARY KEY,
    etf_code VARCHAR(10) NOT NULL COMMENT 'ETF代码',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open_price DECIMAL(10, 4) COMMENT '开盘价',
    high_price DECIMAL(10, 4) COMMENT '最高价',
    low_price DECIMAL(10, 4) COMMENT '最低价',
    close_price DECIMAL(10, 4) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量',
    amount DECIMAL(18, 2) COMMENT '成交额',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (etf_code, trade_date),
    KEY idx_trade_date (trade_date),
    KEY idx_etf_code (etf_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ETF日线行情表';
"""


def ensure_table_exists():
    """确保 etf_daily 表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()
    conn.close()


def get_latest_date(etf_code: str) -> Optional[str]:
    """
    获取某个 ETF 在数据库中的最新日期

    Args:
        etf_code: ETF 代码

    Returns:
        最新日期字符串 (YYYY-MM-DD) 或 None
    """
    rows = execute_query(
        "SELECT MAX(trade_date) as max_date FROM etf_daily WHERE etf_code = %s",
        (etf_code,)
    )
    if rows and rows[0]['max_date']:
        return rows[0]['max_date'].strftime('%Y-%m-%d')
    return None


# ============================================================
# 数据拉取
# ============================================================

def fetch_etf_data(etf_code: str, start_date: str) -> pd.DataFrame:
    """
    拉取单个 ETF 的日线数据

    Args:
        etf_code: ETF 代码 (如 '159930')
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [trade_date, open, high, low, close, volume, amount]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    end_date = date.today().strftime('%Y%m%d')

    try:
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period='daily',
            start_date=start_date,
            end_date=end_date,
            adjust='qfq'
        )

        if df is None or df.empty:
            return pd.DataFrame()

        # 重命名列
        df = df.rename(columns={
            '日期': 'trade_date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
        })

        # 转换日期
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        return df[['trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount']]

    except Exception as e:
        print(f"  拉取 {etf_code} 失败: {e}")
        return pd.DataFrame()


# ============================================================
# 保存数据
# ============================================================

INSERT_SQL = """
    INSERT INTO etf_daily (etf_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    open_price = VALUES(open_price),
    high_price = VALUES(high_price),
    low_price = VALUES(low_price),
    close_price = VALUES(close_price),
    volume = VALUES(volume),
    amount = VALUES(amount)
"""


def save_etf_data(etf_code: str, df: pd.DataFrame) -> int:
    """
    保存 ETF 数据到数据库

    Args:
        etf_code: ETF 代码
        df: DataFrame

    Returns:
        保存记录数
    """
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        rows.append((
            etf_code,
            row['trade_date'].strftime('%Y-%m-%d'),
            float(row['open']) if pd.notna(row.get('open')) else None,
            float(row['high']) if pd.notna(row.get('high')) else None,
            float(row['low']) if pd.notna(row.get('low')) else None,
            float(row['close']) if pd.notna(row.get('close')) else None,
            int(row['volume']) if pd.notna(row.get('volume')) else None,
            float(row['amount']) if pd.notna(row.get('amount')) else None,
        ))

    if rows:
        execute_many(INSERT_SQL, rows)

    return len(rows)


# ============================================================
# 主拉取函数
# ============================================================

def fetch_single_etf(etf_code: str) -> Tuple[bool, int, str]:
    """
    拉取单个 ETF 数据

    Args:
        etf_code: ETF 代码

    Returns:
        (是否成功, 写入记录数, 错误信息)
    """
    try:
        # 获取数据库中最新日期
        latest_date = get_latest_date(etf_code)
        if latest_date:
            # 增量更新
            start_dt = pd.to_datetime(latest_date) + timedelta(days=1)
            start_date = start_dt.strftime('%Y%m%d')
        else:
            # 全量拉取
            start_date = ETF_DATA_START

        # 检查是否需要拉取
        if latest_date:
            today = date.today().strftime('%Y-%m-%d')
            if latest_date >= today:
                return True, 0, "已是最新"

        # 拉取数据
        df = fetch_etf_data(etf_code, start_date)

        if df.empty:
            return True, 0, "无新数据"

        # 保存数据
        count = save_etf_data(etf_code, df)

        return True, count, None

    except Exception as e:
        return False, 0, str(e)


def fetch_all_etfs(etf_codes: List[str] = None) -> dict:
    """
    拉取所有 ETF 数据

    Args:
        etf_codes: ETF 代码列表，默认使用 DEFAULT_ETFS

    Returns:
        结果字典
    """
    if etf_codes is None:
        etf_codes = list(DEFAULT_ETFS.keys())

    results = {}

    for etf_code in etf_codes:
        etf_name = DEFAULT_ETFS.get(etf_code, etf_code)
        success, count, error = fetch_single_etf(etf_code)
        results[etf_code] = {
            'success': success,
            'count': count,
            'error': error,
            'name': etf_name,
        }

    return results


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("ETF 数据采集 (AkShare -> MySQL)")
    print("=" * 60)

    if not HAS_AKSHARE:
        print("\n错误: AKShare 未安装，请运行 pip install akshare")
        return

    # 确保表存在
    print("\n检查数据库表...")
    ensure_table_exists()
    print("  etf_daily 表就绪")

    # 拉取所有 ETF
    print("\n开始拉取 ETF 数据...")
    results = fetch_all_etfs()

    # 打印结果
    print("\n" + "-" * 60)
    print("拉取结果:")
    total_count = 0
    success_count = 0

    for etf_code, result in results.items():
        status = "✓" if result['success'] else "✗"
        name = result['name']
        count = result['count']
        error = result['error']

        if result['success']:
            success_count += 1
            total_count += count
            msg = f"{count} 条记录"
            if error:
                msg += f" ({error})"
            print(f"  {status} {name} ({etf_code}): {msg}")
        else:
            print(f"  {status} {name} ({etf_code}): 失败 - {error}")

    print("\n" + "=" * 60)
    print(f"采集完成! 成功: {success_count}/{len(results)}, 总写入: {total_count} 条")

    # 打印数据库概况
    _print_summary()


def _print_summary():
    """打印数据库概况"""
    summary = execute_query("""
        SELECT
            COUNT(DISTINCT etf_code) as etf_cnt,
            COUNT(*) as row_cnt,
            MIN(trade_date) as min_date,
            MAX(trade_date) as max_date
        FROM etf_daily
    """)

    if summary:
        row = summary[0]
        print(f"\n数据库 etf_daily 概况:")
        print(f"  {row['etf_cnt']} 个 ETF, {row['row_cnt']:,} 条记录")
        print(f"  日期范围: {row['min_date']} ~ {row['max_date']}")

    # 各 ETF 详情
    details = execute_query("""
        SELECT
            etf_code,
            COUNT(*) as cnt,
            MIN(trade_date) as min_date,
            MAX(trade_date) as max_date
        FROM etf_daily
        GROUP BY etf_code
        ORDER BY etf_code
    """)

    if details:
        print("\n  各 ETF 详情:")
        for d in details:
            name = DEFAULT_ETFS.get(d['etf_code'], d['etf_code'])
            print(f"    - {name} ({d['etf_code']}): {d['cnt']} 条, {d['min_date']} ~ {d['max_date']}")

    print("=" * 60)


if __name__ == "__main__":
    main()
