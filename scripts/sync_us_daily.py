# -*- coding: utf-8 -*-
"""
Sync US stock daily data via yfinance (run locally with proxy).
Writes directly to online database.
"""
import os
import sys
import time
import logging

import yfinance as yf
import pandas as pd

# Add project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import execute_many, get_online_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Theme 16 US tickers + extended mapping peers
US_TICKERS = [
    'MSFT', 'NOW', 'ADSK', 'SNPS', 'ORCL', 'SAP', 'CRM', 'DDOG',
    'SNOW', 'CRWD', 'PLTR', 'WDAY', 'FIS', 'PATH', 'ADBE', 'CDNS',
    'ACN', 'CTSH', 'APP',
]

TICKER_NAMES = {
    'MSFT': 'Microsoft', 'NOW': 'ServiceNow', 'ADSK': 'Autodesk',
    'SNPS': 'Synopsys', 'ORCL': 'Oracle', 'SAP': 'SAP',
    'CRM': 'Salesforce', 'DDOG': 'Datadog', 'SNOW': 'Snowflake',
    'CRWD': 'CrowdStrike', 'PLTR': 'Palantir', 'WDAY': 'Workday',
    'FIS': 'FIS Global', 'PATH': 'UiPath', 'ADBE': 'Adobe',
    'CDNS': 'Cadence', 'ACN': 'Accenture', 'CTSH': 'Cognizant',
    'APP': 'AppLovin',
}


def sync_us_daily(tickers=None, period='6mo'):
    """Fetch US stock daily OHLCV and write to trade_us_daily."""
    tickers = tickers or US_TICKERS
    logger.info("Fetching %d US tickers, period=%s", len(tickers), period)

    data = yf.download(
        tickers=tickers,
        period=period,
        interval='1d',
        group_by='ticker',
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    total_rows = 0
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = data
            else:
                df = data[ticker] if ticker in data else None

            if df is None or df.empty:
                logger.warning("No data for %s", ticker)
                continue

            rows = []
            for idx, row in df.iterrows():
                c = row.get('Close')
                if c is not None and not pd.isna(c):
                    rows.append((
                        ticker,
                        idx.strftime('%Y-%m-%d'),
                        round(float(row['Open']), 4) if not pd.isna(row['Open']) else None,
                        round(float(row['High']), 4) if not pd.isna(row['High']) else None,
                        round(float(row['Low']), 4) if not pd.isna(row['Low']) else None,
                        round(float(c), 4),
                        int(row['Volume']) if not pd.isna(row['Volume']) else None,
                        None,  # amount
                    ))

            if rows:
                sql = """
                    INSERT INTO trade_us_daily
                        (stock_code, trade_date, open_price, high_price, low_price, close_price, volume, amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        open_price=VALUES(open_price), high_price=VALUES(high_price),
                        low_price=VALUES(low_price), close_price=VALUES(close_price),
                        volume=VALUES(volume)
                """
                execute_many(sql, rows, env='online')
                total_rows += len(rows)
                name = TICKER_NAMES.get(ticker, ticker)
                logger.info("  %s (%s): %d rows, latest=%.2f",
                            ticker, name, len(rows), float(rows[-1][5]))
        except Exception as e:
            logger.error("Failed for %s: %s", ticker, e)

    logger.info("Done. Total %d rows written.", total_rows)
    return total_rows


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', nargs='+', help='Specific tickers to sync')
    parser.add_argument('--period', default='6mo', help='yfinance period (e.g. 3mo, 1y)')
    args = parser.parse_args()

    os.environ['DB_ENV'] = 'online'
    sync_us_daily(tickers=args.tickers, period=args.period)
