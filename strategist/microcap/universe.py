# -*- coding: utf-8 -*-
"""
动态股票池构建

每日市值后 percentile 的股票列表，排除 ST/*ST 和 PE_TTM <= 0 的股票。
支持财务风险过滤（亏损、高负债、负经营现金流）。
"""
import logging
from typing import List

import pandas as pd

from config.db import get_connection

logger = logging.getLogger(__name__)


def get_daily_universe(trade_date: str, percentile: float = 0.20,
                       exclude_st: bool = True, min_pe_ttm: float = 0.0,
                       require_positive_pe: bool = True,
                       min_avg_turnover: float = 0.0,
                       exclude_risk: bool = False,
                       max_debt_ratio: float = 0.70,
                       require_positive_profit: bool = True,
                       require_positive_cashflow: bool = True) -> List[str]:
    """
    获取指定日期的股票池（市值后 percentile 的股票）。

    Args:
        trade_date: 交易日期，格式 'YYYY-MM-DD'
        percentile: 市值百分位，0.20 表示市值后 20%
        exclude_st: 是否排除 ST/*ST 股票
        min_pe_ttm: PE_TTM 最小值，排除 <= 此值的股票
        require_positive_pe: 是否要求 PE_TTM > 0
        min_avg_turnover: 近 5 日平均成交额最低要求（元），0 表示不过滤
        exclude_risk: 是否启用财务风险过滤
        max_debt_ratio: 资产负债率上限（0.70 = 70%），排除超过此值的股票
        require_positive_profit: 要求最近年报净利润 > 0
        require_positive_cashflow: 要求最近年报经营现金流 > 0

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

        # 成交额流动性过滤：剔除近 5 日平均成交额低于阈值的股票
        if min_avg_turnover > 0 and not df.empty:
            stock_codes = df['stock_code'].tolist()
            placeholders = ','.join(['%s'] * len(stock_codes))
            sql_turnover = f"""
                SELECT stock_code, AVG(amount) AS avg_amount
                FROM trade_stock_daily
                WHERE stock_code IN ({placeholders})
                  AND trade_date <= %s
                  AND trade_date >= DATE_SUB(%s, INTERVAL 10 DAY)
                GROUP BY stock_code
                HAVING COUNT(*) >= 3
            """
            df_turnover = pd.read_sql(
                sql_turnover, conn,
                params=stock_codes + [trade_date, trade_date]
            )
            if not df_turnover.empty:
                liquid_codes = set(
                    df_turnover[df_turnover['avg_amount'] >= min_avg_turnover]['stock_code']
                )
                before = len(df)
                df = df[df['stock_code'].isin(liquid_codes)]
                logger.debug(f"{trade_date}: 流动性过滤: {before} -> {len(df)} "
                             f"(剔除 {before - len(df)} 只，阈值={min_avg_turnover:.0f}元)")

        # 财务风险过滤：排除亏损、高负债、负经营现金流的股票
        if exclude_risk and not df.empty:
            stock_codes = df['stock_code'].tolist()
            trade_year = int(trade_date[:4])
            trade_month = int(trade_date[5:7])
            # PIT 规则：4月底前用前年年报，之后用上年年报
            report_year = trade_year - 1 if trade_month <= 4 else trade_year
            placeholders = ','.join(['%s'] * len(stock_codes))
            sql_fin = f"""
                SELECT f1.stock_code, f1.net_profit, f1.debt_ratio, f1.operating_cashflow
                FROM trade_stock_financial f1
                INNER JOIN (
                    SELECT stock_code, MAX(report_date) AS latest_date
                    FROM trade_stock_financial
                    WHERE stock_code IN ({placeholders})
                      AND report_date <= %s
                      AND MONTH(report_date) = 12
                    GROUP BY stock_code
                ) f2 ON f1.stock_code = f2.stock_code AND f1.report_date = f2.latest_date
            """
            try:
                report_cutoff = f'{report_year}-12-31'
                df_fin = pd.read_sql(sql_fin, conn, params=stock_codes + [report_cutoff])
                if not df_fin.empty:
                    exclude_codes = set()
                    if require_positive_profit:
                        loss_codes = set(df_fin[df_fin['net_profit'] <= 0]['stock_code'])
                        exclude_codes |= loss_codes
                    if max_debt_ratio < 1.0:
                        # debt_ratio in DB is percentage (e.g., 70 means 70%)
                        high_debt = set(df_fin[df_fin['debt_ratio'] > max_debt_ratio * 100]['stock_code'])
                        exclude_codes |= high_debt
                    if require_positive_cashflow:
                        neg_cf = set(df_fin[
                            (df_fin['operating_cashflow'].notna()) &
                            (df_fin['operating_cashflow'] <= 0)
                        ]['stock_code'])
                        exclude_codes |= neg_cf
                    before = len(df)
                    df = df[~df['stock_code'].isin(exclude_codes)]
                    logger.debug(f"{trade_date}: 财务风险过滤: {before} -> {len(df)} "
                                 f"(剔除 {before - len(df)} 只)")
            except Exception as e:
                logger.warning(f"{trade_date}: 财务风险过滤失败: {e}")
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
