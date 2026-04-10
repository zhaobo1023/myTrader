# -*- coding: utf-8 -*-
"""
因子计算模块

- PEG = PE_TTM / (EPS增速 * 100)
- EPS增速 = (最新年报EPS - 上年EPS) / abs(上年EPS)
"""
import logging
from typing import List

import pandas as pd
import numpy as np

from config.db import get_connection

logger = logging.getLogger(__name__)


def calc_peg(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """
    计算 PEG 因子。

    PEG = PE_TTM / (EPS增速 * 100)
    EPS增速 = (最新年报EPS - 上年EPS) / abs(上年EPS)

    数据来源：
    - trade_stock_daily_basic: PE_TTM
    - trade_stock_financial: EPS（最近两个年报）

    如果 EPS 数据不足，则使用 PE_TTM 作为替代。

    Args:
        trade_date: 交易日期，格式 'YYYY-MM-DD'
        stock_codes: 股票代码列表

    Returns:
        DataFrame，列 [stock_code, peg]
        peg > 0 且 < 1000 才有效，否则为 NaN
    """
    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'peg'])

    conn = get_connection()
    try:
        # Step 1: 获取 PE_TTM
        placeholders = ','.join(['%s'] * len(stock_codes))
        sql_pe = f"""
            SELECT stock_code, pe_ttm
            FROM trade_stock_daily_basic
            WHERE trade_date = %s AND stock_code IN ({placeholders})
        """
        params = [trade_date] + stock_codes
        df_pe = pd.read_sql(sql_pe, conn, params=params)

        if df_pe.empty:
            return pd.DataFrame(columns=['stock_code', 'peg'])

        # Step 2: 获取截至 trade_date 的最近两个年报 EPS
        # 保守 PIT 规则：年报最晚 4 月 30 日才披露完毕。
        # 1-4 月只能使用前一年度及更早的年报，避免使用尚未公告的当年度数据。
        trade_year = int(trade_date[:4])
        trade_month = int(trade_date[5:7])
        if trade_month <= 4:
            max_report_year = trade_year - 1
        else:
            max_report_year = trade_year
        logger.debug(f"PIT rule: trade_date={trade_date}, max_report_year={max_report_year}")

        # 分批查询（每批 50 只），避免大 IN 子句导致 MySQL 写 /tmp 临时文件。
        # 去掉 ORDER BY（在 Python 侧排序），进一步降低 MySQL 产生临时文件的概率。
        EPS_BATCH = 50
        eps_chunks = []
        for batch_start in range(0, len(stock_codes), EPS_BATCH):
            batch = stock_codes[batch_start: batch_start + EPS_BATCH]
            ph = ','.join(['%s'] * len(batch))
            sql_eps = f"""
                SELECT
                    stock_code,
                    YEAR(report_date) AS report_year,
                    eps
                FROM trade_stock_financial
                WHERE stock_code IN ({ph})
                AND MONTH(report_date) = 12
                AND YEAR(report_date) <= %s
            """
            chunk = pd.read_sql(sql_eps, conn, params=batch + [max_report_year])
            if not chunk.empty:
                eps_chunks.append(chunk)
        df_eps = pd.concat(eps_chunks, ignore_index=True) if eps_chunks else pd.DataFrame()

    finally:
        conn.close()

    # Step 3: 计算 EPS 增速
    result = df_pe.set_index('stock_code')[['pe_ttm']].copy()

    if not df_eps.empty:
        # 为每个股票获取最新和上一年的 EPS
        eps_growth_list = []
        for stock_code in df_eps['stock_code'].unique():
            stock_eps = df_eps[df_eps['stock_code'] == stock_code].sort_values('report_year', ascending=False)
            if len(stock_eps) >= 2:
                latest_eps = stock_eps.iloc[0]['eps']
                prior_eps = stock_eps.iloc[1]['eps']
                if prior_eps != 0 and latest_eps is not None and prior_eps is not None:
                    eps_growth = (float(latest_eps) - float(prior_eps)) / np.abs(float(prior_eps))
                    eps_growth_list.append({
                        'stock_code': stock_code,
                        'eps_growth_rate': eps_growth
                    })

        if eps_growth_list:
            eps_growth_df = pd.DataFrame(eps_growth_list).set_index('stock_code')
            result = result.join(eps_growth_df, how='left')
            result['peg'] = result['pe_ttm'] / (result['eps_growth_rate'] * 100)
            # 过滤：peg > 0 且 < 1000 才有效
            result.loc[(result['peg'] <= 0) | (result['peg'] >= 1000), 'peg'] = np.nan
        else:
            # 无有效 EPS 增速数据，使用 PE_TTM 作为替代
            result['peg'] = result['pe_ttm']
    else:
        # 无 EPS 数据，使用 PE_TTM 作为替代
        result['peg'] = result['pe_ttm']

    # 返回指定格式
    result = result[['peg']].reset_index()
    return result[['stock_code', 'peg']]


