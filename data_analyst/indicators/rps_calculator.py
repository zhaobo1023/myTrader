# -*- coding: utf-8 -*-
"""
全市场 RPS (Relative Price Strength) 计算器

计算全 A 股多窗口 RPS + RPS 动量斜率，支持全量回填和每日增量更新。

使用方式:
    # 全量回填
    python -m data_analyst.indicators.rps_calculator --backfill

    # 增量更新（仅最新交易日）
    python -m data_analyst.indicators.rps_calculator --latest

    # 指定环境
    python -m data_analyst.indicators.rps_calculator --latest --env online
"""
import sys
import os
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd
import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, execute_many, execute_dual_many, get_dual_connections

logger = logging.getLogger(__name__)

# RPS 计算窗口
RPS_WINDOWS = [20, 60, 120, 250]

# RPS Slope 参数
SLOPE_WINDOW = 20  # 滚动窗口（交易日），约 4 周

# 增量更新时加载的自然日天数
# rps_250 需要 250 交易日，slope 再需要 20 交易日，共约 270 交易日
# 270 交易日 ≈ 378 自然日，加 buffer 取 560 天（约 400 交易日）
INCREMENTAL_LOOKBACK_DAYS = 560


class RPSCalculator:
    """全市场 RPS 计算器"""

    def __init__(self, windows: List[int] = None):
        self.windows = windows or RPS_WINDOWS

    def calc_rps(self, df: pd.DataFrame, window: int) -> pd.Series:
        """
        计算单窗口 RPS

        算法：对每只股票计算 window 日涨幅，然后在每个交易日截面上做排名百分位。

        Args:
            df: DataFrame with columns [stock_code, trade_date, close]
            window: 回溯天数（交易日）

        Returns:
            Series with RPS values (0-100), indexed by original df index
        """
        df = df.copy()
        df = df.sort_values(['stock_code', 'trade_date'])

        # 计算 window 日涨幅
        df['rolling_return'] = df.groupby('stock_code')['close'].transform(
            lambda x: x.pct_change(periods=window)
        )

        # 截面排名（百分位 × 100）
        df['rps'] = df.groupby('trade_date')['rolling_return'].transform(
            lambda x: x.rank(pct=True, na_option='keep') * 100
        )

        return df['rps']

    def calc_rps_slope(self, rps_250: pd.Series, trade_dates: pd.Series,
                       stock_codes: pd.Series, window: int = SLOPE_WINDOW) -> pd.Series:
        """
        计算 RPS 动量斜率 Z-Score

        对每只股票的 rps_250 序列取 window 日滚动窗口做线性回归取斜率，
        然后每日截面对所有股票的斜率做 Z-Score 标准化。

        Args:
            rps_250: RPS(250) 值 Series
            trade_dates: 交易日期 Series
            stock_codes: 股票代码 Series
            window: 滚动窗口天数

        Returns:
            Series with Z-Score values, indexed by original
        """
        df = pd.DataFrame({
            'stock_code': stock_codes,
            'trade_date': trade_dates,
            'rps_250': rps_250,
        })
        df = df.sort_values(['stock_code', 'trade_date'])

        def _slope(y):
            valid = y.dropna()
            if len(valid) < window:
                return np.nan
            x_vals = np.arange(len(valid))
            try:
                slope, _, _, _, _ = stats.linregress(x_vals, valid.values)
                return slope
            except (ValueError, np.linalg.LinAlgError):
                return np.nan

        df['slope_raw'] = df.groupby('stock_code')['rps_250'].transform(
            lambda x: x.rolling(window=window, min_periods=window).apply(_slope, raw=False)
        )

        # 截面 Z-Score 标准化（全 NaN 时保持 NaN，不写 0）
        def _zscore(x):
            s = x.std()
            if s > 0:
                return (x - x.mean()) / s
            return pd.Series(np.nan, index=x.index)

        df['slope_z'] = df.groupby('trade_date')['slope_raw'].transform(_zscore)

        return df['slope_z']

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有窗口的 RPS + RPS slope

        Args:
            df: DataFrame with columns [stock_code, trade_date, close]

        Returns:
            DataFrame with added columns: rps_20, rps_60, rps_120, rps_250, rps_slope
        """
        df = df.copy()
        df = df.sort_values(['stock_code', 'trade_date'])

        for window in self.windows:
            col = f'rps_{window}'
            logger.info(f"计算 RPS({window})...")
            df[col] = self.calc_rps(df, window)

        # RPS slope 基于 rps_250
        logger.info("计算 RPS slope...")
        df['rps_slope'] = self.calc_rps_slope(
            df['rps_250'], df['trade_date'], df['stock_code']
        )

        logger.info("RPS 计算完成")
        return df


class RPSStorage:
    """RPS 数据存储层"""

    UPSERT_SQL = """
        INSERT INTO trade_stock_rps
            (stock_code, trade_date, rps_20, rps_60, rps_120, rps_250, rps_slope)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            rps_20 = VALUES(rps_20),
            rps_60 = VALUES(rps_60),
            rps_120 = VALUES(rps_120),
            rps_250 = VALUES(rps_250),
            rps_slope = VALUES(rps_slope)
    """

    def __init__(self, env: str = 'online'):
        self.env = env

    def init_table(self):
        """创建表（如果不存在）"""
        from config.models import TRADE_STOCK_RPS_SQL
        from config.db import get_connection
        conn = get_connection(self.env)
        cursor = conn.cursor()
        cursor.execute(TRADE_STOCK_RPS_SQL)
        conn.commit()
        cursor.close()
        conn.close()

        # Dual-write: create table on secondary too
        try:
            _, conn2 = get_dual_connections(primary_env=self.env, secondary_env=None)
        except Exception:
            conn2 = None
        if conn2:
            try:
                cursor2 = conn2.cursor()
                cursor2.execute(TRADE_STOCK_RPS_SQL)
                conn2.commit()
                cursor2.close()
            except Exception as e:
                logger.warning("Dual-write init_table failed: %s", e)
            finally:
                conn2.close()

        logger.info("trade_stock_rps 表已就绪")

    def save(self, df: pd.DataFrame, batch_size: int = 1000) -> int:
        """
        批量保存 RPS 数据到数据库

        Args:
            df: DataFrame with columns [stock_code, trade_date, rps_20, rps_60, rps_120, rps_250, rps_slope]
            batch_size: 每批写入行数

        Returns:
            写入总行数
        """
        if df.empty:
            return 0

        cols = ['stock_code', 'trade_date', 'rps_20', 'rps_60', 'rps_120', 'rps_250', 'rps_slope']
        df = df[cols].copy()

        # 确保日期格式
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')

        # 替换 NaN/inf 为 None（SQL NULL）
        df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

        records = [tuple(x) for x in df.itertuples(index=False, name=None)]

        total = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            affected = execute_dual_many(self.UPSERT_SQL, batch, env=self.env)
            total += affected
            logger.debug(f"批次 {i // batch_size + 1}: 写入 {affected} 行")

        logger.info(f"RPS 数据入库完成: 共 {total} 行")
        return total

    def get_latest_date(self) -> Optional[str]:
        """获取已计算的最新日期"""
        rows = execute_query(
            "SELECT MAX(trade_date) as latest FROM trade_stock_rps",
            env=self.env
        )
        if rows and rows[0]['latest']:
            return str(rows[0]['latest'])
        return None

    def get_date_range(self) -> Tuple[Optional[str], Optional[str]]:
        """获取已计算的日期范围"""
        rows = execute_query(
            "SELECT MIN(trade_date) as min_date, MAX(trade_date) as max_date, "
            "COUNT(DISTINCT trade_date) as days FROM trade_stock_rps",
            env=self.env
        )
        if rows:
            r = rows[0]
            return r.get('min_date'), r.get('max_date'), r.get('days', 0)
        return None, None, 0


def _recalc_slope_only(env: str, last_calc_date: str, latest_trade_date: str) -> int:
    """
    从 trade_stock_rps 里读已有的 rps_250 历史，重算 slope 并写回。
    这样截面排名是全市场的，不受分批影响。
    """
    from config.db import get_connection

    # 加载最近 SLOPE_WINDOW+10 天的 rps_250（足够算斜率）
    lookback_days = SLOPE_WINDOW + 10
    # 往前取足够的日期：从 last_calc_date 往前 SLOPE_WINDOW 天
    rows = execute_query(
        f"""
        SELECT stock_code, trade_date, rps_250
        FROM trade_stock_rps
        WHERE trade_date > DATE_SUB(%s, INTERVAL {lookback_days * 2} DAY)
        ORDER BY stock_code, trade_date
        """,
        (latest_trade_date,), env=env
    )
    if not rows:
        return 0

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['rps_250'] = df['rps_250'].astype(float)

    calc = RPSCalculator()
    df['rps_slope'] = calc.calc_rps_slope(df['rps_250'], df['trade_date'], df['stock_code'])

    # 只更新 last_calc_date 之后的日期
    if last_calc_date:
        df = df[df['trade_date'] > pd.Timestamp(last_calc_date)]

    if df.empty:
        return 0

    # 批量 UPDATE rps_slope
    df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
    records = [
        (float(r['rps_slope']) if r['rps_slope'] is not None else None,
         r['stock_code'],
         r['trade_date'].strftime('%Y-%m-%d'))
        for _, r in df.iterrows()
    ]

    sql = "UPDATE trade_stock_rps SET rps_slope = %s WHERE stock_code = %s AND trade_date = %s"
    conn = get_connection(env=env)
    cursor = conn.cursor()
    updated = 0
    for i in range(0, len(records), 1000):
        batch = records[i:i + 1000]
        cursor.executemany(sql, batch)
        updated += cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"slope 修正完成: 更新 {updated} 行")
    return updated


def load_daily_data(env: str = 'online', start_date: str = None) -> pd.DataFrame:
    """
    从 trade_stock_daily 加载全量日线数据

    Args:
        env: 数据库环境
        start_date: 起始日期 (YYYY-MM-DD)，不传则加载全量

    Returns:
        DataFrame with columns [stock_code, trade_date, close]
    """
    if start_date:
        sql = """
            SELECT stock_code, trade_date, close_price as close
            FROM trade_stock_daily
            WHERE trade_date >= %s
            ORDER BY stock_code, trade_date
        """
        rows = execute_query(sql, (start_date,), env=env)
    else:
        sql = """
            SELECT stock_code, trade_date, close_price as close
            FROM trade_stock_daily
            ORDER BY stock_code, trade_date
        """
        rows = execute_query(sql, env=env)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close'] = df['close'].astype(float)
    logger.info(f"加载日线数据: {len(df)} 条, {df['stock_code'].nunique()} 只股票, "
                f"日期范围 {df['trade_date'].min().date()} ~ {df['trade_date'].max().date()}")
    return df


def rps_backfill(env: str = 'online') -> int:
    """
    全量回填 RPS

    加载全量日线数据，计算所有日期的 RPS，批量入库。

    Returns:
        写入行数
    """
    logger.info("=" * 60)
    logger.info("开始全量 RPS 回填")
    logger.info("=" * 60)

    storage = RPSStorage(env=env)
    storage.init_table()

    # 加载全量数据
    df = load_daily_data(env=env)
    if df.empty:
        logger.error("无日线数据，退出")
        return 0

    # 计算 RPS
    calculator = RPSCalculator()
    result = calculator.calculate(df)

    # 只保留结果列
    output_cols = ['stock_code', 'trade_date', 'rps_20', 'rps_60', 'rps_120', 'rps_250', 'rps_slope']
    result = result[output_cols]

    # 入库
    total = storage.save(result)

    logger.info("=" * 60)
    logger.info(f"全量回填完成: {total} 行")
    logger.info("=" * 60)
    return total


def rps_daily_update(env: str = 'online', batch_size: int = 500) -> int:
    """
    每日增量更新 RPS

    策略：分批按股票加载日线数据，避免全量加载导致 MySQL 连接超时。
    每批 batch_size 只股票，加载 INCREMENTAL_LOOKBACK_DAYS 天历史，
    计算 RPS + slope 后写入，再处理下一批。

    Returns:
        写入行数
    """
    logger.info("=" * 60)
    logger.info("开始增量 RPS 更新（分批模式）")
    logger.info("=" * 60)

    storage = RPSStorage(env=env)
    storage.init_table()

    # 检查已计算日期
    last_calc_date = storage.get_latest_date()
    logger.info(f"已计算的最新日期: {last_calc_date or '无'}")

    # 检查数据表最新日期
    rows = execute_query(
        "SELECT MAX(trade_date) as latest FROM trade_stock_daily", env=env
    )
    latest_trade_date = str(rows[0]['latest']) if rows else None

    if not latest_trade_date:
        logger.error("trade_stock_daily 无数据")
        return 0

    logger.info(f"trade_stock_daily 最新日期: {latest_trade_date}")

    if last_calc_date and last_calc_date >= latest_trade_date:
        logger.info("RPS 已是最新，无需更新")
        return 0

    # 获取全量股票列表
    stock_rows = execute_query(
        "SELECT DISTINCT stock_code FROM trade_stock_daily WHERE trade_date >= %s",
        (latest_trade_date,), env=env
    )
    all_codes = [r['stock_code'] for r in stock_rows]
    logger.info(f"待处理股票数: {len(all_codes)}，分批大小: {batch_size}")

    start_date = (datetime.now() - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    calculator = RPSCalculator()
    total = 0
    last_dt = pd.Timestamp(last_calc_date) if last_calc_date else None

    for i in range(0, len(all_codes), batch_size):
        batch_codes = all_codes[i:i + batch_size]
        logger.info(f"处理批次 {i // batch_size + 1}/{(len(all_codes) + batch_size - 1) // batch_size}，"
                    f"股票 {i + 1}~{min(i + batch_size, len(all_codes))}")

        # 加载该批股票的日线数据
        ph = ','.join(['%s'] * len(batch_codes))
        sql = f"""
            SELECT stock_code, trade_date, close_price as close
            FROM trade_stock_daily
            WHERE trade_date >= %s AND stock_code IN ({ph})
            ORDER BY stock_code, trade_date
        """
        rows = execute_query(sql, [start_date] + batch_codes, env=env)
        if not rows:
            continue

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['close'] = df['close'].astype(float)

        # 计算 RPS（截面排名在全市场，批次内只有部分股票会影响精度，
        # 但截面 rps_250 排名通过下面的 UPDATE slope 方式规避）
        result = calculator.calculate(df)

        # 只保留需要入库的日期
        if last_dt is not None:
            result = result[result['trade_date'] > last_dt]

        if result.empty:
            continue

        output_cols = ['stock_code', 'trade_date', 'rps_20', 'rps_60', 'rps_120', 'rps_250', 'rps_slope']
        result = result[output_cols]
        affected = storage.save(result)
        total += affected
        logger.info(f"  批次写入 {affected} 行")

    # slope 需要全市场截面才准确，分批计算有偏差
    # 补跑一次全市场 slope 修正（只更新 rps_slope 列）
    logger.info("补跑全市场 slope 截面修正...")
    total += _recalc_slope_only(env=env, last_calc_date=last_calc_date,
                                latest_trade_date=latest_trade_date)

    logger.info("=" * 60)
    logger.info(f"增量更新完成: 共写入 {total} 行")
    logger.info("=" * 60)
    return total


def main():
    parser = argparse.ArgumentParser(description='全市场 RPS 计算器')
    parser.add_argument(
        '--backfill',
        action='store_true',
        help='全量回填（首次使用或重建）'
    )
    parser.add_argument(
        '--latest',
        action='store_true',
        help='增量更新（仅计算最新交易日）'
    )
    parser.add_argument(
        '--env',
        type=str,
        default='online',
        choices=['local', 'online'],
        help='数据库环境 (默认 online)'
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    if not args.backfill and not args.latest:
        parser.print_help()
        print("\n请指定 --backfill 或 --latest")
        sys.exit(1)

    if args.backfill:
        rps_backfill(env=args.env)
    else:
        rps_daily_update(env=args.env)


if __name__ == '__main__':
    main()
