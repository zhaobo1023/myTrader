# -*- coding: utf-8 -*-
"""
持仓文件解析器

解析 Markdown 格式的持仓文件，提取 A 股/ETF 代码、成本价等信息。
"""
import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Position:
    """持仓信息"""
    code: str           # 股票代码，如 601857.SH
    name: str           # 股票名称
    level: str          # 持仓层级 L1/L2/L3
    shares: Optional[int] = None  # 股数
    cost: Optional[float] = None  # 成本价


class PortfolioParser:
    """持仓文件解析器"""

    # A股代码正则：6位数字
    CODE_PATTERN = re.compile(r'\|\s*(\d{6})\s*\|')

    # ETF代码正则：15xxxx 或 51xxxx 等
    ETF_PREFIXES = ('15', '51', '56', '58', '59')

    # 成本价正则：匹配数字（含小数），可能带 ~ 前缀
    COST_PATTERN = re.compile(r'~?\d+\.?\d*')

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def parse(self) -> List[Position]:
        """
        解析持仓文件，返回 A 股/ETF 持仓列表

        跳过港股（00xxx 开头）和美股（字母代码）
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"持仓文件不存在: {self.file_path}")

        content = self.file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        positions = []
        current_level = None

        for line in lines:
            # 检测层级标题
            if '## L1' in line:
                current_level = 'L1'
            elif '## L2' in line:
                current_level = 'L2'
            elif '## L3' in line:
                current_level = 'L3'
            elif '## 港股' in line or '## 美股' in line:
                current_level = None  # 跳过港美股

            # 跳过非 A 股层级
            if current_level is None:
                continue

            # 解析表格行
            if '|' in line and current_level:
                pos = self._parse_table_row(line, current_level)
                if pos:
                    positions.append(pos)

        return positions

    def _parse_table_row(self, line: str, level: str) -> Optional[Position]:
        """解析表格行"""
        # 跳过表头和分隔行
        if '---' in line or '代码' in line or '名称' in line:
            return None

        # 提取代码
        match = self.CODE_PATTERN.search(line)
        if not match:
            return None

        code = match.group(1)

        # 跳过港股代码（原始 Markdown 中可能是 5 位数字如 00700）
        # 正则已限制 6 位数字，此处为防御性检查
        if len(code) != 6:
            return None

        # 确定市场后缀
        suffix = self._get_market_suffix(code)
        full_code = f"{code}.{suffix}"

        # 提取名称（代码后面的单元格）
        parts = line.split('|')
        name = ""
        for i, part in enumerate(parts):
            if code in part and i + 1 < len(parts):
                name = parts[i + 1].strip()
                break

        # 提取股数（如果有）
        shares = None
        for part in parts:
            part = part.strip()
            if part.isdigit() and len(part) >= 3:
                shares = int(part)
                break

        # 提取成本价（第5列，索引5）
        cost = self._extract_cost(parts)

        return Position(
            code=full_code,
            name=name,
            level=level,
            shares=shares,
            cost=cost
        )

    def _extract_cost(self, parts: List[str]) -> Optional[float]:
        """
        从表格行中提取成本价

        持仓文件格式：| 代码 | 名称 | 股数 | 账户 | 成本价 | 当前价 | 盈亏比例 | ...
        成本价在第5列（索引5），可能包含 ~ 前缀
        """
        # 成本价在代码所在列之后的第3个数值列
        # 格式: | 601857 | 中国石油 | 21400 | 东财 | 11.99 | 12.07 | +3.788% | ...
        # 索引:    0        1          2      3       4       5        6
        for i, part in enumerate(parts):
            part = part.strip()
            # 跳过代码、名称、股数、账户列
            if i < 4:
                continue
            # 成本价：纯数字或 ~ 数字
            if re.match(r'^~?\d+\.?\d*$', part):
                try:
                    return float(part.replace('~', ''))
                except ValueError:
                    continue
        return None

    def _get_market_suffix(self, code: str) -> str:
        """根据代码判断市场后缀"""
        # 沪市：60xxxx, 68xxxx (科创板), 51xxxx (ETF)
        if code.startswith(('60', '68', '51', '58')):
            return 'SH'
        # 深市：00xxxx, 30xxxx (创业板), 15xxxx (ETF), 12xxxx (可转债)
        elif code.startswith(('00', '30', '15', '12', '56', '59')):
            return 'SZ'
        else:
            return 'SH'  # 默认沪市


def parse_portfolio(file_path: str) -> List[Position]:
    """便捷函数：解析持仓文件"""
    parser = PortfolioParser(file_path)
    return parser.parse()


if __name__ == '__main__':
    # 测试解析
    from .config import DEFAULT_CONFIG

    positions = parse_portfolio(DEFAULT_CONFIG.portfolio_file)
    print(f"解析到 {len(positions)} 只 A股/ETF:\n")

    for level in ['L1', 'L2', 'L3']:
        level_pos = [p for p in positions if p.level == level]
        if level_pos:
            print(f"【{level}】{len(level_pos)} 只")
            for p in level_pos:
                cost_str = f"成本={p.cost}" if p.cost else "成本=未知"
                print(f"  {p.code} {p.name} {cost_str}")
            print()
