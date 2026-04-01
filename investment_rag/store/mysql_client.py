# -*- coding: utf-8 -*-
"""
MySQL client for Text2SQL queries. Reuses config.db.
"""
import logging
from typing import List, Dict, Any, Optional

from config.db import execute_query, get_connection

logger = logging.getLogger(__name__)


class MySQLClient:
    """Wrapper for structured data queries via Text2SQL."""

    def __init__(self, env: str = "online"):
        self.env = env

    def execute_sql(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results.

        Args:
            sql: SQL query string.
            params: Query parameters.

        Returns:
            List of row dicts.
        """
        try:
            results = execute_query(sql, params, env=self.env)
            return results
        except Exception as e:
            logger.error("SQL execution failed: %s, error: %s", sql, e)
            return []

    def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get column info for a table.

        Args:
            table_name: Name of the table.

        Returns:
            Dict with column info, or None if table doesn't exist.
        """
        sql = """
            SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """
        columns = self.execute_sql(sql, (table_name,))
        if not columns:
            return None

        return {
            "table": table_name,
            "columns": columns,
        }
