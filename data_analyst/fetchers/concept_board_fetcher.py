# -*- coding: utf-8 -*-
"""
概念板块成员每日同步任务 (多源)

数据源优先级:
    1. Tushare (需 2000+ 积分, 最全最稳定)
    2. 东方财富 push2 HTTP 直连 (绕过 AKShare, ~600 概念)
    3. 同花顺概念板块 (免费, ~375 概念, 每个概念仅第一页约10只)

功能:
    1. 获取全部概念板块列表
    2. 逐板块获取成分股
    3. 批量 upsert 到 stock_concept_map 表

表结构:
    stock_concept_map(stock_code, stock_name, concept_name, source, updated_at)
    唯一键: (stock_code, concept_name)

用法:
    python -m data_analyst.fetchers.concept_board_fetcher
    python -m data_analyst.fetchers.concept_board_fetcher --source ths   # 强制同花顺
    python -m data_analyst.fetchers.concept_board_fetcher --source tushare
    python -m data_analyst.fetchers.concept_board_fetcher --limit 20    # 测试
"""
import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_many

logger = logging.getLogger('myTrader.concept_board_fetcher')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS stock_concept_map (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    stock_code  VARCHAR(12) NOT NULL COMMENT '股票代码 (带后缀, e.g. 600519.SH)',
    stock_name  VARCHAR(50) NOT NULL COMMENT '股票名称',
    concept_name VARCHAR(100) NOT NULL COMMENT '概念板块名称',
    source      VARCHAR(20) NOT NULL DEFAULT 'em' COMMENT '数据源: em/tushare/ths',
    updated_at  DATETIME NOT NULL COMMENT '最近同步时间',
    UNIQUE KEY uk_stock_concept (stock_code, concept_name),
    INDEX ix_concept_name (concept_name),
    INDEX ix_stock_code (stock_code),
    INDEX ix_source (source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='概念板块成员同步表';
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_proxy():
    """清除代理环境变量, 避免代理干扰连接."""
    for k in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
              'all_proxy', 'ALL_PROXY'):
        os.environ.pop(k, None)


def _normalize_code(code: str) -> Optional[str]:
    """Convert 6-digit code string to exchange-suffixed format."""
    code = str(code).strip().zfill(6)
    code = re.sub(r'[^0-9]', '', code).zfill(6)
    if not code:
        return None
    if code.startswith(('0', '3')):
        return f"{code}.SZ"
    elif code.startswith(('6', '9')):
        return f"{code}.SH"
    elif code.startswith(('4', '8')):
        return f"{code}.BJ"
    return f"{code}.SZ"


def _em_http_get(url: str, retries: int = 2) -> Optional[dict]:
    """东方财富 push2 HTTP 直连请求."""
    _clear_proxy()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://data.eastmoney.com/',
    }
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            return None


# ---------------------------------------------------------------------------
# Source 1: Tushare (需 2000+ 积分)
# ---------------------------------------------------------------------------

def tushare_fetch_all_boards() -> list[dict]:
    """Return all concept boards from Tushare.
    Returns: [{'code': 'TK0001', 'name': '白酒'}, ...]
    """
    _clear_proxy()
    try:
        import tushare as ts
        from dotenv import load_dotenv
        load_dotenv()
        token = os.getenv('TUSHARE_TOKEN')
        if not token:
            logger.error('[Tushare] TUSHARE_TOKEN not set')
            return []
        pro = ts.pro_api(token)
        df = pro.concept(fields='code,name')
        boards = []
        for _, row in df.iterrows():
            boards.append({
                'code': str(row.get('code', '')),
                'name': str(row.get('name', '')).strip(),
            })
        logger.info('[Tushare] Total concept boards: %d', len(boards))
        return boards
    except Exception as e:
        logger.error('[Tushare] fetch_all_boards failed: %s', e)
        return []


def tushare_fetch_board_members(board_code: str) -> list[dict]:
    """Return members of one Tushare concept board.
    Returns: [{'stock_code': '600519.SH', 'stock_name': '贵州茅台'}, ...]
    """
    _clear_proxy()
    try:
        import tushare as ts
        from dotenv import load_dotenv
        load_dotenv()
        token = os.getenv('TUSHARE_TOKEN')
        pro = ts.pro_api(token)
        df = pro.concept_detail(id=board_code, fields='ts_code,name')
        members = []
        for _, row in df.iterrows():
            ts_code = str(row.get('ts_code', ''))
            # ts_code format: 600519.SH
            code = ts_code.split('.')[0] if '.' in ts_code else ts_code
            normalized = _normalize_code(code)
            name = str(row.get('name', '')).strip()
            if normalized and name:
                members.append({'stock_code': normalized, 'stock_name': name})
        return members
    except Exception as e:
        logger.warning('[Tushare] fetch_board_members(%s) failed: %s', board_code, e)
        return []


