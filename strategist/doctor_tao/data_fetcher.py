# -*- coding: utf-8 -*-
"""
陶博士策略 - 数据拉取模块

提供数据基础建设功能：
1. fetch_all_stocks() - 拉取全A股代码列表
2. fetch_daily_price() - 拉取单股日线行情
3. fetch_filter_table() - 基本面过滤表（ST标记、上市日期、成交额、净利润）
"""
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, get_connection
from dotenv import load_dotenv

load_dotenv()


class DoctorTaoDataFetcher:
    """陶博士策略数据拉取器"""

    def __init__(self, use_cache: bool = True, cache_dir: str = None):
        """
        初始化数据拉取器

        Args:
            use_cache: 是否使用本地 parquet 缓存
            cache_dir: 缓存目录，默认为 data/cache/doctor_tao
        """
        self.use_cache = use_cache
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(__file__).parent.parent.parent / 'data' / 'cache' / 'doctor_tao'

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_all_stocks(self) -> List[str]:
        """
        拉取全A股代码列表（从 trade_stock_daily 表获取有数据的股票）

        Returns:
            股票代码列表，如 ['000001.SZ', '600519.SH', ...]
        """
        cache_file = self.cache_dir / 'all_stocks.parquet'

        # 尝试从缓存加载
        if self.use_cache and cache_file.exists():
            cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            # 缓存有效期：1天
            if datetime.now() - cache_time < timedelta(days=1):
                df = pd.read_parquet(cache_file)
                return df['stock_code'].tolist()

        # 从数据库查询
        sql = """
            SELECT DISTINCT stock_code
            FROM trade_stock_daily
            WHERE stock_code REGEXP '^[0-9]{6}\\.(SH|SZ)$'
            ORDER BY stock_code
        """
        result = execute_query(sql, env='online')
        stock_list = [row['stock_code'] for row in result]

        # 保存到缓存
        if self.use_cache:
            pd.DataFrame({'stock_code': stock_list}).to_parquet(cache_file, index=False)

        print(f"fetch_all_stocks: 获取到 {len(stock_list)} 只股票")
        return stock_list

    def fetch_daily_price(
        self,
        stock_code: str,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """
        拉取单股日线行情

        Args:
            stock_code: 股票代码，如 '600519.SH'
            start_date: 开始日期，如 '2024-01-01'，默认为 2023-01-01
            end_date: 结束日期，如 '2024-12-31'，默认为最新

        Returns:
            DataFrame，包含 open/close/high/low/volume/amount/turnover_rate
        """
        if start_date is None:
            start_date = '2023-01-01'
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # 检查缓存
        cache_file = self.cache_dir / f'price_{stock_code.replace(".", "_")}.parquet'
        if self.use_cache and cache_file.exists():
            cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            # 缓存有效期：到当天 18:00 之前有效（数据通常在 18:00 更新）
            if cache_time.date() == datetime.now().date() and datetime.now().hour < 18:
                df = pd.read_parquet(cache_file)
                df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
                return df

        # 从数据库查询
        sql = """
            SELECT
                trade_date,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                volume,
                amount,
                turnover_rate
            FROM trade_stock_daily
            WHERE stock_code = %s
            AND trade_date >= %s
            AND trade_date <= %s
            ORDER BY trade_date
        """
        result = execute_query(sql, (stock_code, start_date, end_date), env='online')

        if not result:
            return pd.DataFrame()

        df = pd.DataFrame(result)
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        # 保存到缓存
        if self.use_cache and len(df) > 0:
            df.to_parquet(cache_file, index=False)

        return df

    def fetch_daily_price_batch(
        self,
        stock_codes: List[str],
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, pd.DataFrame]:
        """
        批量拉取多只股票的日线行情

        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            字典 {stock_code: DataFrame}
        """
        if start_date is None:
            start_date = '2023-01-01'
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # 使用单个 SQL 查询提升效率
        placeholders = ','.join(['%s'] * len(stock_codes))
        sql = f"""
            SELECT
                stock_code,
                trade_date,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                volume,
                amount,
                turnover_rate
            FROM trade_stock_daily
            WHERE stock_code IN ({placeholders})
            AND trade_date >= %s
            AND trade_date <= %s
            ORDER BY stock_code, trade_date
        """
        params = tuple(stock_codes) + (start_date, end_date)
        result = execute_query(sql, params, env='online')

        if not result:
            return {}

        # 转换为字典
        df = pd.DataFrame(result)
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        result_dict = {}
        for code in stock_codes:
            code_df = df[df['stock_code'] == code].copy()
            if len(code_df) > 0:
                code_df = code_df.drop(columns=['stock_code'])
                result_dict[code] = code_df

        return result_dict

    def fetch_filter_table(self) -> pd.DataFrame:
        """
        拉取基本面过滤表

        包含：
        - stock_code: 股票代码
        - is_st: 是否ST股票（根据股票名称判断）
        - list_date: 上市日期（从 trade_stock_daily 最早日期推断）
        - avg_amount_60d: 近60日均成交额（万元）
        - latest_net_profit: 最新净利润（亿元）
        - latest_roe: 最新ROE

        Returns:
            DataFrame
        """
        cache_file = self.cache_dir / 'filter_table.parquet'

        # 尝试从缓存加载（有效期1天）
        if self.use_cache and cache_file.exists():
            cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - cache_time < timedelta(days=1):
                df = pd.read_parquet(cache_file)
                print(f"fetch_filter_table: 从缓存加载 {len(df)} 只股票")
                return df

        print("fetch_filter_table: 正在构建基本面过滤表...")

        # 1. 获取所有股票代码和最早交易日期（上市日期推断）
        sql_list_date = """
            SELECT
                stock_code,
                MIN(trade_date) as list_date
            FROM trade_stock_daily
            WHERE stock_code REGEXP '^[0-9]{6}\\.(SH|SZ)$'
            GROUP BY stock_code
        """
        list_date_data = execute_query(sql_list_date, env='online')
        df_list_date = pd.DataFrame(list_date_data)

        # 2. 计算近60日均成交额
        sql_amount = """
            SELECT
                stock_code,
                AVG(amount) / 10000 as avg_amount_60d
            FROM trade_stock_daily
            WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL 60 DAY)
            GROUP BY stock_code
        """
        amount_data = execute_query(sql_amount, env='online')
        df_amount = pd.DataFrame(amount_data)

        # 3. 获取最新财务数据（净利润、ROE）
        sql_financial = """
            SELECT
                t1.stock_code,
                t1.net_profit / 100000000 as latest_net_profit,
                t1.roe as latest_roe,
                t1.report_date
            FROM trade_stock_financial t1
            INNER JOIN (
                SELECT stock_code, MAX(report_date) as max_date
                FROM trade_stock_financial
                GROUP BY stock_code
            ) t2 ON t1.stock_code = t2.stock_code AND t1.report_date = t2.max_date
        """
        financial_data = execute_query(sql_financial, env='online')
        df_financial = pd.DataFrame(financial_data)

        # 4. 判断ST股票（根据股票名称判断）
        sql_st = """
            SELECT DISTINCT stock_code, stock_name
            FROM trade_stock_daily_basic
            WHERE stock_name LIKE '%ST%' OR stock_name LIKE '%*ST%'
        """
        try:
            st_data = execute_query(sql_st, env='online')
            st_codes = set([row['stock_code'] for row in st_data]) if st_data else set()
            df_list_date['is_st'] = df_list_date['stock_code'].isin(st_codes)
            print(f"  ST股票数: {len(st_codes)}")
        except Exception as e:
            print(f"  ST股票查询失败: {e}，默认标记为非ST")
            df_list_date['is_st'] = False

        # 5. 合并数据
        df = df_list_date.merge(df_amount, on='stock_code', how='left')
        df = df.merge(df_financial[['stock_code', 'latest_net_profit', 'latest_roe']], on='stock_code', how='left')

        # 保存到缓存
        if self.use_cache:
            df.to_parquet(cache_file, index=False)

        print(f"fetch_filter_table: 完成，共 {len(df)} 只股票")
        return df

    def clear_cache(self):
        """清空缓存"""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            print("缓存已清空")


# 便捷函数
_fetcher = None

def get_fetcher(use_cache: bool = True) -> DoctorTaoDataFetcher:
    """获取全局数据拉取器实例"""
    global _fetcher
    if _fetcher is None:
        _fetcher = DoctorTaoDataFetcher(use_cache=use_cache)
    return _fetcher


def fetch_all_stocks() -> List[str]:
    """拉取全A股代码列表"""
    return get_fetcher().fetch_all_stocks()


def fetch_daily_price(stock_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """拉取单股日线行情"""
    return get_fetcher().fetch_daily_price(stock_code, start_date, end_date)


def fetch_filter_table() -> pd.DataFrame:
    """拉取基本面过滤表"""
    return get_fetcher().fetch_filter_table()


if __name__ == '__main__':
    # 测试
    fetcher = DoctorTaoDataFetcher(use_cache=True)

    # 测试 fetch_all_stocks
    print("\n1. 测试 fetch_all_stocks():")
    stocks = fetcher.fetch_all_stocks()
    print(f"   前10只: {stocks[:10]}")

    # 测试 fetch_daily_price
    print("\n2. 测试 fetch_daily_price():")
    df = fetcher.fetch_daily_price('600519.SH', '2024-01-01', '2024-12-31')
    print(f"   600519.SH 数据行数: {len(df)}")
    if len(df) > 0:
        print(f"   最新数据: {df.iloc[-1].to_dict()}")

    # 测试 fetch_filter_table
    print("\n3. 测试 fetch_filter_table():")
    df_filter = fetcher.fetch_filter_table()
    print(f"   总行数: {len(df_filter)}")
    print(f"   列名: {df_filter.columns.tolist()}")
    print(f"   样例:\n{df_filter.head()}")
