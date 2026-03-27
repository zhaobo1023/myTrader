# -*- coding: utf-8 -*-
"""
因子存储模块

功能:
  1. 创建因子数据表
  2. 保存因子计算结果
  3. 加载历史因子数据
  4. 增量更新因子

建表SQL:
  见 create_factor_table()
"""
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.db import execute_query, get_connection


from config.settings import settings


# ============================================================
# 建表SQL
# ============================================================

CREATE_table_sql = """
CREATE TABLE IF NOT EXISTS trade_stock_factor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL COMMENT '股票代码',
    calc_date DATE NOT NULL COMMENT '计算日期(数据截止日期)',

    -- 技术因子
    momentum_20d DOUBLE COMMENT '20日动量 ROC(20)',
    momentum_60d DOUBLE COMMENT '60日动量 ROC(60)',
    volatility DOUBLE COMMENT '波动率 ATR(14)/Close',
    rsi_14 DOUBLE COMMENT 'RSI(14)',
    adx_14 DOUBLE COMMENT 'ADX(14) 趋势强度',
    turnover_ratio DOUBLE COMMENT '换手率 当日量/20日均量',
    price_position DOUBLE COMMENT '价格位置 60日区间内位置',
    macd_signal DOUBLE COMMENT 'MACD柱状图',

    -- 辅助字段
    close DOUBLE COMMENT '收盘价',

    -- 元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 唯一索引: 同一股票同一日期只有一条记录
    UNIQUE KEY uk_code_date (calc_date, stock_code),
    KEY idx_calc_date (calc_date),
    KEY idx_stock_code (stock_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票技术因子表';
"""


def create_factor_table():
    """创建因子数据表"""
    from config.db import get_connection

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_sql)
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ 因子表创建成功: trade_stock_factor")


# ============================================================
# 保存因子
# ============================================================

def save_factors(factor_df, calc_date):
    """
    保存因子计算结果到数据库

    参数:
        factor_df: DataFrame, 索引为stock_code, 列为因子
        calc_date: str or date, 计算日期

    返回:
        int: 成功保存的记录数
    """
    if isinstance(calc_date, str):
        calc_date = pd.to_datetime(calc_date).date()
    elif isinstance(calc_date, datetime):
        calc_date = calc_date.date()

    factor_cols = [
        'momentum_20d', 'momentum_60d', 'volatility', 'rsi_14',
        'adx_14', 'turnover_ratio', 'price_position', 'macd_signal', 'close'
    ]

    conn = get_connection()
    cursor = conn.cursor()

    # 使用 REPLACE INTO 实现 upsert (存在则更新，不存在则插入)
    sql = f"""
        replace into trade_stock_factor
        (stock_code, calc_date, {', '.join(factor_cols)})
        values (%s, %s, {', '.join(['%s'] * len(factor_cols))})
    """

    success_count = 0
    for code, row in factor_df.iterrows():
        try:
            values = [code, calc_date] + [row.get(col, None) for col in factor_cols]
            cursor.execute(sql, values)
            success_count += 1
        except Exception as e:
            print(f"  保存失败 {code}: {e}")

    conn.commit()
    cursor.close()
    conn.close()

    return success_count


def batch_save_factors(factor_df, calc_date, batch_size=500):
    """
    批量保存因子 (大数据量时使用)

    参数:
        factor_df: DataFrame
        calc_date: 计算日期
        batch_size: 每批数量
    """
    if isinstance(calc_date, str):
        calc_date = pd.to_datetime(calc_date).date()

    factor_cols = [
        'momentum_20d', 'momentum_60d', 'volatility', 'rsi_14',
        'adx_14', 'turnover_ratio', 'price_position', 'macd_signal', 'close'
    ]

    conn = get_connection()
    cursor = conn.cursor()

    sql = f"""
        replace into trade_stock_factor
        (stock_code, calc_date, {', '.join(factor_cols)})
        values (%s, %s, {', '.join(['%s'] * len(factor_cols))})
    """

    total = len(factor_df)
    success_count = 0
    batch = []

    for i, (code, row) in enumerate(factor_df.iterrows()):
        values = [code, calc_date] + [row.get(col, None) for col in factor_cols]
        batch.append(values)

        if len(batch) >= batch_size:
            try:
                cursor.executemany(sql, batch)
                conn.commit()
                success_count += len(batch)
                print(f"  保存进度: {success_count}/{total}")
            except Exception as e:
                print(f"  批量保存失败: {e}")
            batch = []

    # 保存剩余
    if batch:
        try:
            cursor.executemany(sql, batch)
            conn.commit()
            success_count += len(batch)
        except Exception as e:
            print(f"  最后一批保存失败: {e}")

    cursor.close()
    conn.close()

    print(f"✅ 保存完成: {success_count}/{total} 条记录")
    return success_count


