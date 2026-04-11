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
        self.df_daily_basic = None  # PE_TTM等
        self.df_financial = None    # EPS等财务数据
        self.df_daily = None        # 价格数据
        self.is_loaded = False

    def load_data(self, start_date: str, end_date: str):
        """一次性加载所有需要的数据到内存"""
        logger.info(f"开始加载数据: {start_date} ~ {end_date}")

        # 使用原始的 pymysql 连接
        import os
        db_host = os.getenv('ONLINE_DB_HOST', 'localhost')
        db_user = os.getenv('ONLINE_DB_USER', 'root')
        db_pass = os.getenv('ONLINE_DB_PASSWORD', '')
        db_name = os.getenv('ONLINE_DB_NAME', 'trade')

        conn = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_pass,
            database=db_name,
            charset='utf8mb4'
        )

        try:
            # 1. 加载日线基础数据 (PE_TTM)
            sql_basic = f"""
                SELECT stock_code, trade_date, pe_ttm
                FROM trade_stock_daily_basic
                WHERE trade_date BETWEEN %s AND %s
            """
            self.df_daily_basic = pd.read_sql(sql_basic, conn, params=[start_date, end_date])
            # 转换 trade_date 为字符串格式，确保一致性
            self.df_daily_basic['trade_date'] = pd.to_datetime(self.df_daily_basic['trade_date']).dt.strftime('%Y-%m-%d')
            logger.info(f"加载日线基础数据: {len(self.df_daily_basic)} 行")

            # 2. 加载财务数据 (EPS)
            start_year = int(start_date[:4]) - 3
            sql_financial = f"""
                SELECT
                    stock_code,
                    report_date,
                    YEAR(report_date) AS report_year,
                    eps
                FROM trade_stock_financial
                WHERE MONTH(report_date) = 12
                AND YEAR(report_date) >= %s
            """
            self.df_financial = pd.read_sql(sql_financial, conn, params=[start_year])
            logger.info(f"加载财务数据: {len(self.df_financial)} 行")

            # 3. 加载日线价格数据
            sql_daily = f"""
                SELECT stock_code, trade_date, open_price, close_price, high_price, low_price
                FROM trade_stock_daily
                WHERE trade_date BETWEEN %s AND %s
            """
            self.df_daily = pd.read_sql(sql_daily, conn, params=[start_date, end_date])
            # 重命名列以保持兼容性
            self.df_daily = self.df_daily.rename(columns={
                'open_price': 'open',
                'close_price': 'close',
                'high_price': 'high',
                'low_price': 'low'
            })
            # 转换 trade_date 为字符串格式
            self.df_daily['trade_date'] = pd.to_datetime(self.df_daily['trade_date']).dt.strftime('%Y-%m-%d')
            logger.info(f"加载日线价格: {len(self.df_daily)} 行")

            self.is_loaded = True
            logger.info("数据加载完成")

        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            raise
        finally:
            conn.close()


# 全局缓存实例
_cache = FactorDataCache()


def init_cache(start_date: str, end_date: str):
    """初始化数据缓存"""
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
    """计算纯市值因子（缓存版）"""
    if not _cache.is_loaded:
        raise RuntimeError("数据缓存未初始化，请先调用 init_cache()")

    # 使用 close 价作为市值代理
    df_mv = _cache.df_daily[
        (_cache.df_daily['trade_date'] == trade_date) &
        (_cache.df_daily['stock_code'].isin(stock_codes))
    ][['stock_code', 'close']].rename(columns={'close': 'pure_mv'})

    df_mv.loc[df_mv['pure_mv'] <= 0, 'pure_mv'] = np.nan

    return df_mv


def calc_peg_ebit_mv_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算 PEG_EBIT_MV 复合因子（缓存版）- 占位实现"""
    return pd.DataFrame(columns=['stock_code', 'peg_ebit_mv'])


def calc_ebit_ratio_cached(trade_date: str, stock_codes: List[str]) -> pd.DataFrame:
    """计算 EBIT 比率因子（缓存版）- 占位实现"""
    return pd.DataFrame(columns=['stock_code', 'ebit_ratio'])
