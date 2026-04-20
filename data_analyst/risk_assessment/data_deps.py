# -*- coding: utf-8 -*-

import logging
import importlib
from datetime import date, datetime
from typing import List, Optional

from data_analyst.risk_assessment.schemas import DataStatus

logger = logging.getLogger(__name__)

# 数据依赖配置
# trigger 格式: 'module.path.function'，None 表示无自动触发
DEPENDENCIES = [
    {
        'name': 'macro_data',
        'table': 'macro_data',
        'date_column': 'date',
        'max_delay_days': 2,
        'trigger': None,
        'critical': True,
    },
    {
        'name': 'trade_stock_daily',
        'table': 'trade_stock_daily',
        'date_column': 'trade_date',
        'max_delay_days': 1,
        'trigger': None,
        'critical': True,
    },
    {
        'name': 'sw_industry_valuation',
        'table': 'sw_industry_valuation',
        'date_column': 'trade_date',
        'max_delay_days': 1,
        'trigger': None,
        'critical': False,
    },
    {
        'name': 'trade_svd_market_state',
        'table': 'trade_svd_market_state',
        'date_column': 'calc_date',
        'max_delay_days': 1,
        'trigger': None,
        'critical': False,
    },
    {
        'name': 'trade_fear_index',
        'table': 'trade_fear_index',
        'date_column': 'trade_date',
        'max_delay_days': 2,
        'trigger': None,
        'critical': False,
    },
    {
        'name': 'trade_stock_factor',
        'table': 'trade_stock_factor',
        'date_column': 'calc_date',
        'max_delay_days': 1,
        'trigger': None,
        'critical': False,
    },
    {
        'name': 'trade_stock_rps',
        'table': 'trade_stock_rps',
        'date_column': 'trade_date',
        'max_delay_days': 1,
        'trigger': None,
        'critical': False,
    },
    {
        'name': 'trade_news_sentiment',
        'table': 'trade_news_sentiment',
        'date_column': 'publish_time',
        'max_delay_days': 3,
        'trigger': None,
        'critical': False,
    },
]


def _call_trigger(trigger_path: str) -> bool:
    """尝试通过 'module.path.function' 格式调用触发函数。返回是否成功。"""
    try:
        parts = trigger_path.rsplit('.', 1)
        if len(parts) != 2:
            logger.error("trigger 格式错误: %s，期望 'module.path.function'", trigger_path)
            return False
        module_path, func_name = parts
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        func()
        return True
    except Exception as e:
        logger.error("触发 %s 失败: %s", trigger_path, e)
        return False


class DataDependencyChecker:
    """检查各数据表的最新日期，必要时自动触发更新。"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def _query_max_date(self, table: str, date_column: str) -> Optional[date]:
        """查询表中最大日期。"""
        try:
            from config.db import execute_query
            rows = list(execute_query(
                "SELECT MAX({}) AS max_date FROM {}".format(date_column, table),
                (),
                env=self.env,
            ))
            if rows and rows[0]['max_date'] is not None:
                val = rows[0]['max_date']
                if isinstance(val, date):
                    return val
                if isinstance(val, datetime):
                    return val.date()
                # 尝试字符串解析
                return datetime.strptime(str(val), '%Y-%m-%d').date()
        except Exception as e:
            logger.warning("查询 %s.%s 最大日期失败: %s", table, date_column, e)
        return None

    def check_and_trigger(self) -> List[DataStatus]:
        """检查所有依赖数据的新鲜度，必要时触发更新，返回 DataStatus 列表。"""
        today = date.today()
        results: List[DataStatus] = []

        for dep in DEPENDENCIES:
            name = dep['name']
            table = dep['table']
            date_col = dep['date_column']
            max_delay = dep['max_delay_days']
            trigger = dep.get('trigger')

            max_date = self._query_max_date(table, date_col)

            if max_date is None:
                results.append(DataStatus(
                    name=name,
                    latest_date='',
                    delay_days=-1,
                    status='no_data',
                ))
                continue

            delay_days = (today - max_date).days
            latest_date_str = str(max_date)

            if delay_days <= max_delay:
                status = 'ok'
            else:
                # 数据过期，尝试触发
                if trigger:
                    logger.info("[WARN] %s 数据延迟 %d 天，尝试触发: %s", name, delay_days, trigger)
                    success = _call_trigger(trigger)
                    status = 'auto_triggered' if success else 'trigger_failed'
                else:
                    status = 'stale'
                    logger.warning("[WARN] %s 数据延迟 %d 天（允许 %d 天），无触发器", name, delay_days, max_delay)

            results.append(DataStatus(
                name=name,
                latest_date=latest_date_str,
                delay_days=delay_days,
                status=status,
            ))

        return results
