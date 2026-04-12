# -*- coding: utf-8 -*-
"""
因子计算模块 - 数据缓存优化版

在回测开始前预加载所有数据到内存，避免每个交易日重复查询数据库。
"""
import logging
from typing import List, Dict
from datetime import datetime

import pandas as pd
import numpy as np
import pymysql

from config.db import get_connection

logger = logging.getLogger(__name__)


class FactorDataCache:
    """因子数据缓存类"""

    def __init__(self):
        self.df_daily_basic = None  # PE_TTM + total_mv
        self.df_financial = None    # EPS等财务数据
        self.df_daily = None        # 价格数据 + amount
        self.df_st = None           # ST标志
        self.df_risk = None         # 财务风险数据（净利润/负债率/现金流）
        self.is_loaded = False

    def _query_with_new_conn(self, sql: str, params: list) -> pd.DataFrame:
        """每次查询新建连接，避免长时间连接被服务器主动断开。"""
        conn = get_connection()
        try:
            return pd.read_sql(sql, conn, params=params)
        finally:
            conn.close()

    def load_data(self, start_date: str, end_date: str):
        """分批加载所有需要的数据到内存（每批次独立连接，避免连接超时）"""
        from datetime import datetime as _dt, timedelta as _td

        logger.info(f"开始加载数据: {start_date} ~ {end_date}")
        _end = _dt.strptime(end_date, '%Y-%m-%d')

        def iter_quarters(s: str):
            """生成 (batch_start, batch_end) 季度区间列表"""
            cur = _dt.strptime(s, '%Y-%m-%d')
            while cur <= _end:
                m = cur.month - 1 + 3
                y = cur.year + m // 12
                m = m % 12 + 1
                be = _dt(y, m, 1) - _td(days=1)
                if be > _end:
                    be = _end
                yield cur.strftime('%Y-%m-%d'), be.strftime('%Y-%m-%d')
                cur = be + _td(days=1)

        try:
            # 1. 加载日线基础数据 (PE_TTM + total_mv)，按季度分批，每批独立连接
            basic_chunks = []
            for bs, bes in iter_quarters(start_date):
                sql = """
                    SELECT stock_code, trade_date, pe_ttm, total_mv
                    FROM trade_stock_daily_basic
                    WHERE trade_date BETWEEN %s AND %s
                """
                chunk = self._query_with_new_conn(sql, [bs, bes])
                basic_chunks.append(chunk)
                logger.info(f"加载日线基础数据批次 {bs}~{bes}: {len(chunk)} 行")
            self.df_daily_basic = pd.concat(basic_chunks, ignore_index=True) if basic_chunks else pd.DataFrame()
            self.df_daily_basic['trade_date'] = pd.to_datetime(
                self.df_daily_basic['trade_date']).dt.strftime('%Y-%m-%d')
            logger.info(f"加载日线基础数据合计: {len(self.df_daily_basic)} 行")

            # 2. 加载财务数据 (EPS)，单独连接（数据量小，无需分批）
            start_year = int(start_date[:4]) - 3
            sql_financial = """
                SELECT
                    stock_code,
                    report_date,
                    YEAR(report_date) AS report_year,
                    eps
                FROM trade_stock_financial
                WHERE MONTH(report_date) = 12
                AND YEAR(report_date) >= %s
            """
            self.df_financial = self._query_with_new_conn(sql_financial, [start_year])
            logger.info(f"加载财务数据: {len(self.df_financial)} 行")

            # 3. 加载日线价格数据（含 amount 用于流动性过滤），按季度分批，每批独立连接
            chunks = []
            for bs, bes in iter_quarters(start_date):
                sql = """
                    SELECT stock_code, trade_date, open_price, close_price,
                           high_price, low_price, amount
                    FROM trade_stock_daily
                    WHERE trade_date BETWEEN %s AND %s
                """
                chunk = self._query_with_new_conn(sql, [bs, bes])
                chunks.append(chunk)
                logger.info(f"加载日线价格批次 {bs}~{bes}: {len(chunk)} 行")
            self.df_daily = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            self.df_daily = self.df_daily.rename(columns={
                'open_price': 'open',
                'close_price': 'close',
                'high_price': 'high',
                'low_price': 'low'
            })
            self.df_daily['trade_date'] = pd.to_datetime(
                self.df_daily['trade_date']).dt.strftime('%Y-%m-%d')
            logger.info(f"加载日线价格合计: {len(self.df_daily)} 行")

            # 4. 加载 ST 标志（静态数据，无需按日期分批）
            sql_st = "SELECT stock_code, is_st FROM trade_stock_basic"
            self.df_st = self._query_with_new_conn(sql_st, [])
            logger.info(f"加载 ST 标志: {len(self.df_st)} 行")

            # 5. 加载财务风险数据（净利润/负债率/经营现金流），多年年报
            sql_risk = """
                SELECT stock_code, report_date,
                       YEAR(report_date) AS report_year,
                       net_profit, debt_ratio, operating_cashflow
                FROM trade_stock_financial
                WHERE MONTH(report_date) = 12
                AND YEAR(report_date) >= %s
            """
            self.df_risk = self._query_with_new_conn(sql_risk, [int(start_date[:4]) - 3])
            logger.info(f"加载财务风险数据: {len(self.df_risk)} 行")

            self.is_loaded = True
            logger.info("数据加载完成")

        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            raise