def calc_peg_ebit_mv(trade_date: str, stock_codes: List[str],
                     peg_pct: float = 0.20,
                     ebit_pct: float = 0.30) -> pd.DataFrame:
    """
    基本面小市值策略（两阶段漏斗）。

    逻辑：
      1. 全市场按 PEG 升序，取最小 peg_pct（默认前20%）
      2. 从中按 EBIT 降序，取最大 ebit_pct（默认前30%）
      3. 最终按总市值升序排列，返回 market_cap 作为排序因子

    调用方排序：sort_values('peg_ebit_mv').head(top_n) 即得到最终选股结果。

    Args:
        trade_date:  交易日期
        stock_codes: 候选股票列表（建议传入全市场或宽泛筛选后的列表）
        peg_pct:     第一阶段保留 PEG 最小的比例
        ebit_pct:    第二阶段保留 EBIT 最大的比例

    Returns:
        DataFrame，列 [stock_code, peg_ebit_mv]（值为总市值，越小排名越靠前）
    """
    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'peg_ebit_mv'])

    conn = get_connection()
    try:
        placeholders = ','.join(['%s'] * len(stock_codes))

        # Step 1: 获取 PE_TTM + 总市值
        sql_pe = f"""
            SELECT stock_code, pe_ttm, total_mv
            FROM trade_stock_daily_basic
            WHERE trade_date = %s AND stock_code IN ({placeholders})
            AND pe_ttm > 0 AND pe_ttm < 1000 AND total_mv > 0
        """
        df_pe = pd.read_sql(sql_pe, conn, params=[trade_date] + stock_codes)

        if df_pe.empty:
            return pd.DataFrame(columns=['stock_code', 'peg_ebit_mv'])

        # Step 2: 获取截至 trade_date 的最近两个年报 EPS（避免前视偏差）
        sql_eps = f"""
            SELECT stock_code, YEAR(report_date) AS report_year, eps
            FROM trade_stock_financial
            WHERE stock_code IN ({placeholders})
            AND report_date <= %s
            AND MONTH(report_date) = 12
            ORDER BY stock_code, report_date DESC
        """
        df_eps = pd.read_sql(sql_eps, conn, params=stock_codes + [trade_date])

        # Step 3: 获取截至 trade_date 的最近年报 EBIT（避免前视偏差）
        sql_ebit = f"""
            SELECT t1.stock_code, t1.ebit
            FROM trade_stock_ebit t1
            INNER JOIN (
                SELECT stock_code, MAX(report_date) AS latest_date
                FROM trade_stock_ebit
                WHERE stock_code IN ({placeholders})
                AND report_date <= %s
                AND MONTH(report_date) = 12
                GROUP BY stock_code
            ) t2 ON t1.stock_code = t2.stock_code AND t1.report_date = t2.latest_date
            WHERE t1.ebit IS NOT NULL AND t1.ebit > 0
        """
        df_ebit = pd.read_sql(sql_ebit, conn, params=stock_codes + [trade_date])

    finally:
        conn.close()

    # 计算 PEG
    result = df_pe.set_index('stock_code')[['pe_ttm', 'total_mv']].copy()

    if not df_eps.empty:
        eps_growth_list = []
        for code in df_eps['stock_code'].unique():
            stock_eps = df_eps[df_eps['stock_code'] == code].sort_values('report_year', ascending=False)
            if len(stock_eps) >= 2:
                latest_eps = stock_eps.iloc[0]['eps']
                prior_eps = stock_eps.iloc[1]['eps']
                if prior_eps and prior_eps != 0 and latest_eps is not None:
                    growth = (float(latest_eps) - float(prior_eps)) / abs(float(prior_eps))
                    if growth > 0:
                        eps_growth_list.append({'stock_code': code, 'eps_growth': growth})
        if eps_growth_list:
            df_growth = pd.DataFrame(eps_growth_list).set_index('stock_code')
            result = result.join(df_growth, how='left')
            result['peg'] = result['pe_ttm'] / (result['eps_growth'] * 100)
            result.loc[(result['peg'] <= 0) | (result['peg'] >= 1000), 'peg'] = np.nan
        else:
            result['peg'] = result['pe_ttm']
    else:
        result['peg'] = result['pe_ttm']

    result = result.dropna(subset=['peg']).reset_index()

    # 漏斗第一层：保留 PEG 最小的 peg_pct
    n_peg = max(1, int(len(result) * peg_pct))
    result = result.nsmallest(n_peg, 'peg')

    if result.empty:
        return pd.DataFrame(columns=['stock_code', 'peg_ebit_mv'])

    # 漏斗第二层：保留 EBIT 最大的 ebit_pct
    if not df_ebit.empty:
        result = result.merge(df_ebit[['stock_code', 'ebit']], on='stock_code', how='left')
        result['ebit'] = pd.to_numeric(result['ebit'], errors='coerce')
        # 只对有 EBIT 数据的股票做第二层筛选；无数据的直接保留
        has_ebit = result.dropna(subset=['ebit'])
        no_ebit = result[result['ebit'].isna()]
        if not has_ebit.empty:
            n_ebit = max(1, int(len(has_ebit) * ebit_pct))
            has_ebit = has_ebit.nlargest(n_ebit, 'ebit')
        result = pd.concat([has_ebit, no_ebit], ignore_index=True)

    if result.empty:
        return pd.DataFrame(columns=['stock_code', 'peg_ebit_mv'])

    # 最终按市值升序：market_cap 即为排序因子（越小越好）
    result['peg_ebit_mv'] = result['total_mv'].astype(float)
    return result[['stock_code', 'peg_ebit_mv']].dropna()