def tushare_test_connectivity() -> bool:
    """Test if Tushare concept API is available (has permission)."""
    _clear_proxy()
    try:
        import tushare as ts
        from dotenv import load_dotenv
        load_dotenv()
        token = os.getenv('TUSHARE_TOKEN')
        if not token:
            return False
        pro = ts.pro_api(token)
        df = pro.concept(fields='code,name')
        return len(df) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Source 2: 东方财富 push2 HTTP 直连
# ---------------------------------------------------------------------------

_EM_BOARD_LIST_URL = (
    'https://79.push2.eastmoney.com/api/qt/clist/get'
    '?pn={pn}&pz={pz}&po=1&np=1'
    '&ut=bd1d9ddb04089700cf9c27f6f7426281'
    '&fltt=2&invt=2&fid=f3'
    '&fs=m:90+t:3+f:!50'
    '&fields=f12,f14'
)


def em_fetch_all_boards() -> list[dict]:
    """Return all concept boards from Eastmoney push2 HTTP."""
    boards = []
    pn = 1
    pz = 500
    while True:
        url = _EM_BOARD_LIST_URL.format(pn=pn, pz=pz)
        data = _em_http_get(url)
        if not data:
            break
        diff = data.get('data', {}).get('diff', [])
        if not diff:
            break
        for item in diff:
            boards.append({'code': item.get('f12', ''), 'name': item.get('f14', '')})
        if len(diff) < pz:
            break
        pn += 1
    logger.info('[EM] Total concept boards: %d', len(boards))
    return boards


def em_fetch_board_members(board_code: str, board_name: str) -> list[dict]:
    """Return members of one EM concept board."""
    members = []
    pn = 1
    pz = 500
    while True:
        url = (
            f'https://29.push2.eastmoney.com/api/qt/clist/get'
            f'?pn={pn}&pz={pz}&po=1&np=1'
            f'&ut=bd1d9ddb04089700cf9c27f6f7426281'
            f'&fltt=2&invt=2&fid=f12'
            f'&fs=b:{board_code}+f:!50'
            f'&fields=f12,f14'
        )
        data = _em_http_get(url)
        if not data:
            break
        diff = data.get('data', {}).get('diff', [])
        if not diff:
            break
        for item in diff:
            code = _normalize_code(str(item.get('f12', '')))
            name = str(item.get('f14', '')).strip()
            if code and name:
                members.append({'stock_code': code, 'stock_name': name})
        if len(diff) < pz:
            break
        pn += 1
    return members


def em_test_connectivity() -> bool:
    """Test if Eastmoney push2 is reachable."""
    url = _EM_BOARD_LIST_URL.format(pn=1, pz=1)
    data = _em_http_get(url)
    return data is not None and data.get('data', {}).get('diff') is not None


# ---------------------------------------------------------------------------
# Source 3: 同花顺概念板块 (免费, 第一页 ~10 只/概念)
# ---------------------------------------------------------------------------

def ths_fetch_all_boards() -> list[dict]:
    """Return all concept boards from THS via AKShare."""
    _clear_proxy()
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_ths()
        boards = []
        for _, row in df.iterrows():
            boards.append({
                'code': str(row.get('code', '')),
                'name': str(row.get('name', '')).strip(),
            })
        logger.info('[THS] Total concept boards: %d', len(boards))
        return boards
    except Exception as e:
        logger.error('[THS] fetch_all_boards failed: %s', e)
        return []


def ths_fetch_board_members(board_code: str) -> list[dict]:
    """Fetch members of one THS concept board (first page only, ~10 stocks).
    Uses requests with GBK encoding for correct Chinese text.
    """
    _clear_proxy()
    try:
        import requests as req_lib
        from bs4 import BeautifulSoup

        s = req_lib.Session()
        s.trust_env = False
        url = f'https://q.10jqka.com.cn/gn/detail/code/{board_code}/'
        r = s.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        })
        r.encoding = 'gbk'
        soup = BeautifulSoup(r.text, 'lxml')
        table = soup.find('table', class_='m-table')
        if not table:
            return []

        members = []
        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 3:
                raw_code = cells[1].get_text(strip=True)
                raw_name = cells[2].get_text(strip=True)
                code = _normalize_code(raw_code)
                if code and raw_name:
                    members.append({'stock_code': code, 'stock_name': raw_name})
        return members
    except Exception as e:
        logger.warning('[THS] fetch_board_members(%s) failed: %s', board_code, e)
        return []


def ths_test_connectivity() -> bool:
    """Test if THS concept API is reachable."""
    _clear_proxy()
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_ths()
        return len(df) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_concept_members(rows: list[dict]) -> int:
    """Upsert rows into stock_concept_map. Returns number of rows affected."""
    if not rows:
        return 0
    sql = """
        INSERT INTO stock_concept_map (stock_code, stock_name, concept_name, source, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name = VALUES(stock_name),
            source = VALUES(source),
            updated_at = VALUES(updated_at)
    """
    params = [(r['stock_code'], r['stock_name'], r['concept_name'], r['source'], r['updated_at']) for r in rows]
    execute_many(sql, params, env='online')
    return len(params)


