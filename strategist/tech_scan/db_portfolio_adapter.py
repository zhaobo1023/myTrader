# -*- coding: utf-8 -*-
"""
Database portfolio adapter for tech_scan.

Reads positions from user_positions table instead of Markdown file.
Returns the same Position dataclass used by PortfolioParser.
"""
from typing import List

from config.db import execute_query
from strategist.tech_scan.portfolio_parser import Position


class DbPortfolioAdapter:
    """Read user positions from database, returning Position objects."""

    def __init__(self, user_id: int, env: str = 'online'):
        self.user_id = user_id
        self.env = env

    def parse(self) -> List[Position]:
        """Query active positions for user and return as Position list."""
        sql = """
            SELECT stock_code, stock_name, level, shares, cost_price
            FROM user_positions
            WHERE user_id = %s AND is_active = 1
            ORDER BY level, stock_code
        """
        rows = execute_query(sql, (self.user_id,), env=self.env)
        if not rows:
            return []

        positions = []
        for row in rows:
            code = row['stock_code']
            # Add market suffix if not present
            if '.' not in code:
                code = self._add_market_suffix(code)
            positions.append(Position(
                code=code,
                name=row.get('stock_name', ''),
                level=row.get('level', 'L3'),
                shares=row.get('shares'),
                cost=row.get('cost_price'),
            ))
        return positions

    @staticmethod
    def _add_market_suffix(code: str) -> str:
        """Determine .SH or .SZ suffix by code prefix."""
        if code.startswith(('6', '5', '9')):
            return f'{code}.SH'
        return f'{code}.SZ'