def calc_pure_mv(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """
    垃圾小市值策略：无基本面因子，纯按市值从小到大选股。

    Args:
        trade_date:  交易日期
        stock_codes: 候选股票列表

    Returns:
        DataFrame，列 [stock_code, pure_mv]（值为总市值，越小排名越靠前）
    """
    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'pure_mv'])

    conn = get_connection()
    try:
        placeholders = ','.join(['%s'] * len(stock_codes))
        sql = f"""
            SELECT stock_code, total_mv AS pure_mv
            FROM trade_stock_daily_basic
            WHERE trade_date = %s AND stock_code IN ({placeholders})
            AND total_mv > 0
        """
        df = pd.read_sql(sql, conn, params=[trade_date] + stock_codes)
    finally:
        conn.close()

    return df[['stock_code', 'pure_mv']] if not df.empty else pd.DataFrame(columns=['stock_code', 'pure_mv'])


def calc_pe(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """
    计算 PE_TTM 因子（越小越便宜）。

    直接使用 trade_stock_daily_basic 中的 pe_ttm 字段，
    选取 PE_TTM 最低的股票（价值选股）。

    Args:
        trade_date: 交易日期
        stock_codes: 股票代码列表

    Returns:
        DataFrame，列 [stock_code, pe]
    """
    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'pe'])

    conn = get_connection()
    try:
        placeholders = ','.join(['%s'] * len(stock_codes))
        sql = f"""
            SELECT stock_code, pe_ttm AS pe
            FROM trade_stock_daily_basic
            WHERE trade_date = %s AND stock_code IN ({placeholders})
            AND pe_ttm > 0 AND pe_ttm < 1000
        """
        params = [trade_date] + stock_codes
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    return df[['stock_code', 'pe']] if not df.empty else pd.DataFrame(columns=['stock_code', 'pe'])


