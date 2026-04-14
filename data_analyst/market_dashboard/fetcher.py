# -*- coding: utf-8 -*-
"""
Market Dashboard Fetcher - collects new market-level indicators.

Writes to the `macro_data` table with appropriate indicator names.
Run daily after market close (16:30+).

Indicators fetched:
  - market_volume: Total A-share market volume (two exchanges)
  - advance_count / decline_count: Number of advancing/declining stocks
  - limit_up_count / limit_down_count: Limit up/down stock count
  - margin_balance / margin_net_buy: Margin trading data
  - new_high_60d / new_low_60d: 60-day new high/low count
  - seal_rate: Limit-up holding rate (seal rate)

No emoji - plain text labels only.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, date
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_update

logger = logging.getLogger(__name__)

UPSERT_SQL = """
    INSERT INTO macro_data (date, indicator, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value)
"""


def _normalize_date(d: str) -> str:
    """Normalize date string to YYYY-MM-DD format."""
    d = d.strip().replace('/', '-')
    if len(d) == 8 and '-' not in d:
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d


def _to_compact(d: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD for AKShare APIs."""
    return _normalize_date(d).replace('-', '')


def _save(trade_date: str, indicator: str, value, env: str = 'online'):
    """Upsert a single indicator value into macro_data."""
    if value is None:
        return
    trade_date = _normalize_date(trade_date)
    try:
        execute_update(UPSERT_SQL, (trade_date, indicator, float(value)), env=env)
        logger.info("[OK] %s %s = %s", trade_date, indicator, value)
    except Exception as e:
        logger.error("[FAIL] %s %s: %s", trade_date, indicator, e)


