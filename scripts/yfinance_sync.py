#!/usr/bin/env python3
"""
yfinance 本机抓取 -> 线上数据库同步脚本

背景: 阿里云 ECS 服务器访问 Yahoo Finance 会被限流/封 IP，
因此需要从本机 (macOS) 抓取 yfinance 数据，直接写入线上 MySQL。

用法:
    # 同步所有 yfinance 指标 (全球资产 + A股指数)
    DB_ENV=online python scripts/yfinance_sync.py

    # 只同步指定指标
    DB_ENV=online python scripts/yfinance_sync.py --indicators ovx vix gvz

    # 同步最近 N 天 (默认 7)
    DB_ENV=online python scripts/yfinance_sync.py --days 30

定时执行:
    crontab -e
    # 每日 07:30 同步 (美股收盘后, A股开盘前)
    30 7 * * 1-5 cd /Users/wenwen/data0/person/myTrader && DB_ENV=online /usr/bin/python3 scripts/yfinance_sync.py >> output/yfinance_sync.log 2>&1
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

from config.db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

# ============================================================
# yfinance 指标注册表
# indicator_name -> yfinance ticker
# ============================================================

# 全球资产 (与 macro_fetcher.py 注册表保持一致)
GLOBAL_ASSETS = {
    'btc':       'BTC-USD',
    'brent_oil': 'BZ=F',
    'spy':       'SPY',
    'qqq':       'QQQ',
    'dia':       'DIA',
    'vix':       '^VIX',
    'gvz':       '^GVZ',
    'ovx':       '^OVX',
    'dxy':       'DX-Y.NYB',
    'usdcny':    'CNY=X',
    'spgsci':    '^SPGSCI',
    # GSCI 子指数
    'spgsci_energy':    '^SPGSENTR',
    'spgsci_pm':        '^SPGSPM',
    'spgsci_ag':        '^SPGSAG',
    'spgsci_livestock': '^SPGSLV',
    'spgsci_softs':     '^SPGSSO',
    # 单品种期货（补充品种，黄金/原油已有）
    'nat_gas':  'NG=F',
    'copper':   'HG=F',
    'silver':   'SI=F',
    'wheat':    'ZW=F',
    'corn':     'ZC=F',
    'soybean':  'ZS=F',
}

# A 股指数 (yfinance .SS 后缀 = 上交所)
A_SHARE_INDICES = {
    'idx_all_a':      '000985.SS',
    'idx_sse':        '000001.SS',
    'idx_csi300':     '000300.SS',
    'idx_csi500':     '000905.SS',
}

ALL_INDICATORS = {**GLOBAL_ASSETS, **A_SHARE_INDICES}

INSERT_SQL = """
    INSERT INTO macro_data (date, indicator, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value)
"""


def fetch_and_save(indicator: str, ticker: str, start_date: str, conn) -> int:
    """拉取单个 yfinance 指标并写入数据库, 返回写入行数"""
    try:
        t = yf.Ticker(ticker)
        df = t.history(start=start_date, auto_adjust=True)
        if df is None or df.empty:
            logger.warning('[%s] %s returned empty', indicator, ticker)
            return 0

        df = df.reset_index()
        cursor = conn.cursor()
        cnt = 0
        for _, row in df.iterrows():
            d = pd.to_datetime(row['Date']).date()
            v = float(row['Close'])
            # A 股指数校验: 排除明显的 PE 数据 (< 100)
            if indicator in A_SHARE_INDICES and v < 100:
                continue
            cursor.execute(INSERT_SQL, (d, indicator, round(v, 4)))
            cnt += 1
        conn.commit()
        cursor.close()

        latest_val = df['Close'].iloc[-1]
        latest_date = pd.to_datetime(df['Date'].iloc[-1]).strftime('%Y-%m-%d')
        logger.info('[OK] %s: %d rows, latest %s = %.4f',
                     indicator, cnt, latest_date, latest_val)
        return cnt
    except Exception as e:
        logger.error('[FAIL] %s (%s): %s', indicator, ticker, e)
        return 0


def main():
    if not HAS_YFINANCE:
        logger.error('yfinance not installed, run: pip install yfinance')
        sys.exit(1)

    parser = argparse.ArgumentParser(description='yfinance -> online DB sync')
    parser.add_argument('--indicators', nargs='+', default=None,
                        help='Only sync these indicators (default: all)')
    parser.add_argument('--days', type=int, default=7,
                        help='Sync recent N days (default: 7)')
    args = parser.parse_args()

    start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    targets = args.indicators or list(ALL_INDICATORS.keys())

    # 过滤无效指标
    targets = [t for t in targets if t in ALL_INDICATORS]
    if not targets:
        logger.error('No valid indicators to sync')
        sys.exit(1)

    logger.info('Syncing %d indicators from %s, DB_ENV=%s',
                len(targets), start_date, os.getenv('DB_ENV', 'local'))

    conn = get_connection()
    total_rows = 0
    success = 0
    failed = 0

    for indicator in targets:
        ticker = ALL_INDICATORS[indicator]
        cnt = fetch_and_save(indicator, ticker, start_date, conn)
        total_rows += cnt
        if cnt > 0:
            success += 1
        else:
            failed += 1
        # yfinance 限流保护: 每个请求间隔 1 秒
        time.sleep(1)

    conn.close()
    logger.info('Done: %d/%d success, %d rows written',
                success, len(targets), total_rows)


if __name__ == '__main__':
    main()