def calc_roe(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """
    计算 ROE 因子（越大越好，选最近年报 ROE 最高的股票）。

    ROE = 净资产收益率（来自 trade_stock_financial 年报数据）。
    只取最近一个年报的 ROE（roe 字段）。

    选取逻辑：ROE 越高越好，因此外层排名时需反向（取最大的 top_n）。
    为统一接口（越小排名越靠前），返回 -roe（负值），这样 sort 后最小的就是 ROE 最大的。

    Args:
        trade_date: 交易日期
        stock_codes: 股票代码列表

    Returns:
        DataFrame，列 [stock_code, roe]（值已取负，越小表示 ROE 越高）
    """
    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'roe'])

    conn = get_connection()
    try:
        placeholders = ','.join(['%s'] * len(stock_codes))
        # 取每个股票最近一个年报的 ROE（MONTH=12 的报告期）
        sql = f"""
            SELECT t1.stock_code, t1.roe AS roe_val
            FROM trade_stock_financial t1
            INNER JOIN (
                SELECT stock_code, MAX(report_date) AS latest_date
                FROM trade_stock_financial
                WHERE stock_code IN ({placeholders})
                AND report_date <= %s
                AND MONTH(report_date) = 12
                GROUP BY stock_code
            ) t2 ON t1.stock_code = t2.stock_code AND t1.report_date = t2.latest_date
            WHERE t1.roe IS NOT NULL AND t1.roe > 0
        """
        params = stock_codes + [trade_date]
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame(columns=['stock_code', 'roe'])

    # 取负值，使"越小越好"的排序逻辑选出 ROE 最高的股票
    df['roe'] = -df['roe_val'].astype(float)
    return df[['stock_code', 'roe']]


def calc_ebit_ratio(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """
    计算 EBIT/MV 因子（越大越好）。

    EBIT/MV = 息税前利润 / 总市值，衡量盈利能力相对市场估值。
    数据来源：trade_stock_ebit（EBIT）+ trade_stock_daily_basic（total_mv）。
    返回 -ebit_ratio（负值），使排序逻辑一致（越小越好）。

    Args:
        trade_date: 交易日期
        stock_codes: 股票代码列表

    Returns:
        DataFrame，列 [stock_code, ebit_ratio]（值已取负）
    """
    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'ebit_ratio'])

    conn = get_connection()
    try:
        placeholders = ','.join(['%s'] * len(stock_codes))

        # 获取最近年报 EBIT
        sql_ebit = f"""
            SELECT t1.stock_code, t1.ebit
            FROM trade_stock_ebit t1
            INNER JOIN (
                SELECT stock_code, MAX(report_date) AS latest_date
                FROM trade_stock_ebit
                WHERE stock_code IN ({placeholders})
                AND report_date <= %s
                AND MONTH(report_date) = 12
                GROUP BY stock_code
            ) t2 ON t1.stock_code = t2.stock_code AND t1.report_date = t2.latest_date
            WHERE t1.ebit IS NOT NULL AND t1.ebit > 0
        """
        df_ebit = pd.read_sql(sql_ebit, conn, params=stock_codes + [trade_date])

        if df_ebit.empty:
            return pd.DataFrame(columns=['stock_code', 'ebit_ratio'])

        # 获取总市值
        sql_mv = f"""
            SELECT stock_code, total_mv
            FROM trade_stock_daily_basic
            WHERE trade_date = %s AND stock_code IN ({placeholders})
            AND total_mv > 0
        """
        valid_codes = df_ebit['stock_code'].tolist()
        df_mv = pd.read_sql(sql_mv, conn, params=[trade_date] + valid_codes)

    finally:
        conn.close()

    if df_mv.empty:
        return pd.DataFrame(columns=['stock_code', 'ebit_ratio'])

    df = df_ebit.merge(df_mv, on='stock_code', how='inner')
    # total_mv 单位亿元，ebit 单位元；统一量纲后比值含义为 ebit/mv（比率）
    df['ebit_ratio_val'] = df['ebit'].astype(float) / (df['total_mv'].astype(float) * 1e8)
    df['ebit_ratio'] = -df['ebit_ratio_val']  # 取负，越小表示 EBIT/MV 越高
    return df[['stock_code', 'ebit_ratio']]