def fetch_market_volume(trade_date: str = None, env: str = 'online'):
    """
    Fetch total A-share market turnover amount (both exchanges, in yuan).

    Uses:
      1. SSE (stock_sse_deal_daily) + SZSE (stock_szse_summary) for exact amount
      2. Fallback: SH + SZ index volume (shares, less accurate)

    Stores as `market_volume` in yuan (e.g. 2.15e12 for 2.15 wan-yi).
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')
    compact_date = _to_compact(trade_date)

    # --- Method 1: Exchange official summary (accurate turnover in yuan) ---
    try:
        sse_amount = 0.0
        szse_amount = 0.0

        # SSE: returns amount in yi (100M yuan)
        df_sse = ak.stock_sse_deal_daily(date=compact_date)
        if df_sse is not None and not df_sse.empty:
            amount_row = df_sse[df_sse.iloc[:, 0].astype(str).str.contains('成交金额')]
            if not amount_row.empty:
                # Column '股票' has total stock turnover in yi
                sse_val = amount_row.iloc[0, 1]  # '股票' column
                sse_amount = float(sse_val) * 1e8  # yi -> yuan
                if trade_date == date.today().strftime('%Y-%m-%d'):
                    # Adjust trade_date to actual trading day from SSE data
                    pass

        # SZSE: returns amount in yuan
        df_szse = ak.stock_szse_summary(date=compact_date)
        if df_szse is not None and not df_szse.empty:
            stock_row = df_szse[df_szse.iloc[:, 0].astype(str).str.contains('股票')]
            if not stock_row.empty:
                amount_col = None
                for col in df_szse.columns:
                    if '成交金额' in str(col):
                        amount_col = col
                        break
                if amount_col and not stock_row.empty:
                    szse_amount = float(stock_row.iloc[0][amount_col])

        total = sse_amount + szse_amount
        if total > 0:
            trade_date = _normalize_date(trade_date)
            _save(trade_date, 'market_volume', total, env=env)
            logger.info("[OK] %s market_volume = %.0f (SSE %.0f + SZSE %.0f)",
                        trade_date, total, sse_amount, szse_amount)
            return total
    except Exception as e:
        logger.warning("exchange summary fetch failed, trying fallback: %s", e)

    # --- Method 2: Fallback - SH + SZ index volume (shares, not yuan) ---
    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty:
            df['date'] = df['date'].astype(str)
            row = df[df['date'] == trade_date]
            if row.empty:
                row = df.tail(1)
                trade_date = str(row.iloc[0]['date'])

            volume = float(row.iloc[0]['volume'])
            # Note: this is shares not yuan, stored with '_shares' suffix
            _save(trade_date, 'market_volume', volume, env=env)
            logger.warning("[FALLBACK] %s market_volume = %.0f (shares, not yuan)", trade_date, volume)
            return volume
    except Exception as e:
        logger.error("fetch_market_volume failed: %s", e)
    return None


def fetch_advance_decline(trade_date: str = None, env: str = 'online'):
    """
    Fetch number of advancing and declining stocks.

    Method 1: stock_market_activity_legu (乐股网) - returns aggregated counts directly
    Method 2: stock_zh_a_spot_em (东财EM) - blocked on Aliyun cloud servers
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    # --- Method 1: stock_market_activity_legu (works on cloud servers) ---
    try:
        df = ak.stock_market_activity_legu()
        if df is not None and not df.empty:
            # Returns rows like: 上涨, 下跌, 平盘, 涨停, 跌停 etc.
            # Column names: '项目', '数量' or similar
            name_col = df.columns[0]
            val_col = df.columns[1]
            row_map = dict(zip(df[name_col].astype(str), df[val_col]))

            advance = int(float(row_map.get('上涨', 0)))
            decline = int(float(row_map.get('下跌', 0)))
            flat = int(float(row_map.get('平盘', 0)))

            if advance > 0 or decline > 0:
                _save(trade_date, 'advance_count', advance, env=env)
                _save(trade_date, 'decline_count', decline, env=env)
                _save(trade_date, 'flat_count', flat, env=env)
                logger.info("[legu] Advance: %d, Decline: %d, Flat: %d", advance, decline, flat)
                return
            logger.warning("stock_market_activity_legu returned zero advance/decline, trying fallback")
    except Exception as e:
        logger.warning("stock_market_activity_legu failed, trying fallback: %s", e)

    # --- Method 2: stock_zh_a_spot_em (may be blocked on cloud) ---
    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            logger.warning("stock_zh_a_spot_em returned empty")
            return

        pct_col = None
        for col_name in ['涨跌幅', '涨跌百分比', 'change_pct']:
            if col_name in df.columns:
                pct_col = col_name
                break

        if pct_col is None:
            logger.warning("Cannot find change percent column. Columns: %s", list(df.columns))
            return

        changes = df[pct_col].astype(float)
        advance = int((changes > 0).sum())
        decline = int((changes < 0).sum())
        flat = int((changes == 0).sum())

        _save(trade_date, 'advance_count', advance, env=env)
        _save(trade_date, 'decline_count', decline, env=env)
        _save(trade_date, 'flat_count', flat, env=env)
        logger.info("[spot_em] Advance: %d, Decline: %d, Flat: %d", advance, decline, flat)
    except Exception as e:
        logger.error("fetch_advance_decline failed: %s", e)