# 全局缓存实例
_cache = FactorDataCache()


def init_cache(start_date: str, end_date: str):
    """初始化数据缓存（已加载则跳过重复查询）"""
    if _cache.is_loaded:
        logger.info("数据缓存已就绪，跳过重复加载")
        return
    _cache.load_data(start_date, end_date)


def calc_peg_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """
    计算 PEG 因子（缓存版）

    PEG = PE_TTM / (EPS增速 * 100)
    """
    if not _cache.is_loaded:
        raise RuntimeError("数据缓存未初始化，请先调用 init_cache()")

    if not stock_codes:
        return pd.DataFrame(columns=['stock_code', 'peg'])

    # Step 1: 从缓存获取 PE_TTM
    df_pe = _cache.df_daily_basic[
        (_cache.df_daily_basic['trade_date'] == trade_date) &
        (_cache.df_daily_basic['stock_code'].isin(stock_codes))
    ][['stock_code', 'pe_ttm']]

    if df_pe.empty:
        return pd.DataFrame(columns=['stock_code', 'peg'])

    # Step 2: 计算 EPS 增速
    trade_year = int(trade_date[:4])
    trade_month = int(trade_date[5:7])
    if trade_month <= 4:
        max_report_year = trade_year - 1
    else:
        max_report_year = trade_year

    # 从缓存获取财务数据
    df_eps = _cache.df_financial[
        (_cache.df_financial['stock_code'].isin(stock_codes)) &
        (_cache.df_financial['report_year'] <= max_report_year)
    ].copy()

    result = df_pe.set_index('stock_code')[['pe_ttm']].copy()

    if not df_eps.empty:
        eps_growth_list = []
        for stock_code in df_eps['stock_code'].unique():
            stock_eps = df_eps[df_eps['stock_code'] == stock_code].sort_values('report_year')
            if len(stock_eps) >= 2:
                eps_latest = stock_eps.iloc[-1]['eps']
                eps_prev = stock_eps.iloc[-2]['eps']
                if eps_prev and eps_prev != 0 and pd.notna(eps_prev) and pd.notna(eps_latest):
                    eps_growth = (eps_latest - eps_prev) / abs(eps_prev)
                    eps_growth_list.append({'stock_code': stock_code, 'eps_growth': eps_growth})

        if eps_growth_list:
            df_growth = pd.DataFrame(eps_growth_list).set_index('stock_code')
            result = result.join(df_growth, how='left')

            # 计算 PEG
            result['peg'] = result['pe_ttm'] / (result['eps_growth'] * 100)
        else:
            result['peg'] = result['pe_ttm']
    else:
        result['peg'] = result['pe_ttm']

    # 过滤异常值
    result.loc[(result['peg'] <= 0) | (result['peg'] >= 1000), 'peg'] = np.nan

    return result.reset_index()


