# -*- coding: utf-8 -*-
"""
research/industry_classifier.py

将申万一级行业映射到估值模型类型。
不同行业类型使用不同的估值评分逻辑：
- CYCLICAL  周期资源：石油/煤炭/有色/钢铁/化工/航运 -> PB-ROE 模型
- FINANCIAL 金融地产：银行/保险/证券/房地产         -> PB 主导
- GROWTH    成长科技：半导体/软件/新能源             -> PE 分位主导
- CONSUMER  消费医药：食品饮料/医药/家电/零售        -> PE 分位主导
- UNKNOWN   未分类                                  -> PE 分位主导（默认）
"""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class IndustryType(Enum):
    CYCLICAL = "周期资源"
    FINANCIAL = "金融地产"
    GROWTH = "成长科技"
    CONSUMER = "消费医药"
    UNKNOWN = "未分类"


# 申万一级行业名称 -> IndustryType
_SW_MAP: dict[str, IndustryType] = {
    # 周期资源
    "石油石化": IndustryType.CYCLICAL,
    "煤炭":     IndustryType.CYCLICAL,
    "有色金属": IndustryType.CYCLICAL,
    "钢铁":     IndustryType.CYCLICAL,
    "基础化工": IndustryType.CYCLICAL,
    "建筑材料": IndustryType.CYCLICAL,
    "建筑装饰": IndustryType.CYCLICAL,
    "公用事业": IndustryType.CYCLICAL,
    "环保":     IndustryType.CYCLICAL,
    "机械设备": IndustryType.CYCLICAL,
    "汽车":     IndustryType.CYCLICAL,
    "交通运输": IndustryType.CYCLICAL,
    # 金融地产
    "银行":     IndustryType.FINANCIAL,
    "非银金融": IndustryType.FINANCIAL,
    "房地产":   IndustryType.FINANCIAL,
    # 成长科技
    "电子":     IndustryType.GROWTH,
    "计算机":   IndustryType.GROWTH,
    "通信":     IndustryType.GROWTH,
    "传媒":     IndustryType.GROWTH,
    "电力设备": IndustryType.GROWTH,
    "国防军工": IndustryType.GROWTH,
    # 消费医药
    "食品饮料": IndustryType.CONSUMER,
    "医药生物": IndustryType.CONSUMER,
    "家用电器": IndustryType.CONSUMER,
    "美容护理": IndustryType.CONSUMER,
    "商贸零售": IndustryType.CONSUMER,
    "社会服务": IndustryType.CONSUMER,
    "农林牧渔": IndustryType.CONSUMER,
    "纺织服饰": IndustryType.CONSUMER,
    "轻工制造": IndustryType.CONSUMER,
}


class IndustryClassifier:
    """根据申万行业名称返回行业类型，支持数据库查询和直接传名称两种方式。"""

    def __init__(self, env: str = "online"):
        self.env = env
        self._cache: dict[str, IndustryType] = {}

    def classify_by_name(self, sw_industry_name: str) -> IndustryType:
        """直接根据申万行业名称返回类型（无需 DB）。"""
        if not sw_industry_name:
            return IndustryType.UNKNOWN
        return _SW_MAP.get(sw_industry_name.strip(), IndustryType.UNKNOWN)

    def classify_by_code(self, stock_code: str) -> IndustryType:
        """根据股票代码查询 DB 获取申万行业名称，然后映射。"""
        if stock_code in self._cache:
            return self._cache[stock_code]

        sw_name = self._fetch_sw_industry(stock_code)
        industry_type = self.classify_by_name(sw_name)

        if industry_type == IndustryType.UNKNOWN and sw_name:
            logger.debug(f"[{stock_code}] 申万行业 '{sw_name}' 未在映射表中，归为 UNKNOWN")

        self._cache[stock_code] = industry_type
        return industry_type

    def _fetch_sw_industry(self, stock_code: str) -> str:
        try:
            from config.db import execute_query
            # 优先查 trade_stock_industry 表（申万分类），回退到 trade_stock_basic.industry
            rows = execute_query(
                """
                SELECT industry_name FROM trade_stock_industry
                WHERE stock_code = %s AND classify_type = 'SW' AND industry_level = '1'
                LIMIT 1
                """,
                [stock_code],
                env=self.env,
            )
            if rows and rows[0].get("industry_name"):
                return rows[0]["industry_name"]

            # 回退：trade_stock_basic.industry
            rows = execute_query(
                "SELECT industry FROM trade_stock_basic WHERE stock_code = %s LIMIT 1",
                [stock_code],
                env=self.env,
            )
            if rows and rows[0].get("industry"):
                return rows[0]["industry"]
        except Exception as e:
            logger.warning(f"[{stock_code}] 查询申万行业失败: {e}")
        return ""
