# -*- coding: utf-8 -*-
"""
总池子 CSV 解析器

解析 ~/Documents/notes/Finance/总池子.csv，提取股票代码、名称、行业，
并自动分类为 A股 / 港股 / ETF / 其他。
"""
import csv
import logging
from dataclasses import dataclass
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StockInfo:
    """股票基本信息"""
    code: str          # 纯数字代码，如 "600036"
    code_fmt: str      # 带后缀代码，如 "600036.SH" (A股/ETF) 或原始代码 (港股)
    name: str
    industry: str
    market: str        # "A" / "HK" / "ETF" / "OTHER"


def _format_a_share_code(code: str) -> str:
    """将纯数字代码转为带交易所后缀的格式"""
    code = code.strip().strip("'")
    if code.startswith(('6', '9')) and len(code) == 6:
        return f"{code}.SH"
    elif code.startswith(('0', '3')) and len(code) == 6:
        return f"{code}.SZ"
    elif code.startswith(('15', '51', '56', '58', '59')) and len(code) == 6:
        # ETF
        if code.startswith('1'):
            return f"{code}.SZ"
        else:
            return f"{code}.SH"
    return code


def _classify_market(code: str) -> str:
    """根据代码判断市场类型"""
    code = code.strip().strip("'")
    if code.startswith(('15', '51', '56', '58', '59')) and len(code) == 6:
        return "ETF"
    if code.startswith(('8', '4')) and len(code) == 6:
        return "BJ"  # 北交所
    if code.startswith(('0', '3', '6')) and len(code) == 6:
        return "A"
    if len(code) == 5 and code.startswith('0'):
        return "HK"
    # 转债、LOF 等
    return "OTHER"


def parse_universe_csv(csv_path: str) -> Tuple[List[StockInfo], List[StockInfo]]:
    """
    解析总池子 CSV 文件

    CSV 是 UTF-16 编码、Tab 分隔的单列表。

    Returns:
        (a_share_list, other_list) - A股+ETF 列表 和 港股+其他列表
    """
    stocks = []

    with open(csv_path, 'r', encoding='utf-16') as f:
        reader = csv.reader(f)
        header_line = next(reader)[0]
        headers = header_line.split('\t')
        # headers[1] = 代码, headers[2] = 名称, headers[14] = 所属行业

        for row in reader:
            fields = row[0].split('\t')
            if len(fields) < 15:
                continue

            code = fields[1].strip().strip("'")
            name = fields[2].strip().strip('"').strip()
            industry = fields[14].strip().strip('"').strip() if len(fields) > 14 else '--'

            if not code:
                continue

            market = _classify_market(code)
            code_fmt = _format_a_share_code(code) if market in ("A", "ETF") else code

            stocks.append(StockInfo(
                code=code,
                code_fmt=code_fmt,
                name=name,
                industry=industry,
                market=market,
            ))

    a_share = [s for s in stocks if s.market in ("A", "ETF")]
    other = [s for s in stocks if s.market not in ("A", "ETF")]

    logger.info(f"解析总池子: 总计 {len(stocks)} 只")
    logger.info(f"  A股+ETF: {len(a_share)} 只 (可进入分层)")
    logger.info(f"  港股+其他: {len(other)} 只 (仅展示)")

    return a_share, other
