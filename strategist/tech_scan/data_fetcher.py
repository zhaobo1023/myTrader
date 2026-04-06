# -*- coding: utf-8 -*-
"""
数据获取器

从 MySQL 数据库获取行情数据和 RPS 数据
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query

logger = logging.getLogger(__name__)


class DataFetcher:
    """数据获取器"""
    
    def __init__(self, env: str = 'online'):
        """
        初始化数据获取器
        
        Args:
            env: 数据库环境 'local' 或 'online'
        """
        self.env = env
        
    def _is_etf(self, code: str) -> bool:
        """判断是否为 ETF 代码"""
        # ETF 代码以 15/51/56/58/59 开头（深市/沪市 ETF）
        code_num = code.split('.')[0]
        return code_num.startswith(('15', '51', '56', '58', '59'))

    def fetch_etf_data(
        self,
        etf_codes: List[str],
        lookback_days: int = 300
    ) -> pd.DataFrame:
        """
        从 trade_etf_daily 获取 ETF 日线数据

        Args:
            etf_codes: ETF 代码列表，如 ['159992.SZ', '159698.SZ']
            lookback_days: 回溯天数（自然日）
        """
        if not etf_codes:
            return pd.DataFrame()

        start_date = (datetime.now() - timedelta(days=int(lookback_days * 1.5))).strftime('%Y-%m-%d')
        placeholders = ','.join(['%s'] * len(etf_codes))

        sql = f"""
            SELECT
                fund_code as stock_code,
                trade_date,
                open_price as `open`,
                high_price as high,
                low_price as low,
                close_price as close,
                volume,
                amount
            FROM trade_etf_daily
            WHERE fund_code IN ({placeholders})
              AND trade_date >= %s
            ORDER BY fund_code, trade_date
        """

        params = tuple(etf_codes) + (start_date,)

        try:
            rows = execute_query(sql, params, env=self.env)
            df = pd.DataFrame(rows)

            if not df.empty:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                for col in ['open', 'high', 'low', 'close', 'amount']:
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                if 'volume' in df.columns:
                    df['volume'] = df['volume'].astype(float)
                # ETF 表没有 turnover_rate，填充 NaN
                if 'turnover_rate' not in df.columns:
                    df['turnover_rate'] = float('nan')

            logger.info(f"获取 ETF 数据: {len(etf_codes)} 只, {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"获取 ETF 数据失败: {e}")
            return pd.DataFrame()

    def fetch_daily_data(
        self,
        stock_codes: List[str],
        lookback_days: int = 300
    ) -> pd.DataFrame:
        """
        获取日线数据（自动区分股票和 ETF，从不同表取数）
        """
        if not stock_codes:
            return pd.DataFrame()

        etf_codes = [c for c in stock_codes if self._is_etf(c)]
        stock_only = [c for c in stock_codes if not self._is_etf(c)]

        dfs = []

        # 股票数据从 trade_stock_daily 取
        if stock_only:
            df_stock = self._fetch_stock_data(stock_only, lookback_days)
            if not df_stock.empty:
                dfs.append(df_stock)

        # ETF 数据从 trade_etf_daily 取
        if etf_codes:
            df_etf = self.fetch_etf_data(etf_codes, lookback_days)
            if not df_etf.empty:
                dfs.append(df_etf)

        if dfs:
            result = pd.concat(dfs, ignore_index=True)
            logger.info(f"获取日线数据: {len(stock_codes)} 只(A股 {len(stock_only)} + ETF {len(etf_codes)}), {len(result)} 条记录")
            return result

        return pd.DataFrame()

    def _fetch_stock_data(
        self,
        stock_codes: List[str],
        lookback_days: int = 300
    ) -> pd.DataFrame:
        """从 trade_stock_daily 获取股票日线数据"""
        start_date = (datetime.now() - timedelta(days=int(lookback_days * 1.5))).strftime('%Y-%m-%d')

        placeholders = ','.join(['%s'] * len(stock_codes))
        sql = f"""
            SELECT
                stock_code,
                trade_date,
                open_price as `open`,
                high_price as high,
                low_price as low,
                close_price as close,
                volume,
                amount,
                turnover_rate
            FROM trade_stock_daily
            WHERE stock_code IN ({placeholders})
              AND trade_date >= %s
            ORDER BY stock_code, trade_date
        """

        params = tuple(stock_codes) + (start_date,)

        try:
            rows = execute_query(sql, params, env=self.env)
            df = pd.DataFrame(rows)

            if not df.empty:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                for col in ['open', 'high', 'low', 'close', 'amount', 'turnover_rate']:
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                if 'volume' in df.columns:
                    df['volume'] = df['volume'].astype(float)

            return df

        except Exception as e:
            logger.error(f"获取股票日线数据失败: {e}")
            raise
    
    def fetch_rps_data(
        self, 
        stock_codes: List[str], 
        lookback_days: int = 30
    ) -> pd.DataFrame:
        """
        获取 RPS 数据
        
        Args:
            stock_codes: 股票代码列表
            lookback_days: 回溯天数
            
        Returns:
            DataFrame with columns: stock_code, trade_date, rps_120, rps_250
        """
        if not stock_codes:
            return pd.DataFrame()
        
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        placeholders = ','.join(['%s'] * len(stock_codes))
        
        # 查询 RPS 表
        possible_tables = ['trade_stock_rps', 'trade_rps_daily', 'stock_rps', 'rps_data']
        
        for table_name in possible_tables:
            try:
                sql = f"""
                    SELECT
                        stock_code,
                        trade_date,
                        rps_120,
                        rps_250,
                        rps_slope
                    FROM {table_name}
                    WHERE stock_code IN ({placeholders})
                      AND trade_date >= %s
                    ORDER BY stock_code, trade_date
                """
                params = tuple(stock_codes) + (start_date,)
                rows = execute_query(sql, params, env=self.env)
                
                if rows:
                    df = pd.DataFrame(rows)
                    df['trade_date'] = pd.to_datetime(df['trade_date'])
                    for col in ['rps_120', 'rps_250', 'rps_slope']:
                        if col in df.columns:
                            df[col] = df[col].astype(float)
                    logger.info(f"从 {table_name} 获取 RPS 数据: {len(df)} 条记录")
                    return df
                    
            except Exception as e:
                logger.debug(f"尝试表 {table_name} 失败: {e}")
                continue
        
        logger.warning("未找到 RPS 数据表，将实时计算 RPS")
        return pd.DataFrame()
    
    def fetch_stock_names(self, stock_codes: List[str]) -> Dict[str, str]:
        """
        获取股票名称映射
        
        Args:
            stock_codes: 股票代码列表
            
        Returns:
            {stock_code: stock_name} 映射
        """
        if not stock_codes:
            return {}
        
        placeholders = ','.join(['%s'] * len(stock_codes))
        
        # 尝试从不同表获取名称
        possible_queries = [
            f"SELECT stock_code, stock_name FROM trade_stock_basic WHERE stock_code IN ({placeholders})",
            f"SELECT stock_code, stock_name FROM trade_stock_info WHERE stock_code IN ({placeholders})",
            f"SELECT stock_code, name as stock_name FROM stock_basic WHERE stock_code IN ({placeholders})",
            f"SELECT stock_code, stock_name FROM trade_stock_daily WHERE stock_code IN ({placeholders}) AND stock_name IS NOT NULL GROUP BY stock_code ORDER BY trade_date DESC",
        ]
        
        for sql in possible_queries:
            try:
                rows = execute_query(sql, tuple(stock_codes), env=self.env)
                if rows:
                    return {r['stock_code']: r['stock_name'] for r in rows}
            except Exception:
                continue
        
        logger.warning("未找到股票名称表")
        return {}
    
    def check_data_availability(self, stock_codes: List[str]) -> Dict[str, Any]:
        """
        检查数据可用性（同时查 trade_stock_daily 和 trade_etf_daily）
        """
        if not stock_codes:
            return {'available': [], 'missing': [], 'latest_date': None}

        etf_codes = [c for c in stock_codes if self._is_etf(c)]
        stock_only = [c for c in stock_codes if not self._is_etf(c)]

        available = {}
        all_dates = []

        # 查股票表
        if stock_only:
            placeholders = ','.join(['%s'] * len(stock_only))
            sql = f"""
                SELECT stock_code, MAX(trade_date) as latest_date
                FROM trade_stock_daily
                WHERE stock_code IN ({placeholders})
                GROUP BY stock_code
            """
            try:
                rows = execute_query(sql, tuple(stock_only), env=self.env)
                for r in rows:
                    available[r['stock_code']] = r['latest_date']
                    all_dates.append(r['latest_date'])
            except Exception as e:
                logger.error(f"检查股票数据可用性失败: {e}")

        # 查 ETF 表
        if etf_codes:
            placeholders = ','.join(['%s'] * len(etf_codes))
            sql = f"""
                SELECT fund_code, MAX(trade_date) as latest_date
                FROM trade_etf_daily
                WHERE fund_code IN ({placeholders})
                GROUP BY fund_code
            """
            try:
                rows = execute_query(sql, tuple(etf_codes), env=self.env)
                for r in rows:
                    available[r['fund_code']] = r['latest_date']
                    all_dates.append(r['latest_date'])
            except Exception as e:
                logger.error(f"检查 ETF 数据可用性失败: {e}")

        missing = [c for c in stock_codes if c not in available]
        latest_date = max(all_dates) if all_dates else None

        return {
            'available': list(available.keys()),
            'missing': missing,
            'latest_date': latest_date,
            'details': available
        }


def fetch_market_data(stock_codes: List[str], env: str = 'online') -> pd.DataFrame:
    """便捷函数：获取行情数据"""
    fetcher = DataFetcher(env=env)
    return fetcher.fetch_daily_data(stock_codes)