def calc_pe_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算 PE 因子（缓存版）"""
    if not _cache.is_loaded:
        raise RuntimeError("数据缓存未初始化，请先调用 init_cache()")

    df_pe = _cache.df_daily_basic[
        (_cache.df_daily_basic['trade_date'] == trade_date) &
        (_cache.df_daily_basic['stock_code'].isin(stock_codes))
    ][['stock_code', 'pe_ttm']].rename(columns={'pe_ttm': 'pe'})

    df_pe.loc[df_pe['pe'] <= 0, 'pe'] = np.nan
    df_pe.loc[df_pe['pe'] > 1000, 'pe'] = np.nan

    return df_pe


def calc_roe_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算 ROE 因子（缓存版）- 这里使用占位实现"""
    # ROE 需要从财务数据获取，这里先返回空DataFrame
    # 实际实现需要加载净资产和净利润数据
    return pd.DataFrame(columns=['stock_code', 'roe'])


def calc_pure_mv_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算纯市值因子（缓存版）- 使用 total_mv"""
    if not _cache.is_loaded:
        raise RuntimeError("数据缓存未初始化，请先调用 init_cache()")

    df_mv = _cache.df_daily_basic[
        (_cache.df_daily_basic['trade_date'] == trade_date) &
        (_cache.df_daily_basic['stock_code'].isin(stock_codes))
    ][['stock_code', 'total_mv']].rename(columns={'total_mv': 'pure_mv'})

    df_mv = df_mv.copy()
    df_mv.loc[df_mv['pure_mv'] <= 0, 'pure_mv'] = np.nan

    return df_mv


def calc_pure_mv_mom_cached(trade_date: str, stock_codes: List[str],
                            lookback: int = 20, weight: float = 0.3) -> pd.DataFrame:
    """计算动量反转因子（缓存版）- total_mv + reversal"""
    if not _cache.is_loaded:
        raise RuntimeError("数据缓存未初始化，请先调用 init_cache()")

    # 获取当日 total_mv
    df_mv = _cache.df_daily_basic[
        (_cache.df_daily_basic['trade_date'] == trade_date) &
        (_cache.df_daily_basic['stock_code'].isin(stock_codes))
    ][['stock_code', 'total_mv']].copy()

    if df_mv.empty:
        return pd.DataFrame(columns=['stock_code', 'pure_mv_mom'])

    df_mv.loc[df_mv['total_mv'] <= 0, 'total_mv'] = np.nan

    # 计算反转因子：过去 lookback 天的累积收益（越低越好，用于反转）
    df_price = _cache.df_daily[
        _cache.df_daily['stock_code'].isin(stock_codes)
    ][['stock_code', 'trade_date', 'close']].copy()

    df_price_sorted = df_price.sort_values(['stock_code', 'trade_date'])
    all_dates = sorted(_cache.df_daily['trade_date'].unique())
    try:
        date_idx = all_dates.index(trade_date)
    except ValueError:
        # 当日无数据，仅用市值排序
        df_mv['pure_mv_mom'] = df_mv['total_mv'].astype(float)
        return df_mv[['stock_code', 'pure_mv_mom']].dropna()

    lookback_start_idx = max(0, date_idx - lookback)
    lookback_dates = set(all_dates[lookback_start_idx:date_idx + 1])

    df_window = df_price_sorted[df_price_sorted['trade_date'].isin(lookback_dates)]
    reversal_list = []
    for code, grp in df_window.groupby('stock_code'):
        grp = grp.sort_values('trade_date')
        if len(grp) >= 2:
            ret = float(grp.iloc[-1]['close']) / float(grp.iloc[0]['close']) - 1
            reversal_list.append({'stock_code': code, 'reversal': ret})

    if not reversal_list:
        df_mv['pure_mv_mom'] = df_mv['total_mv'].astype(float)
        return df_mv[['stock_code', 'pure_mv_mom']].dropna()

    df_rev = pd.DataFrame(reversal_list)
    df_merged = df_mv.merge(df_rev, on='stock_code', how='left')

    # 排名：mv_rank 升序（小市值优先），reversal_rank 升序（跌最多优先 = 反转）
    df_merged['mv_rank'] = df_merged['total_mv'].rank(ascending=True, pct=True)
    df_merged['reversal_rank'] = df_merged['reversal'].rank(ascending=True, pct=True)
    df_merged['pure_mv_mom'] = (
        df_merged['mv_rank'] * (1 - weight) + df_merged['reversal_rank'] * weight
    )

    return df_merged[['stock_code', 'pure_mv_mom']].dropna(subset=['pure_mv_mom'])


def calc_peg_ebit_mv_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算 PEG_EBIT_MV 复合因子（缓存版）- 占位实现"""
    return pd.DataFrame(columns=['stock_code', 'peg_ebit_mv'])


