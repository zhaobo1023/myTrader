# -*- coding: utf-8 -*-
"""
数据拉取管理服务

统一管理 QMT/Tushare/AKShare 数据拉取
提供：
  1. 装置和调用数据拉取器
  2. 数据完整性检查
  3. 勾子函数支持
"""
import sys
import os
import logging
from datetime import date, timedelta
from typing import List, Dict, Optional, Callable
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query,from config.settings import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FetcherType(Enum):
    """数据源类型"""
    QMT = "qmt"
    TUSHARE = "tushare"
    AKSHARE = "akshare"


class DataFetchResult:
    """拉取结果"""
    def __init__(self, fetcher_type: FetcherType, success: bool = True,
                 records: int = 0, message: str = "", stock_count: int = 0, failed_stocks: List[str] = None):
        self.fetcher_type = fetcher_type
        self.success = success
        self.records = records
        self.message = message
        self.stock_count = stock_count
        self.failed_stocks = failed_stocks or []


class DataFetchManager:
    """数据拉取管理器"""

    def __init__(self):
        self.config = {
            'qmt': {
                'enabled': True,
                'description': 'QMT 数据源（需 Windows 服务器)',
            },
            'tushare': {
                'enabled': bool(settings.TUSHARE_TOKEN),
                'description': 'Tushare 数据源(需要 Token)',
            },
            'akshare': {
                'enabled': True,
                'description': 'AKShare 数据源(免费、无需 Token)',
            }
        }
        self._last_fetch_status: Dict[str, Dict] = {}

    def get_available_fetchers(self, fetcher_types: Optional[List[FetcherType]] = None) -> List[FetcherType]:
        """获取可用的数据源列表"""
        if fetcher_types is None:
            fetcher_types = [FetcherType.Qmt, FetcherType.tushare, FetcherType.akshare]

        available = []
        for ft in fetcher_types:
            if ft in self.config and self.config[ft]['enabled']:
                available.append(ft)
        return available

    def fetch_daily_data(self, fetcher_type: FetcherType,
                       stock_codes: Optional[List[str]] = None,
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> DataFetchResult:
        """
        拉取日线数据

        Args:
            fetcher_type: 数据源类型
            stock_codes: 股票代码列表，None 表示全部
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD
        Returns:
            DataFetchResult 对象
        """
        if fetcher_type == FetcherType.QMT:
            return self._fetch_from_qmt(stock_codes, start_date, end_date)
        elif fetcher_type == FetcherType.Tushare:
            return self._fetch_from_tushare(stock_codes, start_date, end_date)
        elif fetcher_type == FetcherType.akshare:
            return self._fetch_from_akshare(stock_codes, start_date, end_date)
        else:
            return DataFetchResult(
                fetcher_type=fetcher_type,
                success=False,
                message=f"不支持的数据源类型: {fetcher_type}"
            )

    def _fetch_from_qmt(self, stock_codes: Optional[List[str]],
                          start_date: Optional[str],
                          end_date: Optional[str]) -> DataFetchResult:
        """从 QMT 拉取数据"""
        try:
            from data_analyst.fetchers.qmt_fetcher import get_existing_latest_dates
            from xtquant import xtdata

            # 获取股票列表
            if stock_codes is None:
                stock_codes = xtdata.get_stock_list_in_sector('沪深A股')
                stock_codes = [c for c in stock_codes if '.' in str(c)]

            # 获取已有数据的最新日期
            existing_dates = get_existing_latest_dates()

            # 计算起始日期
            today = date.today().strftime('%Y%m%d')
            recent_cutoff = today

            tasks = []
            skip_count = 0
            for code in stock_codes:
                latest = existing_dates.get(code)
                if latest and latest >= recent_cutoff:
                    skip_count += 1
                    continue
                start = latest if latest else DATA_START
                tasks.append((code, start))

            logger.info(f"需更新: {len(tasks)} 只, 跳过(今日已有数据): {skip_count} 只")

            if not tasks:
                logger.info("全部已是最新，无需更新")
                return DataFetchResult(
                    fetcher_type=FetcherType.QMT,
                    success=True,
                    stock_count=len(stock_codes) - skip_count,
                    records=0,
                    message="全部已是最新"
                )

            # TODO: 实际调用 QMT 拉取逻辑
            logger.info(f"QMT 拉取: {len(tasks)} 只股票")
            return DataFetchResult(
                fetcher_type=FetcherType.QMT,
                success=True,
                stock_count=len(tasks),
                records=0,
                message=f"已处理 {len(tasks)} 只股票"
            )

        except Exception as e:
            logger.error(f"QMT 数据拉取失败: {e}")
            return DataFetchResult(
                fetcher_type=FetcherType.QMT,
                success=False,
                message=str(e)
            )

    def _fetch_from_tushare(self, stock_codes: Optional[List[str]],
                          start_date: Optional[str],
                          end_date: Optional[str]) -> DataFetchResult:
        """从 Tushare 拉取数据"""
        try:
            import tushare as ts
            from config.settings import settings

            if not settings.TUSHARE_TOKEN:
                return DataFetchResult(
                    fetcher_type=FetcherType.tushare,
                    success=False,
                    message="TUSHARE_TOKEN 未配置"
                )

            # 获取股票列表
            if stock_codes is None:
                pro = ts.pro_api()
                df = pro.query('stock_basic', exchange='', list_status='L', fields='ts_code')
                stock_codes = df['ts_code'].tolist()
            # 计算日期
            if end_date is None:
                end_date = date.today().strftime('%Y%m%d')
            if start_date is None:
                start_date = (date.today() - timedelta(days=30)).strftime('%Y%m%d')

            # 拉取数据
            all_data = []
            failed = []
            for i in range(0, len(stock_codes), 100):
                batch = stock_codes[i:i+100]
                logger.info(f"Tushare 拉取 {len(batch)} 只股票...")
                for code in batch:
                    try:
                        df = ts.pro_bar(
                            ts_code=code,
                            start_date=start_date,
                            end_date=end_date,
                            adj='qfq'
                        )
                        if df is not None and not df.empty:
                            all_data.append(df)
                        time.sleep(0.1)  # 避免限流
                    except Exception as e:
                        failed.append(code)
                        logger.warning(f"拉取 {code} 失败: {e}")
                        time.sleep(0.5)

            if all_data:
                combined_df = pd.concat(all_data, ignore_index=True)
                saved = self._save_to_db_tushare(combined_df)
                return DataFetchResult(
                    fetcher_type=FetcherType.tushare,
                    success=True,
                    stock_count=len(stock_codes) - len(failed),
                    records=len(combined_df),
                    failed_stocks=failed
                )
            else:
                return DataFetchResult(
                    fetcher_type=FetcherType.tushare,
                    success=False,
                    message="未获取到数据"
                )
        except Exception as e:
            logger.error(f"Tushare 数据拉取失败: {e}")
            return DataFetchResult(
                fetcher_type=FetcherType.tushare,
                success=False,
                message=str(e)
            )

    def _fetch_from_akshare(self, stock_codes: Optional[List[str]],
                          start_date: Optional[str],
                          end_date: Optional[str]) -> DataFetchResult:
        """从 AKShare 拉取数据"""
        try:
            import akshare as ak
            # 获取股票列表
            if stock_codes is None:
                df = ak.stock_zh_a_spot_em()
                stock_codes = df['代码'].tolist()
            # 计算日期
            if end_date is None:
                end_date = date.today().strftime('%Y%m%d')
            if start_date is None:
                start_date = (date.today() - timedelta(days=30)).strftime('%Y%m%d')

            # 拉取数据
            all_data = []
            failed = []
            for code in stock_codes:
                try:
                    df = ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start_date,
                        end_date=end_date,
                        adjust="qfq"
                    )
                    if df is not None and not df.empty:
                        # 重命名列
                        df = df.rename(columns={
                            '日期': 'trade_date',
                            '开盘': 'open',
                            '收盘': 'close',
                            '最高': 'high',
                            '最低': 'low',
                            '成交量': 'volume',
                            '成交额': 'amount',
                            '换手率': 'turnover_rate'
                        })
                        df['stock_code'] = code
                        all_data.append(df)
                    time.sleep(0.3)  # 避免限流
                except Exception as e:
                    failed.append(code)
                    logger.warning(f"拉取 {code} 失败: {e}")
                    time.sleep(0.5)

            if all_data:
                combined_df = pd.concat(all_data, ignore_index=True)
                saved = self._save_to_db_akshare(combined_df)
                return DataFetchResult(
                    fetcher_type=FetcherType.akshare,
                    success=True,
                    stock_count=len(stock_codes) - len(failed),
                    records=len(combined_df),
                    failed_stocks=failed
                )
            else:
                return DataFetchResult(
                    fetcher_type=FetcherType.akshare,
                    success=False,
                    message="未获取到数据"
                )
        except Exception as e:
            logger.error(f"AKShare 数据拉取失败: {e}")
            return DataFetchResult(
                fetcher_type=FetcherType.akshare,
                success=False,
                message=str(e)
            )

    def _save_to_db_tushare(self, df: pd.DataFrame) -> int:
        """保存 Tushare 数据到数据库"""
        from config.db import execute_many
        records = []
        for _, row in df.iterrows():
            # 转换股票代码格式
            ts_code = row['ts_code']
            if ts_code.endswith('.SH'):
                code = ts_code
            elif ts_code.endswith('.SZ'):
                code = ts_code
            else:
                continue
            # 格式化日期
            trade_date = pd.to_datetime(row['trade_date']).strftime('%Y-%m-%d')
            records.append((
                code, trade_date,
                float(row['open']) if pd.notna(row.get('open')) else None,
                float(row['high']) if pd.notna(row.get('high')) else None,
                float(row['low']) if pd.notna(row.get('low')) else None,
                float(row['close']) if pd.notna(row.get('close')) else None,
                int(row['vol']) if pd.notna(row.get('vol')) else None,
                float(row['amount']) if pd.notna(row.get('amount')) else None,
                float(row.get('turnover_rate')) if pd.notna(row.get('turnover_rate')) else None,
            ))
        if records:
            sql = """
                INSERT INTO trade_stock_daily
                (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount, turnover_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                open_price=VALUES(open_price), high_price=VALUES(high_price),
                low_price=VALUES(low_price), close_price=VALUES(close_price),
                volume=VALUES(volume), amount=VALUES(amount),
                turnover_rate=VALUES(turnover_rate)
            """
            execute_many(sql, records)
            return len(records)
        return 0

    def _save_to_db_akshare(self, df: pd.DataFrame) -> int:
        """保存 AKShare 数据到数据库"""
        from config.db import execute_many
        records = []
        for _, row in df.iterrows():
            # 格式化日期
            trade_date = row['trade_date'].strftime('%Y-%m-%d')
            # 转换股票代码格式
            code = row['stock_code']
            if code.startswith('6'):
                full_code = f"{code}.SH"
            else:
                full_code = f"{code}.SZ"
            records.append((
                full_code, trade_date,
                float(row['open']) if pd.notna(row.get('open')) else None,
                float(row['high']) if pd.notna(row.get('high')) else None,
                float(row['low']) if pd.notna(row.get('low')) else None,
                float(row['close']) if pd.notna(row.get('close')) else None,
                int(row['volume']) if pd.notna(row.get('volume')) else None,
                float(row['amount']) if pd.notna(row.get('amount')) else None,
                float(row['turnover_rate']) if pd.notna(row.get('turnover_rate')) else None,
            ))
        if records:
            sql = """
                INSERT INTO trade_stock_daily
                (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount, turnover_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                open_price=VALUES(open_price), high_price=VALUES(high_price),
                low_price=VALUES(low_price), close_price=VALUES(close_price),
                volume=VALUES(volume), amount=VALUES(amount),
                turnover_rate=VALUES(turnover_rate)
            """
            execute_many(sql, records)
            return len(records)
        return 0
    def check_data_integrity(self, expected_date: Optional[str] = None) -> Dict:
        """
        检查数据完整性

        Args:
            expected_date: 期望的最新日期，None 表示今天
        Returns:
            检查结果字典
        """
        if expected_date is None:
            expected_date = date.today().strftime('%Y-%m-%d')

        # 检查股票数量
        stock_count_sql = "SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_daily"
        result = execute_query(stock_count_sql)
        stock_count = result[0]['cnt'] if result else 0
        # 检查最新日期
        max_date_sql = "SELECT MAX(trade_date) as max_date FROM trade_stock_daily"
        result = execute_query(max_date_sql)
        max_date = result[0]['max_date'] if result else None
        # 检查记录数
        total_sql = "SELECT COUNT(*) as cnt FROM trade_stock_daily"
        result = execute_query(total_sql)
        total_records = result[0]['cnt'] if result else 0
        # 检查缺失数据的股票
        start_check = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
        missing_sql = """
            SELECT stock_code, COUNT(*) as cnt
            FROM trade_stock_daily
            WHERE trade_date >= %s
            GROUP BY stock_code
            HAVING cnt < 5
        """
        missing = execute_query(missing_sql, [start_check])
        # 检查完全没数据的股票
        empty_sql = """
            SELECT stock_code FROM trade_stock_daily
            WHERE trade_date >= %s
            GROUP BY stock_code
            HAVING COUNT(*) = 0
        """
        empty_stocks = execute_query(empty_sql, [start_check])
        is_ok = True
        issues = []
        # 检查股票数量
        if stock_count < 3000:
            is_ok = False
            issues.append(f"股票数量过少: {stock_count} (预期 5000+)")
        # 检查最新日期
        if max_date:
            max_date_str = max_date.strftime('%Y-%m-%d') if hasattr(max_date, 'strftime') else str(max_date)
            if max_date_str < expected_date:
                is_ok = False
                issues.append(f"数据未更新: 最新日期 {max_date_str} (预期 {expected_date})")
        else:
            is_ok = False
            issues.append("数据库中没有数据")
        return {
            'is_ok': is_ok,
            'stock_count': stock_count,
            'max_date': str(max_date) if max_date else None,
            'total_records': total_records,
            'issues': issues,
            'missing_stocks': [r['stock_code'] for r in missing] if missing else [],
            'empty_stocks': [r['stock_code'] for r in empty_stocks] if empty_stocks else []
        }

    def get_status(self) -> Dict:
        """获取数据拉取状态"""
        status = {
            'available_fetchers': [ft.value for ft in self.get_available_fetchers()],
            'data_integrity': self.check_data_integrity(),
            'last_fetch_status': self._last_fetch_status
        }
        return status


if __name__ == "__main__":
    # 测试
    manager = DataFetchManager()
    # 显示可用数据源
    print("可用数据源:")
    for ft in manager.get_available_fetchers():
        print(f"  - {ft.value}: {manager.config[ft]['description']}")
    # 检查数据完整性
    print("\n数据完整性检查:")
    result = manager.check_data_integrity()
    print(f"  状态: {'正常' if result['is_ok'] else '异常'}")
    print(f"  股票数量: {result['stock_count']}")
    print(f"  最新日期: {result['max_date']}")
    print(f"  总记录数: {result['total_records']}")
    if result['issues']:
        print(f"  问题:")
        for issue in result['issues']:
            print(f"    - {issue}")
