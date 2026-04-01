# -*- coding: utf-8 -*-
"""
Rule-based Text2SQL: template matching for common structured queries.

Targets MySQL tables:
    - trade_stock_daily_basic  (PE, PB, PS, market_cap, turnover_rate)
    - trade_stock_daily_factor (7 base factors + macro factors)
    - trade_stock_daily        (price data)
    - trade_stock_financial    (financial metrics)
    - trade_stock_rps          (RPS values)
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from investment_rag.store.mysql_client import MySQLClient

logger = logging.getLogger(__name__)


class Text2SQL:
    """Rule-based Text2SQL engine for structured data queries."""

    # Stock code pattern: 6-digit number, optionally with SZ/SH suffix
    STOCK_CODE_RE = re.compile(
        r'(\d{6})(?:\.(SZ|SH|sz|sh))?'
    )

    def __init__(self, mysql_client: Optional[MySQLClient] = None):
        self.mysql = mysql_client or MySQLClient()

    def _extract_stock_code(self, query: str) -> Optional[str]:
        """Extract stock code from query."""
        match = self.STOCK_CODE_RE.search(query)
        if match:
            return match.group(1)
        return None

    def _extract_stock_name(self, query: str) -> Optional[str]:
        """Try to resolve stock name to code. This requires a lookup table."""
        # For now, we only support code-based queries
        return None

    def _parse_comparison(self, query: str) -> List[Tuple[str, str, str]]:
        """Extract field comparisons like 'PE<20', 'PB>1' from query.

        Returns:
            List of (field, operator, value) tuples.
        """
        comparisons = []

        # Normalize Chinese comparison operators to symbols
        op_map = {
            "小于": "<", "低于": "<", "不到": "<",
            "大于": ">", "高于": ">", "超过": ">",
            "等于": "=", "等于": "=", "是": "=",
        }
        normalized_query = query
        for cn_op, sym_op in op_map.items():
            normalized_query = normalized_query.replace(cn_op, sym_op)

        # Pattern: field <op> number (e.g., PE<20, PB > 1, 市值>=100)
        pattern = re.compile(
            r'(PE|PB|PS|市值|换手率|市盈率|市净率|市销率)'
            r'\s*([<>=]+)\s*'
            r'([\d.]+)'
        )
        for match in pattern.finditer(normalized_query):
            field_raw = match.group(1)
            op = match.group(2)
            value = match.group(3)

            # Normalize field names
            field_map = {
                "PE": "pe",
                "市盈率": "pe",
                "PB": "pb",
                "市净率": "pb",
                "PS": "ps",
                "市销率": "ps",
                "市值": "total_mv",
                "换手率": "turnover_rate",
            }
            field = field_map.get(field_raw, field_raw.lower())
            comparisons.append((field, op, value))

        return comparisons

    def build_query(
        self,
        natural_query: str,
    ) -> Optional[Dict[str, Any]]:
        """Convert a natural language query to SQL.

        Args:
            natural_query: User's natural language query.

        Returns:
            Dict with 'sql', 'params', 'description' or None if no match.
        """
        stock_code = self._extract_stock_code(natural_query)

        # Try comparison-based screening
        comparisons = self._parse_comparison(natural_query)
        if comparisons:
            return self._build_screening_query(comparisons, stock_code)

        # Try simple metric lookup for a specific stock
        if stock_code:
            return self._build_metric_query(stock_code, natural_query)

        return None

    def _build_screening_query(
        self,
        comparisons: List[Tuple[str, str, str]],
        stock_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a stock screening SQL query."""
        # Map fields to actual column names
        column_map = {
            "pe": "pe_ttm",
            "pb": "pb",
            "ps": "ps_ttm",
            "total_mv": "total_mv",
            "turnover_rate": "turnover_rate",
        }

        where_clauses = []
        params = []

        if stock_code:
            where_clauses.append("ts_code = %s")
            params.append(stock_code)

        for field, op, value in comparisons:
            col = column_map.get(field, field)
            where_clauses.append(f"{col} {op} %s")
            params.append(float(value))

        where_sql = " AND ".join(where_clauses)

        sql = f"""
            SELECT ts_code, trade_date, pe_ttm, pb, ps_ttm, total_mv, turnover_rate
            FROM trade_stock_daily_basic
            WHERE {where_sql}
            ORDER BY trade_date DESC
            LIMIT 50
        """

        return {
            "sql": sql,
            "params": tuple(params),
            "description": f"Screen stocks: {', '.join(f'{f}{o}{v}' for f, o, v in comparisons)}",
        }

    def _build_metric_query(
        self,
        stock_code: str,
        query: str,
    ) -> Dict[str, Any]:
        """Build a simple metric lookup query."""
        # Detect which metric the user wants
        metric_map = {
            "毛利率": "gross_margin",
            "净利率": "net_margin",
            "ROE": "roe",
            "ROA": "roa",
            "营收": "revenue",
            "净利润": "net_profit",
        }

        metric = None
        for keyword, col in metric_map.items():
            if keyword in query:
                metric = col
                break

        if metric and "financial" in metric_map.values():
            sql = f"""
                SELECT ts_code, end_date, {metric}
                FROM trade_stock_financial
                WHERE ts_code = %s
                ORDER BY end_date DESC
                LIMIT 10
            """
            return {
                "sql": sql,
                "params": (stock_code,),
                "description": f"Get {metric} for stock {stock_code}",
            }

        # Default: return latest daily basic data
        sql = """
            SELECT ts_code, trade_date, pe_ttm, pb, ps_ttm, total_mv, turnover_rate
            FROM trade_stock_daily_basic
            WHERE ts_code = %s
            ORDER BY trade_date DESC
            LIMIT 10
        """
        return {
            "sql": sql,
            "params": (stock_code,),
            "description": f"Get basic metrics for stock {stock_code}",
        }

    def execute(self, natural_query: str) -> List[Dict[str, Any]]:
        """Execute a natural language query against MySQL.

        Args:
            natural_query: User's natural language query.

        Returns:
            Query results as list of dicts, or empty list if no match.
        """
        query_info = self.build_query(natural_query)
        if not query_info:
            logger.info("No SQL template matched for query: %s", natural_query)
            return []

        logger.info("Generated SQL: %s", query_info["sql"])
        results = self.mysql.execute_sql(query_info["sql"], query_info["params"])
        return results