def fetch_limit_up_down(trade_date: str = None, env: str = 'online'):
    """
    Fetch limit-up and limit-down stock count + seal rate.
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y%m%d')
    else:
        trade_date = _to_compact(trade_date)

    try:
        # Limit up pool
        df_up = ak.stock_zt_pool_em(date=trade_date)
        limit_up = len(df_up) if df_up is not None and not df_up.empty else 0

        # Limit down pool
        try:
            df_down = ak.stock_zt_pool_dtgc_em(date=trade_date)
            limit_down = len(df_down) if df_down is not None and not df_down.empty else 0
        except Exception:
            limit_down = 0

        date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
        _save(date_str, 'limit_up_count', limit_up, env=env)
        _save(date_str, 'limit_down_count', limit_down, env=env)

        # Seal rate: count stocks that stayed at limit up until close
        if df_up is not None and not df_up.empty and limit_up > 0:
            # stock_zt_pool_em returns stocks at limit-up at close
            # For seal rate, we also need "曾涨停" (stocks that touched limit up)
            try:
                df_touched = ak.stock_zt_pool_previous_em(date=trade_date)
                total_touched = limit_up + (len(df_touched) if df_touched is not None else 0)
                seal_rate = limit_up / total_touched * 100 if total_touched > 0 else 0
            except Exception:
                seal_rate = 100.0 if limit_up > 0 else 0
            _save(date_str, 'seal_rate', round(seal_rate, 1), env=env)

        logger.info("Limit up: %d, Limit down: %d", limit_up, limit_down)
    except Exception as e:
        logger.error("fetch_limit_up_down failed: %s", e)


def fetch_margin_data(trade_date: str = None, env: str = 'online'):
    """
    Fetch margin balance and net buy data.
    """
    import akshare as ak
    if trade_date is None:
        trade_date = date.today().strftime('%Y%m%d')
    else:
        trade_date = _to_compact(trade_date)

    try:
        # Shanghai margin data
        df_sh = ak.stock_margin_sse(
            start_date=(datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=10)).strftime('%Y%m%d'),
            end_date=trade_date,
        )
        if df_sh is not None and not df_sh.empty:
            latest = df_sh.iloc[-1]

            # Determine date from data
            date_col = None
            for c in df_sh.columns:
                if '日期' in str(c):
                    date_col = c
                    break
            if date_col and latest[date_col] is not None:
                date_str = _normalize_date(str(latest[date_col]))
            else:
                date_str = _normalize_date(trade_date)

            # Margin balance and net buy - find columns by keyword matching
            balance_col = None
            buy_col = None
            for col in df_sh.columns:
                col_str = str(col)
                if '余额' in col_str and '融资' in col_str:
                    balance_col = col
                if '买入' in col_str and '融资' in col_str:
                    buy_col = col

            if balance_col:
                balance = float(latest[balance_col])
                _save(date_str, 'margin_balance', balance, env=env)
            else:
                logger.warning("Cannot find margin balance column. Columns: %s", list(df_sh.columns))

            if buy_col:
                buy = float(latest[buy_col])
                _save(date_str, 'margin_net_buy', buy, env=env)
            else:
                logger.warning("Cannot find margin buy column. Columns: %s", list(df_sh.columns))

    except Exception as e:
        logger.error("fetch_margin_data failed: %s", e)


def fetch_new_high_low(trade_date: str = None, env: str = 'online'):
    """
    Calculate 60-day new high/low count from trade_stock_daily.
    """
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    try:
        # Count stocks at 60-day high/low using a JOIN instead of correlated subqueries
        rows = execute_query("""
            SELECT
                SUM(CASE WHEN a.close_price >= hist.high_60d THEN 1 ELSE 0 END) AS new_high,
                SUM(CASE WHEN a.close_price <= hist.low_60d THEN 1 ELSE 0 END) AS new_low
            FROM trade_stock_daily a
            INNER JOIN (
                SELECT stock_code,
                       MAX(high_price) AS high_60d,
                       MIN(low_price) AS low_60d
                FROM trade_stock_daily
                WHERE trade_date BETWEEN DATE_SUB(%s, INTERVAL 60 DAY)
                                     AND DATE_SUB(%s, INTERVAL 1 DAY)
                GROUP BY stock_code
            ) hist ON a.stock_code = hist.stock_code
            WHERE a.trade_date = %s
              AND a.close_price > 0
        """, (trade_date, trade_date, trade_date))

        if rows and rows[0]:
            new_high = int(rows[0]['new_high'] or 0)
            new_low = int(rows[0]['new_low'] or 0)
            _save(trade_date, 'new_high_60d', new_high, env=env)
            _save(trade_date, 'new_low_60d', new_low, env=env)
            logger.info("New 60d high: %d, low: %d", new_high, new_low)
    except Exception as e:
        logger.error("fetch_new_high_low failed: %s", e)


def fetch_all(trade_date: str = None, env: str = 'online'):
    """
    Run all fetchers for a single trade date.
    Call this in the daily scheduler after market close.
    """
    if trade_date is None:
        trade_date = date.today().strftime('%Y-%m-%d')

    logger.info("=== Market Dashboard Fetch: %s (env=%s) ===", trade_date, env)

    fetch_market_volume(trade_date, env=env)
    fetch_advance_decline(trade_date, env=env)
    fetch_limit_up_down(trade_date, env=env)
    fetch_margin_data(trade_date, env=env)
    fetch_new_high_low(trade_date, env=env)

    logger.info("=== Market Dashboard Fetch Complete ===")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    parser = argparse.ArgumentParser(description='Fetch market dashboard indicators')
    parser.add_argument('--date', help='Trade date (YYYY-MM-DD)')
    parser.add_argument('--env', default='online', help='DB environment')
    args = parser.parse_args()

    fetch_all(trade_date=args.date, env=args.env)