def ensure_table():
    """Ensure stock_concept_map table exists."""
    try:
        execute_query(_CREATE_TABLE_SQL, env='online')
        logger.info('[ConceptFetcher] Table stock_concept_map ready.')
    except Exception as e:
        logger.error('[ConceptFetcher] Failed to create table: %s', e)


# ---------------------------------------------------------------------------
# Source auto-detection
# ---------------------------------------------------------------------------

_SOURCE_CONFIG = {
    'tushare': {
        'test': tushare_test_connectivity,
        'fetch_boards': tushare_fetch_all_boards,
        'fetch_members': tushare_fetch_board_members,
        'label': 'Tushare (2000+ points)',
    },
    'em': {
        'test': em_test_connectivity,
        'fetch_boards': em_fetch_all_boards,
        'fetch_members': em_fetch_board_members,
        'label': 'Eastmoney (push2 HTTP)',
    },
    'ths': {
        'test': ths_test_connectivity,
        'fetch_boards': ths_fetch_all_boards,
        'fetch_members': ths_fetch_board_members,
        'label': 'THS (first page only)',
    },
}


def detect_source(force_source: Optional[str] = None) -> str:
    """Detect best available source. Priority: tushare > em > ths."""
    if force_source:
        if force_source in _SOURCE_CONFIG:
            return force_source
        raise ValueError(f'Unknown source: {force_source}, valid: {list(_SOURCE_CONFIG.keys())}')

    for source_id, cfg in _SOURCE_CONFIG.items():
        label = cfg['label']
        logger.info('[ConceptFetcher] Testing %s...', label)
        if cfg['test']():
            logger.info('[ConceptFetcher] Using source: %s', label)
            return source_id
        logger.info('[ConceptFetcher] %s not available.', label)

    raise RuntimeError('[ConceptFetcher] No data source available!')


# ---------------------------------------------------------------------------
# Main sync
# ---------------------------------------------------------------------------

def run_sync(limit: Optional[int] = None, sleep_between: float = 0.3,
             force_source: Optional[str] = None) -> dict:
    """
    Full sync: detect source -> fetch all boards -> per-board members -> upsert.

    Args:
        limit: Only sync first N boards (for testing).
        sleep_between: Seconds to sleep between board requests.
        force_source: 'tushare', 'em', or 'ths'. Skip auto-detection.

    Returns:
        summary dict with source, board_count, stock_count, error_count.
    """
    ensure_table()
    source = detect_source(force_source)
    cfg = _SOURCE_CONFIG[source]

    boards = cfg['fetch_boards']()
    if not boards:
        logger.error('[ConceptFetcher] No boards returned, aborting.')
        return {'source': source, 'board_count': 0, 'stock_count': 0, 'error_count': 0}

    if limit:
        boards = boards[:limit]
        logger.info('[ConceptFetcher] Limited to first %d boards.', limit)

    now = datetime.utcnow()
    total_stocks = 0
    error_count = 0
    batch_size = 200

    for i, board in enumerate(boards, 1):
        board_code = board['code']
        board_name = board['name']
        logger.info('[ConceptFetcher] [%d/%d] %s (%s)', i, len(boards), board_name, board_code)

        if source == 'em':
            members = cfg['fetch_members'](board_code, board_name)
        else:
            members = cfg['fetch_members'](board_code)

        if not members:
            error_count += 1
            time.sleep(sleep_between)
            continue

        rows = [
            {
                'stock_code': m['stock_code'],
                'stock_name': m['stock_name'],
                'concept_name': board_name,
                'source': source,
                'updated_at': now,
            }
            for m in members
        ]

        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            try:
                total_stocks += upsert_concept_members(batch)
            except Exception as e:
                logger.error('[ConceptFetcher] upsert failed for %s: %s', board_name, e)
                error_count += 1

        time.sleep(sleep_between)

    summary = {
        'source': source,
        'board_count': len(boards),
        'stock_count': total_stocks,
        'error_count': error_count,
    }
    logger.info('[ConceptFetcher] Sync done: source=%s boards=%d stocks=%d errors=%d',
                summary['source'], summary['board_count'],
                summary['stock_count'], summary['error_count'])
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='概念板块成员每日同步 (多源)')
    parser.add_argument('--limit', type=int, default=None, help='Only sync first N boards (testing)')
    parser.add_argument('--sleep', type=float, default=0.3, help='Sleep between board requests (default 0.3s)')
    parser.add_argument('--source', type=str, default=None, choices=['tushare', 'em', 'ths'],
                        help='Force data source: tushare/em/ths')
    args = parser.parse_args()

    result = run_sync(limit=args.limit, sleep_between=args.sleep, force_source=args.source)
    print(f"Done: {result}")