# ============================================================
# 加载因子
# ============================================================

def load_factors(calc_date, stock_codes=None):
    """
    从数据库加载指定日期的因子数据

    参数:
        calc_date: str or date, 计算日期
        stock_codes: list, 指定股票代码列表 (None=全部)

    返回:
        DataFrame, 索引为stock_code, 列为因子
    """
    if isinstance(calc_date, str):
        calc_date = pd.to_datetime(calc_date).date()

    sql = """
        select stock_code, calc_date, momentum_20d, momentum_60d,
               volatility, rsi_14, adx_14, turnover_ratio,
               price_position, macd_signal, close
        from trade_stock_factor
        where calc_date = %s
    """
    params = [calc_date]

    if stock_codes:
        placeholders = ', '.join(['%s'] * len(stock_codes))
        sql += f" and stock_code in ({placeholders})"
        params.extend(stock_codes)

    rows = execute_query(sql, params)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['stock_code'] = df['stock_code'].astype(str)
    df = df.set_index('stock_code')

    # 转换数值类型
    factor_cols = [
        'momentum_20d', 'momentum_60d', 'volatility', 'rsi_14',
        'adx_14', 'turnover_ratio', 'price_position', 'macd_signal', 'close'
    ]
    for col in factor_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def load_factors_range(start_date, end_date, stock_code=None):
    """
    加载日期范围内的因子数据

    参数:
        start_date: 开始日期
        end_date: 结束日期
        stock_code: 指定股票代码 (None=全部)

    返回:
        DataFrame, 多级索引 (stock_code, calc_date)
    """
    sql = """
        select stock_code, calc_date, momentum_20d, momentum_60d,
               volatility, rsi_14, adx_14, turnover_ratio,
               price_position, macd_signal, close
        from trade_stock_factor
        where calc_date >= %s and calc_date <= %s
    """
    params = [start_date, end_date]

    if stock_code:
        sql += " and stock_code = %s"
        params.append(stock_code)

    sql += " order by stock_code, calc_date"

    rows = execute_query(sql, params)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['calc_date'] = pd.to_datetime(df['calc_date'])
    df = df.set_index(['stock_code', 'calc_date'])

    return df


# ============================================================
# 元数据查询
# ============================================================

def get_latest_factor_date():
    """获取最新的因子计算日期"""
    sql = "select max(calc_date) as latest from trade_stock_factor"
    rows = execute_query(sql)
    if rows and rows[0]['latest']:
        return rows[0]['latest']
    return None


def get_factor_dates():
    """获取所有已计算的因子日期列表"""
    sql = """
        select distinct calc_date, count(*) as stock_count
        from trade_stock_factor
        group by calc_date
        order by calc_date desc
    """
    return execute_query(sql)


def delete_factors_by_date(calc_date):
    """删除指定日期的因子数据"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("delete from trade_stock_factor where calc_date = %s", [calc_date])
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    return deleted


# ============================================================
# 测试
# ============================================================

if __name__ == '__main__':
    print("=" * 50)
    print("因子存储模块测试")
    print("=" * 50)

    # 1. 创建表
    print("\n[1] 创建因子表...")
    try:
        create_factor_table()
    except Exception as e:
        print(f"  创建失败: {e}")

    # 2. 查询已有数据
    print("\n[2] 查询已计算的因子日期...")
    dates = get_factor_dates()
    if dates:
        print(f"  共 {len(dates)} 个日期")
        for d in dates[:5]:
            print(f"    {d['calc_date']}: {d['stock_count']} 只股票")
    else:
        print("  暂无数据")

    # 3. 获取最新日期
    latest = get_latest_factor_date()
    if latest:
        print(f"\n[3] 最新因子日期: {latest}")
