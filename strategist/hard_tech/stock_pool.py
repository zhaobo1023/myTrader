# -*- coding: utf-8 -*-
"""
Hard-tech stock pool builder

Builds universe from:
  - 10 hard-tech industries in trade_stock_basic
  - 688xxx (KCB) and 300xxx (CYB) boards
  - R&D intensity filter (rd_expense / revenue > threshold)
"""
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query
from .config import HARD_TECH_INDUSTRIES, RD_INTENSITY_THRESHOLD

logger = logging.getLogger(__name__)


def build_hardtech_universe() -> list:
    """
    Get all hard-tech stock codes from trade_stock_basic.

    Covers:
      - 10 hard-tech industries
      - 688xxx (KCB) and 300xxx (CYB) boards

    Returns:
        list of stock_code with suffix (e.g. '300750.SZ')
    """
    placeholders = ', '.join(['%s'] * len(HARD_TECH_INDUSTRIES))
    sql = f"""
        SELECT DISTINCT stock_code
        FROM trade_stock_basic
        WHERE industry IN ({placeholders})
           OR stock_code LIKE '688%%'
           OR stock_code LIKE '300%%'
    """
    rows = execute_query(sql, HARD_TECH_INDUSTRIES)
    codes = [r['stock_code'] for r in rows]
    logger.info(f"Hard-tech universe: {len(codes)} stocks")
    return codes


def get_industry_map() -> dict:
    """
    Get {stock_code: industry} mapping for hard-tech stocks.

    Returns:
        dict, e.g. {'300750.SZ': '电气设备', '688981.SH': '电子'}
    """
    placeholders = ', '.join(['%s'] * len(HARD_TECH_INDUSTRIES))
    sql = f"""
        SELECT stock_code, industry
        FROM trade_stock_basic
        WHERE industry IN ({placeholders})
           OR stock_code LIKE '688%%'
           OR stock_code LIKE '300%%'
    """
    rows = execute_query(sql, HARD_TECH_INDUSTRIES)
    return {r['stock_code']: r['industry'] for r in rows if r['industry']}


def apply_rd_filter(stock_codes: list, threshold: float = None) -> list:
    """
    Filter stocks by R&D intensity threshold.

    Stocks WITH rd_intensity data: keep if rd_intensity >= threshold.
    Stocks WITHOUT rd_intensity data: excluded.

    Args:
        stock_codes: list of stock_code with suffix
        threshold: rd_expense / revenue ratio (default from config)

    Returns:
        list of stock_code that pass the R&D filter
    """
    if threshold is None:
        threshold = RD_INTENSITY_THRESHOLD

    if not stock_codes:
        return []

    # Batch query to avoid SQL length limit
    batch_size = 500
    all_filtered = []

    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ', '.join(['%s'] * len(batch))
        sql = f"""
            SELECT stock_code, rd_intensity
            FROM trade_stock_hardtech_factor
            WHERE stock_code IN ({placeholders})
              AND rd_intensity IS NOT NULL
              AND calc_date = (
                  SELECT MAX(calc_date) FROM trade_stock_hardtech_factor
                  WHERE rd_intensity IS NOT NULL
              )
        """
        rows = execute_query(sql, batch)
        passed = [r['stock_code'] for r in rows
                  if r['rd_intensity'] is not None and float(r['rd_intensity']) >= threshold]
        all_filtered.extend(passed)

    logger.info(f"RD filter (>= {threshold:.1%}): {len(all_filtered)}/{len(stock_codes)} passed")
    return all_filtered


def get_stock_names(stock_codes: list) -> dict:
    """
    Get {stock_code: stock_name} mapping.

    Returns:
        dict, e.g. {'300750.SZ': '宁德时代'}
    """
    if not stock_codes:
        return {}

    result = {}
    batch_size = 500

    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ', '.join(['%s'] * len(batch))
        sql = f"""
            SELECT DISTINCT stock_code, stock_name
            FROM trade_stock_basic
            WHERE stock_code IN ({placeholders})
        """
        rows = execute_query(sql, batch)
        for r in rows:
            result[r['stock_code']] = r['stock_name']

    return result
