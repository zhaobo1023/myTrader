# -*- coding: utf-8 -*-
"""
动态股票池构建

每日市值后 percentile 的股票列表，排除 ST/*ST 和 PE_TTM <= 0 的股票。
"""
import logging
from typing import List

import pandas as pd

from config.db import get_connection

logger = logging.getLogger(__name__)


def get_daily_universe(trade_date: str, percentile: float = 0.20,
                       exclude_st: bool = True, min_pe_ttm: float = 0.0,
                       require_positive_pe: bool = True) -> List[str]:
    """
    获取指定日期的股票池（市值后 percentile 的股票）。

    Args:
        trade_date: 交易日期，格式 'YYYY-MM-DD'
        percentile: 市值百分位，0.20 表示市值后 20%
        exclude_st: 是否排除 ST/*ST 股票
        min_pe_ttm: PE_TTM 最小值，排除 <= 此值的股票

    Returns:
        股票代码列表，格式 ['000001.SZ', '600519.SH', ...]
    """
    conn = get_connection()
    try:
        # 构建 SQL：获取指定日期的市值数据
        sql = """
            SELECT
                b.stock_code,
                b.pe_ttm,
                b.total_mv
            FROM trade_stock_daily_basic b
        """
        if exclude_st:
            sql += """
            JOIN trade_stock_basic s
              ON b.stock_code COLLATE utf8mb4_unicode_ci = s.stock_code COLLATE utf8mb4_unicode_ci
             AND s.is_st = 0
            """

        sql += " WHERE b.trade_date = %s"
        params = [trade_date]
        if require_positive_pe:
            sql += " AND b.pe_ttm > %s"
            params.append(min_pe_ttm)
        sql += " AND b.total_mv > 0"
        sql += " ORDER BY b.total_mv ASC"

        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        logger.warning(f"No stocks found for {trade_date}")
        return []

    # 计算市值百分位阈值
    market_cap_threshold = df['total_mv'].quantile(percentile)

    # 筛选市值后 percentile 的股票
    universe = df[df['total_mv'] <= market_cap_threshold]['stock_code'].tolist()

    logger.debug(f"{trade_date}: universe size={len(universe)}, "
                 f"percentile={percentile}, threshold={float(market_cap_threshold):.2e}")

    return universe