def calc_ebit_ratio_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算 EBIT 比率因子（缓存版）- 占位实现"""
    return pd.DataFrame(columns=['stock_code', 'ebit_ratio'])


def get_universe_cached(trade_date: str,
                        percentile: float = 0.20,
                        exclude_st: bool = True,
                        require_positive_pe: bool = True,
                        min_avg_turnover: float = 0.0,
                        exclude_risk: bool = False,
                        max_debt_ratio: float = 0.70,
                        require_positive_profit: bool = True,
                        require_positive_cashflow: bool = True) -> List[str]:
    """
    基于内存缓存构建当日 Universe，完全跳过 DB 查询。

    流程：
    1. 从 df_daily_basic 取当日所有股票的 total_mv / pe_ttm
    2. 排除 ST（df_st）
    3. 流动性过滤（df_daily 近5日 amount 均值）
    4. 财务风险过滤（df_risk）
    5. 按市值 percentile 截断
    """
    if not _cache.is_loaded:
        raise RuntimeError("数据缓存未初始化，请先调用 init_cache()")

    # Step 1: 当日市值数据
    df = _cache.df_daily_basic[
        _cache.df_daily_basic['trade_date'] == trade_date
    ][['stock_code', 'total_mv', 'pe_ttm']].copy()

    if df.empty:
        return []

    df = df[df['total_mv'] > 0]

    if require_positive_pe:
        df = df[df['pe_ttm'] > 0]

    # Step 2: 排除 ST
    if exclude_st and _cache.df_st is not None and not _cache.df_st.empty:
        non_st = set(_cache.df_st[_cache.df_st['is_st'] == 0]['stock_code'])
        df = df[df['stock_code'].isin(non_st)]

    if df.empty:
        return []

    # Step 3: 流动性过滤（近5个交易日均值）
    if min_avg_turnover > 0 and _cache.df_daily is not None and 'amount' in _cache.df_daily.columns:
        all_dates = sorted(_cache.df_daily['trade_date'].unique())
        try:
            date_idx = all_dates.index(trade_date)
        except ValueError:
            date_idx = -1
        if date_idx >= 0:
            window_dates = set(all_dates[max(0, date_idx - 9): date_idx + 1])
            df_amt = _cache.df_daily[
                _cache.df_daily['trade_date'].isin(window_dates) &
                _cache.df_daily['stock_code'].isin(df['stock_code'])
            ].groupby('stock_code')['amount'].agg(['mean', 'count']).reset_index()
            df_amt.columns = ['stock_code', 'avg_amount', 'cnt']
            df_amt = df_amt[(df_amt['cnt'] >= 3) & (df_amt['avg_amount'] >= min_avg_turnover)]
            liquid_codes = set(df_amt['stock_code'])
            df = df[df['stock_code'].isin(liquid_codes)]

    if df.empty:
        return []

    # Step 4: 财务风险过滤
    if exclude_risk and _cache.df_risk is not None and not _cache.df_risk.empty:
        trade_year = int(trade_date[:4])
        trade_month = int(trade_date[5:7])
        report_year = trade_year - 1 if trade_month <= 4 else trade_year
        df_fin = _cache.df_risk[_cache.df_risk['report_year'] <= report_year]
        # 取每只股票最新年报
        df_fin_latest = df_fin.sort_values('report_year').groupby('stock_code').last().reset_index()
        exclude_codes = set()
        if require_positive_profit:
            exclude_codes |= set(df_fin_latest[df_fin_latest['net_profit'] <= 0]['stock_code'])
        if max_debt_ratio < 1.0:
            exclude_codes |= set(df_fin_latest[df_fin_latest['debt_ratio'] > max_debt_ratio * 100]['stock_code'])
        if require_positive_cashflow:
            neg_cf = df_fin_latest[
                df_fin_latest['operating_cashflow'].notna() &
                (df_fin_latest['operating_cashflow'] <= 0)
            ]
            exclude_codes |= set(neg_cf['stock_code'])
        df = df[~df['stock_code'].isin(exclude_codes)]

    if df.empty:
        return []

    # Step 5: 市值百分位截断
    if percentile < 1.0:
        threshold = df['total_mv'].quantile(percentile)
        df = df[df['total_mv'] <= threshold]

    return df['stock_code'].tolist()
