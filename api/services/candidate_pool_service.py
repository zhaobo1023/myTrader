# -*- coding: utf-8 -*-
"""
Candidate Pool Service

Handles:
- CRUD for candidate_pool_stocks
- Industry stock screening (query RPS + tech from DB)
- Daily monitoring data query
- Feishu push notification
"""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import requests

from config.db import execute_query, execute_update, execute_many
from config.settings import CURRENT_ENV, FEISHU_WEBHOOK_URL

logger = logging.getLogger('myTrader.candidate_pool')

_DB_ENV = CURRENT_ENV

FEISHU_WEBHOOK = FEISHU_WEBHOOK_URL

ALERT_COLORS = {
    'red': '#e5534b',
    'yellow': '#c69026',
    'green': '#27a644',
    'info': '#6e7681',
}

ALERT_LABELS = {
    'red': '[RED]',
    'yellow': '[YELLOW]',
    'green': '[GREEN]',
    'info': '[INFO]',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().strftime('%Y-%m-%d')


def _latest_trade_date() -> str:
    rows = execute_query(
        'SELECT MAX(trade_date) AS d FROM trade_stock_rps', env=_DB_ENV
    )
    if rows and rows[0]['d']:
        return str(rows[0]['d'])
    return _today()


# ---------------------------------------------------------------------------
# Tag CRUD
# ---------------------------------------------------------------------------

def list_tags(user_id: int) -> list:
    """Return all tags for a user, with stock count."""
    rows = execute_query(
        '''SELECT t.id, t.name, t.color, t.created_at,
                  (SELECT COUNT(*) FROM candidate_stock_tags st WHERE st.tag_id = t.id) AS stock_count
           FROM candidate_tags t
           WHERE t.user_id = %s
           ORDER BY t.created_at DESC''',
        (user_id,), env=_DB_ENV,
    )
    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'name': r['name'],
            'color': r['color'],
            'stock_count': int(r['stock_count']),
            'created_at': str(r['created_at']) if r.get('created_at') else None,
        })
    return result


def create_tag(user_id: int, name: str, color: str = '#5e6ad2') -> dict:
    """Create a new tag for user. Returns tag dict."""
    existing = execute_query(
        'SELECT id FROM candidate_tags WHERE user_id = %s AND name = %s',
        (user_id, name), env=_DB_ENV,
    )
    if existing:
        return {'id': existing[0]['id'], 'name': name, 'color': color, 'action': 'exists'}

    execute_update(
        '''INSERT INTO candidate_tags (user_id, name, color, created_at)
           VALUES (%s, %s, %s, NOW())''',
        (user_id, name, color), env=_DB_ENV,
    )
    rows = execute_query(
        'SELECT id FROM candidate_tags WHERE user_id = %s AND name = %s',
        (user_id, name), env=_DB_ENV,
    )
    return {'id': rows[0]['id'], 'name': name, 'color': color, 'action': 'created'}


def delete_tag(user_id: int, tag_id: int) -> bool:
    """Delete a tag and all its associations."""
    execute_update(
        'DELETE FROM candidate_stock_tags WHERE tag_id = %s',
        (tag_id,), env=_DB_ENV,
    )
    execute_update(
        'DELETE FROM candidate_tags WHERE id = %s AND user_id = %s',
        (tag_id, user_id), env=_DB_ENV,
    )
    return True


def tag_stock(user_id: int, stock_id: int, tag_id: int) -> bool:
    """Associate a tag with a stock. Validates ownership."""
    # Verify tag belongs to user
    tag = execute_query(
        'SELECT id FROM candidate_tags WHERE id = %s AND user_id = %s',
        (tag_id, user_id), env=_DB_ENV,
    )
    if not tag:
        return False
    # Verify stock belongs to user
    stock = execute_query(
        'SELECT id FROM candidate_pool_stocks WHERE id = %s AND user_id = %s',
        (stock_id, user_id), env=_DB_ENV,
    )
    if not stock:
        return False
    execute_update(
        '''INSERT INTO candidate_stock_tags (stock_id, tag_id, created_at)
           VALUES (%s, %s, NOW())
           ON DUPLICATE KEY UPDATE stock_id=stock_id''',
        (stock_id, tag_id), env=_DB_ENV,
    )
    return True


def untag_stock(user_id: int, stock_id: int, tag_id: int) -> bool:
    """Remove a tag from a stock."""
    execute_update(
        'DELETE st FROM candidate_stock_tags st '
        'INNER JOIN candidate_tags t ON st.tag_id = t.id '
        'WHERE st.stock_id = %s AND st.tag_id = %s AND t.user_id = %s',
        (stock_id, tag_id, user_id), env=_DB_ENV,
    )
    return True


def get_stock_tags(stock_id: int) -> list:
    """Get all tags for a stock."""
    rows = execute_query(
        '''SELECT t.id, t.name, t.color
           FROM candidate_tags t
           INNER JOIN candidate_stock_tags st ON st.tag_id = t.id
           WHERE st.stock_id = %s
           ORDER BY t.name''',
        (stock_id,), env=_DB_ENV,
    )
    return [{'id': r['id'], 'name': r['name'], 'color': r['color']} for r in rows]


def list_stocks_with_tags(user_id: int, tag_id: Optional[int] = None, **kwargs) -> list:
    """List stocks optionally filtered by tag."""
    stocks = list_stocks(user_id, **kwargs)
    if not stocks:
        return stocks

    stock_ids = [s['id'] for s in stocks]

    # Batch load tags for all stocks
    CHUNK = 200
    tag_map = {}
    for i in range(0, len(stock_ids), CHUNK):
        chunk = stock_ids[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'''SELECT st.stock_id, t.id AS tag_id, t.name, t.color
                FROM candidate_stock_tags st
                INNER JOIN candidate_tags t ON st.tag_id = t.id
                WHERE st.stock_id IN ({ph})
                ORDER BY t.name''',
            tuple(chunk), env=_DB_ENV,
        )
        for r in rows:
            sid = r['stock_id']
            if sid not in tag_map:
                tag_map[sid] = []
            tag_map[sid].append({'id': r['tag_id'], 'name': r['name'], 'color': r['color']})

    # Filter by tag if specified
    if tag_id is not None:
        stocks = [s for s in stocks if any(t['id'] == tag_id for t in tag_map.get(s['id'], []))]

    # Attach tags to each stock
    for s in stocks:
        s['tags'] = tag_map.get(s['id'], [])

    return stocks


# ---------------------------------------------------------------------------
# Position stock tags (reuse candidate_tags, separate association table)
# ---------------------------------------------------------------------------

def tag_position(user_id: int, position_id: int, tag_id: int) -> bool:
    """Associate a tag with a position. Validates ownership."""
    tag = execute_query(
        'SELECT id FROM candidate_tags WHERE id = %s AND user_id = %s',
        (tag_id, user_id), env=_DB_ENV,
    )
    if not tag:
        return False
    execute_update(
        '''INSERT INTO position_stock_tags (position_id, tag_id, created_at)
           VALUES (%s, %s, NOW())
           ON DUPLICATE KEY UPDATE position_id=position_id''',
        (position_id, tag_id), env=_DB_ENV,
    )
    return True


def untag_position(user_id: int, position_id: int, tag_id: int) -> bool:
    """Remove a tag from a position."""
    execute_update(
        'DELETE pt FROM position_stock_tags pt '
        'INNER JOIN candidate_tags t ON pt.tag_id = t.id '
        'WHERE pt.position_id = %s AND pt.tag_id = %s AND t.user_id = %s',
        (position_id, tag_id, user_id), env=_DB_ENV,
    )
    return True


def get_position_tags(position_id: int) -> list:
    """Get all tags for a position."""
    rows = execute_query(
        '''SELECT t.id, t.name, t.color
           FROM candidate_tags t
           INNER JOIN position_stock_tags pt ON pt.tag_id = t.id
           WHERE pt.position_id = %s
           ORDER BY t.name''',
        (position_id,), env=_DB_ENV,
    )
    return [{'id': r['id'], 'name': r['name'], 'color': r['color']} for r in rows]


def get_all_position_tags(position_ids: list) -> dict:
    """Batch load tags for multiple positions. Returns {position_id: [tag_dicts]}."""
    if not position_ids:
        return {}
    tag_map = {}
    CHUNK = 200
    for i in range(0, len(position_ids), CHUNK):
        chunk = position_ids[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'''SELECT pt.position_id, t.id AS tag_id, t.name, t.color
                FROM position_stock_tags pt
                INNER JOIN candidate_tags t ON pt.tag_id = t.id
                WHERE pt.position_id IN ({ph})
                ORDER BY t.name''',
            tuple(chunk), env=_DB_ENV,
        )
        for r in rows:
            pid = r['position_id']
            if pid not in tag_map:
                tag_map[pid] = []
            tag_map[pid].append({'id': r['tag_id'], 'name': r['name'], 'color': r['color']})
    return tag_map


# ---------------------------------------------------------------------------
# Single stock refresh
# ---------------------------------------------------------------------------

def refresh_single_stock(stock_code: str, user_id: int) -> dict:
    """Refresh monitor data for a single stock and return updated info."""
    # Run full monitor to ensure data is fresh, then return just this stock
    run_daily_monitor()

    # Return updated stock data
    stocks = list_stocks_with_tags(user_id)
    for s in stocks:
        if s['stock_code'] == stock_code:
            return s
    return {}


# ---------------------------------------------------------------------------
# Candidate pool CRUD
# ---------------------------------------------------------------------------

def list_stocks(user_id: int = 0, status: Optional[str] = None, source_type: Optional[str] = None) -> list:
    """Return all candidate pool stocks with latest monitor snapshot."""
    where = ['c.user_id = %s']
    params = [user_id]
    if status:
        where.append('c.status = %s')
        params.append(status)
    if source_type:
        where.append('c.source_type = %s')
        params.append(source_type)

    where_sql = 'WHERE ' + ' AND '.join(where)

    sql = f"""
        SELECT
            c.id, c.stock_code, c.stock_name,
            c.source_type, c.source_detail,
            c.entry_snapshot, c.add_date, c.status, c.memo,
            c.created_at,
            m.trade_date AS monitor_date,
            m.close, m.rps_250, m.rps_120, m.rps_20, m.rps_slope,
            m.ma20, m.ma60, m.ma250, m.volume_ratio, m.rsi,
            m.pct_since_add, m.rps_change,
            m.signals AS monitor_signals,
            m.alert_level
        FROM candidate_pool_stocks c
        LEFT JOIN candidate_monitor_daily m
            ON c.stock_code = m.stock_code
            AND m.trade_date = (
                SELECT MAX(trade_date) FROM candidate_monitor_daily
                WHERE stock_code = c.stock_code
            )
        {where_sql}
        ORDER BY
            FIELD(c.status, 'focused', 'watching', 'excluded'),
            COALESCE(m.alert_level, 'info'),
            c.add_date DESC
    """
    rows = execute_query(sql, tuple(params) if params else None, env=_DB_ENV)

    result = []
    for r in rows:
        snap = {}
        if r.get('entry_snapshot'):
            try:
                snap = json.loads(r['entry_snapshot'])
            except Exception:
                pass

        signals = []
        if r.get('monitor_signals'):
            try:
                signals = json.loads(r['monitor_signals'])
            except Exception:
                pass

        result.append({
            'id': r['id'],
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'source_type': r['source_type'],
            'source_detail': r['source_detail'],
            'add_date': str(r['add_date']) if r['add_date'] else None,
            'status': r['status'],
            'memo': r['memo'],
            'entry_snapshot': snap,
            # latest monitor
            'monitor_date': str(r['monitor_date']) if r.get('monitor_date') else None,
            'close': float(r['close']) if r.get('close') is not None else None,
            'rps_250': float(r['rps_250']) if r.get('rps_250') is not None else None,
            'rps_120': float(r['rps_120']) if r.get('rps_120') is not None else None,
            'rps_slope': float(r['rps_slope']) if r.get('rps_slope') is not None else None,
            'pct_since_add': float(r['pct_since_add']) if r.get('pct_since_add') is not None else None,
            'rps_change': float(r['rps_change']) if r.get('rps_change') is not None else None,
            'signals': signals,
            'alert_level': r.get('alert_level') or 'info',
        })
    return result


def add_stock(
    user_id: int,
    stock_code: str,
    stock_name: str,
    source_type: str,
    source_detail: Optional[str],
    entry_snapshot: Optional[dict],
    memo: Optional[str],
) -> dict:
    """Add a stock to the candidate pool. If already exists, update snapshot."""
    today = _today()
    snap_json = json.dumps(entry_snapshot or {}, ensure_ascii=False)

    # Check if already in pool for this user
    existing = execute_query(
        'SELECT id, status FROM candidate_pool_stocks WHERE user_id = %s AND stock_code = %s',
        (user_id, stock_code), env=_DB_ENV,
    )
    if existing:
        row = existing[0]
        execute_update(
            '''UPDATE candidate_pool_stocks
               SET stock_name=%s, source_type=%s, source_detail=%s,
                   entry_snapshot=%s, add_date=%s, status='watching',
                   memo=%s, updated_at=NOW()
               WHERE user_id=%s AND stock_code=%s''',
            (stock_name, source_type, source_detail, snap_json, today, memo, user_id, stock_code),
            env=_DB_ENV,
        )
        return {'action': 'updated', 'stock_code': stock_code, 'id': row['id']}

    execute_update(
        '''INSERT INTO candidate_pool_stocks
           (user_id, stock_code, stock_name, source_type, source_detail,
            entry_snapshot, add_date, status, memo, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'watching', %s, NOW(), NOW())''',
        (user_id, stock_code, stock_name, source_type, source_detail, snap_json, today, memo),
        env=_DB_ENV,
    )
    rows = execute_query(
        'SELECT id FROM candidate_pool_stocks WHERE user_id = %s AND stock_code = %s',
        (user_id, stock_code), env=_DB_ENV,
    )
    new_id = rows[0]['id'] if rows else None
    return {'action': 'added', 'stock_code': stock_code, 'id': new_id}


def update_stock(user_id: int, stock_code: str, status: Optional[str] = None, memo: Optional[str] = None) -> bool:
    set_parts = ['updated_at=NOW()']
    params = []
    if status is not None:
        set_parts.append('status=%s')
        params.append(status)
    if memo is not None:
        set_parts.append('memo=%s')
        params.append(memo)
    params.extend([user_id, stock_code])
    execute_update(
        f'UPDATE candidate_pool_stocks SET {", ".join(set_parts)} WHERE user_id=%s AND stock_code=%s',
        tuple(params), env=_DB_ENV,
    )
    return True


def list_memos_by_user(user_id: int, stock_code: str) -> list:
    """Return all memos for a user's candidate stock, newest first."""
    rows = execute_query(
        '''SELECT m.id, m.content, m.created_at
           FROM candidate_pool_memos m
           JOIN candidate_pool_stocks s ON s.id = m.candidate_stock_id
           WHERE s.user_id = %s AND s.stock_code = %s
           ORDER BY m.created_at DESC''',
        (user_id, stock_code), env=_DB_ENV,
    )
    return [
        {'id': r['id'], 'content': r['content'], 'created_at': str(r['created_at'])}
        for r in rows
    ]


def list_memos(candidate_stock_id: int) -> list:
    """Return all memos for a candidate stock, newest first."""
    rows = execute_query(
        'SELECT id, content, created_at FROM candidate_pool_memos WHERE candidate_stock_id = %s ORDER BY created_at DESC',
        (candidate_stock_id,), env=_DB_ENV,
    )
    return [
        {'id': r['id'], 'content': r['content'], 'created_at': str(r['created_at'])}
        for r in rows
    ]


def add_memo(user_id: int, stock_code: str, content: str) -> dict:
    """Add a memo entry. Returns the new memo dict."""
    rows = execute_query(
        'SELECT id FROM candidate_pool_stocks WHERE user_id = %s AND stock_code = %s',
        (user_id, stock_code), env=_DB_ENV,
    )
    if not rows:
        raise ValueError(f'Stock {stock_code} not found in candidate pool for user {user_id}')
    candidate_stock_id = rows[0]['id']
    execute_update(
        'INSERT INTO candidate_pool_memos (candidate_stock_id, content, created_at) VALUES (%s, %s, NOW())',
        (candidate_stock_id, content), env=_DB_ENV,
    )
    new_row = execute_query(
        'SELECT id, content, created_at FROM candidate_pool_memos WHERE candidate_stock_id = %s ORDER BY id DESC LIMIT 1',
        (candidate_stock_id,), env=_DB_ENV,
    )
    r = new_row[0]
    return {'id': r['id'], 'content': r['content'], 'created_at': str(r['created_at'])}


def delete_memo(user_id: int, stock_code: str, memo_id: int) -> bool:
    """Delete a memo. Verifies ownership via candidate_pool_stocks."""
    rows = execute_query(
        'SELECT id FROM candidate_pool_stocks WHERE user_id = %s AND stock_code = %s',
        (user_id, stock_code), env=_DB_ENV,
    )
    if not rows:
        return False
    candidate_stock_id = rows[0]['id']
    execute_update(
        'DELETE FROM candidate_pool_memos WHERE id = %s AND candidate_stock_id = %s',
        (memo_id, candidate_stock_id), env=_DB_ENV,
    )
    return True


def remove_stock(user_id: int, stock_code: str) -> bool:
    # Remove tag associations and memos first
    rows = execute_query(
        'SELECT id FROM candidate_pool_stocks WHERE user_id = %s AND stock_code = %s',
        (user_id, stock_code), env=_DB_ENV,
    )
    if rows:
        stock_id = rows[0]['id']
        execute_update(
            'DELETE FROM candidate_stock_tags WHERE stock_id = %s',
            (stock_id,), env=_DB_ENV,
        )
        execute_update(
            'DELETE FROM candidate_pool_memos WHERE candidate_stock_id = %s',
            (stock_id,), env=_DB_ENV,
        )
    execute_update(
        'DELETE FROM candidate_pool_stocks WHERE user_id = %s AND stock_code = %s',
        (user_id, stock_code), env=_DB_ENV,
    )
    return True


def get_stock_history(stock_code: str, days: int = 30) -> list:
    rows = execute_query(
        '''SELECT trade_date, close, rps_250, rps_120, rps_slope,
                  pct_since_add, rps_change, signals, alert_level
           FROM candidate_monitor_daily
           WHERE stock_code = %s
           ORDER BY trade_date DESC
           LIMIT %s''',
        (stock_code, days), env=_DB_ENV,
    )
    result = []
    for r in rows:
        signals = []
        if r.get('signals'):
            try:
                signals = json.loads(r['signals'])
            except Exception:
                pass
        result.append({
            'trade_date': str(r['trade_date']),
            'close': float(r['close']) if r.get('close') is not None else None,
            'rps_250': float(r['rps_250']) if r.get('rps_250') is not None else None,
            'rps_120': float(r['rps_120']) if r.get('rps_120') is not None else None,
            'rps_slope': float(r['rps_slope']) if r.get('rps_slope') is not None else None,
            'pct_since_add': float(r['pct_since_add']) if r.get('pct_since_add') is not None else None,
            'rps_change': float(r['rps_change']) if r.get('rps_change') is not None else None,
            'signals': signals,
            'alert_level': r.get('alert_level') or 'info',
        })
    return result


# ---------------------------------------------------------------------------
# Industry stock screening
# ---------------------------------------------------------------------------

# SW L1 industry code mapping (name -> code)
# Populated lazily on first call to list_industries()
_SW_INDUSTRY_MAP: dict = {}  # {name: code}


def _load_sw_industry_map() -> dict:
    """Load SW L1 industry name->code map from AKShare. Cached in module."""
    global _SW_INDUSTRY_MAP
    if _SW_INDUSTRY_MAP:
        return _SW_INDUSTRY_MAP
    try:
        import akshare as ak
        df = ak.sw_index_first_info()
        # columns: ���业代码, 行业名称, ...
        for _, row in df.iterrows():
            code = str(row['行业代码']).replace('.SI', '').strip()
            name = str(row['行业名称']).strip()
            _SW_INDUSTRY_MAP[name] = code
        logger.info('Loaded %d SW L1 industries', len(_SW_INDUSTRY_MAP))
    except Exception as e:
        logger.warning('_load_sw_industry_map failed: %s', e)
    return _SW_INDUSTRY_MAP


def list_industries() -> list:
    """Return SW L1 industry names."""
    m = _load_sw_industry_map()
    return sorted(m.keys())


def get_industry_stocks(
    industry_name: str,
    min_rps: float = 0,
    sort_by: str = 'rps_250',
    limit: int = 100,
) -> list:
    """
    Return stocks in a given SW L1 industry with latest RPS + price data.
    Data source: AKShare index_component_sw + trade_stock_rps + trade_stock_daily
    """
    # Step 1: resolve industry code
    ind_map = _load_sw_industry_map()
    ind_code = ind_map.get(industry_name)
    if not ind_code:
        logger.warning('Unknown industry: %s', industry_name)
        return []

    # Step 2: get constituents from AKShare
    try:
        import akshare as ak
        df = ak.index_component_sw(symbol=ind_code)
        if df is None or df.empty:
            return []
        stocks = {}
        for _, row in df.iterrows():
            code = str(row['证券代码']).strip().zfill(6)
            name = str(row['证券名称']).strip()
            if code.startswith('6'):
                full_code = code + '.SH'
            elif code.startswith(('0', '3')):
                full_code = code + '.SZ'
            else:
                full_code = code
            stocks[full_code] = name
    except Exception as e:
        logger.warning('get_industry_stocks akshare failed: %s', e)
        return []

    if not stocks:
        return []

    # Step 2: fetch latest RPS for these stocks
    latest_date = _latest_trade_date()
    codes_list = list(stocks.keys())

    # batch query in chunks to avoid too-large IN clause
    CHUNK = 200
    rps_map = {}
    for i in range(0, len(codes_list), CHUNK):
        chunk = codes_list[i:i + CHUNK]
        placeholders = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'''SELECT stock_code, rps_20, rps_120, rps_250, rps_slope
                FROM trade_stock_rps
                WHERE stock_code IN ({placeholders}) AND trade_date = %s''',
            tuple(chunk) + (latest_date,), env=_DB_ENV,
        )
        for r in rows:
            rps_map[r['stock_code']] = r

    # Step 3: fetch latest close price
    price_map = {}
    for i in range(0, len(codes_list), CHUNK):
        chunk = codes_list[i:i + CHUNK]
        placeholders = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'''SELECT stock_code, close_price
                FROM trade_stock_daily
                WHERE stock_code IN ({placeholders}) AND trade_date = %s''',
            tuple(chunk) + (latest_date,), env=_DB_ENV,
        )
        for r in rows:
            price_map[r['stock_code']] = float(r['close_price']) if r.get('close_price') is not None else None

    # Step 4: check which are in candidate pool already
    pool_codes = set()
    existing = execute_query('SELECT stock_code FROM candidate_pool_stocks', env=_DB_ENV)
    for r in existing:
        pool_codes.add(r['stock_code'])

    # Step 5: assemble result
    result = []
    for code, name in stocks.items():
        rps = rps_map.get(code, {})
        rps_250 = float(rps['rps_250']) if rps.get('rps_250') is not None else None
        rps_120 = float(rps['rps_120']) if rps.get('rps_120') is not None else None
        rps_20 = float(rps['rps_20']) if rps.get('rps_20') is not None else None
        rps_slope = float(rps['rps_slope']) if rps.get('rps_slope') is not None else None

        if min_rps > 0 and (rps_250 is None or rps_250 < min_rps):
            continue

        result.append({
            'stock_code': code,
            'stock_name': name,
            'close': price_map.get(code),
            'rps_250': rps_250,
            'rps_120': rps_120,
            'rps_20': rps_20,
            'rps_slope': rps_slope,
            'in_pool': code in pool_codes,
            'trade_date': latest_date,
        })

    # sort
    valid_sorts = {'rps_250', 'rps_120', 'rps_20', 'rps_slope'}
    if sort_by not in valid_sorts:
        sort_by = 'rps_250'

    result.sort(key=lambda x: (x[sort_by] is None, -(x[sort_by] or 0)))
    return result[:limit]


# ---------------------------------------------------------------------------
# Daily monitoring
# ---------------------------------------------------------------------------

def run_daily_monitor(env: str = 'online') -> dict:
    """
    Compute daily tech snapshot for all candidate pool stocks and save to DB.
    Returns summary dict.
    """
    stocks = execute_query(
        'SELECT stock_code, stock_name, add_date, entry_snapshot FROM candidate_pool_stocks WHERE status != %s',
        ('excluded',), env=env,
    )
    if not stocks:
        return {'monitored': 0, 'alerts': {}}

    latest_date = _latest_trade_date()
    codes = [s['stock_code'] for s in stocks]
    CHUNK = 200

    # Fetch RPS
    rps_map = {}
    for i in range(0, len(codes), CHUNK):
        chunk = codes[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'SELECT stock_code, rps_20, rps_120, rps_250, rps_slope FROM trade_stock_rps WHERE stock_code IN ({ph}) AND trade_date=%s',
            tuple(chunk) + (latest_date,), env=env,
        )
        for r in rows:
            rps_map[r['stock_code']] = r

    # Fetch close price
    price_map = {}
    for i in range(0, len(codes), CHUNK):
        chunk = codes[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'SELECT stock_code, close_price FROM trade_stock_daily WHERE stock_code IN ({ph}) AND trade_date=%s',
            tuple(chunk) + (latest_date,), env=env,
        )
        for r in rows:
            price_map[r['stock_code']] = float(r['close_price']) if r.get('close_price') is not None else None

    # Fetch MA indicators (from trade_stock_factor or trade_stock_basic_factor)
    ma_map = {}
    for i in range(0, len(codes), CHUNK):
        chunk = codes[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        rows = execute_query(
            f'''SELECT stock_code, ma_20, ma_60, ma_250, rsi_14, volume_ratio,
                       macd_dif, macd_dea
                FROM trade_stock_factor
                WHERE stock_code IN ({ph}) AND trade_date=%s''',
            tuple(chunk) + (latest_date,), env=env,
        )
        for r in rows:
            ma_map[r['stock_code']] = r

    alert_counts = {'red': 0, 'yellow': 0, 'green': 0, 'info': 0}
    records = []

    for s in stocks:
        code = s['stock_code']
        rps = rps_map.get(code, {})
        ma = ma_map.get(code, {})
        close = price_map.get(code)

        rps_250 = float(rps['rps_250']) if rps.get('rps_250') is not None else None
        rps_120 = float(rps['rps_120']) if rps.get('rps_120') is not None else None
        rps_20 = float(rps['rps_20']) if rps.get('rps_20') is not None else None
        rps_slope = float(rps['rps_slope']) if rps.get('rps_slope') is not None else None

        ma20 = float(ma['ma_20']) if ma.get('ma_20') is not None else None
        ma60 = float(ma['ma_60']) if ma.get('ma_60') is not None else None
        ma250 = float(ma['ma_250']) if ma.get('ma_250') is not None else None
        rsi = float(ma['rsi_14']) if ma.get('rsi_14') is not None else None
        volume_ratio = float(ma['volume_ratio']) if ma.get('volume_ratio') is not None else None
        macd_dif = float(ma['macd_dif']) if ma.get('macd_dif') is not None else None
        macd_dea = float(ma['macd_dea']) if ma.get('macd_dea') is not None else None

        # Entry price from snapshot
        snap = {}
        if s.get('entry_snapshot'):
            try:
                snap = json.loads(s['entry_snapshot'])
            except Exception:
                pass
        entry_close = snap.get('close')
        entry_rps = snap.get('rps_250')

        pct_since_add = None
        if close is not None and entry_close:
            try:
                pct_since_add = round((close - float(entry_close)) / float(entry_close) * 100, 4)
            except Exception:
                pass

        rps_change = None
        if rps_250 is not None and entry_rps is not None:
            try:
                rps_change = round(rps_250 - float(entry_rps), 2)
            except Exception:
                pass

        # Signal generation
        signals = []
        alert = 'info'

        if rps_250 is not None:
            if rps_250 >= 90:
                signals.append('RPS强势')
                if alert == 'info':
                    alert = 'green'
            elif rps_250 < 50:
                signals.append('RPS偏弱')
                if alert in ('info', 'green'):
                    alert = 'yellow'

        if rps_slope is not None and rps_slope < -0.5 and rps_250 is not None and rps_250 >= 80:
            signals.append('RPS强度衰减')
            alert = 'yellow'

        if close is not None and ma20 is not None:
            if close < ma20 * 0.98:
                signals.append('跌破20日线')
                alert = 'red'
            elif close < ma20 * 1.02:
                signals.append('回踩20日线')
                if alert not in ('red',):
                    alert = 'yellow'

        if close is not None and ma60 is not None:
            if close < ma60 * 0.98:
                signals.append('跌破60日线')
                alert = 'red'

        if rsi is not None:
            if rsi > 75:
                signals.append('RSI超买')
                if alert == 'info':
                    alert = 'yellow'
            elif rsi < 30:
                signals.append('RSI超卖')
                if alert not in ('red',):
                    alert = 'yellow'

        if macd_dif is not None and macd_dea is not None:
            if macd_dif > macd_dea:
                signals.append('MACD金叉')
                if alert == 'info':
                    alert = 'green'
            else:
                signals.append('MACD死叉')
                if alert == 'info':
                    alert = 'yellow'

        if volume_ratio is not None and volume_ratio > 2.0:
            signals.append('放量异动')
            if alert == 'info':
                alert = 'green'

        alert_counts[alert] = alert_counts.get(alert, 0) + 1

        records.append((
            code, latest_date,
            close, rps_250, rps_120, rps_20, rps_slope,
            ma20, ma60, ma250, volume_ratio, rsi, macd_dif, macd_dea,
            pct_since_add, rps_change,
            json.dumps(signals, ensure_ascii=False),
            alert,
            datetime.utcnow(),
        ))

    if records:
        sql = '''
            INSERT INTO candidate_monitor_daily
                (stock_code, trade_date, close, rps_250, rps_120, rps_20, rps_slope,
                 ma20, ma60, ma250, volume_ratio, rsi, macd_dif, macd_dea,
                 pct_since_add, rps_change, signals, alert_level, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                close=VALUES(close), rps_250=VALUES(rps_250), rps_120=VALUES(rps_120),
                rps_20=VALUES(rps_20), rps_slope=VALUES(rps_slope),
                ma20=VALUES(ma20), ma60=VALUES(ma60), ma250=VALUES(ma250),
                volume_ratio=VALUES(volume_ratio), rsi=VALUES(rsi),
                macd_dif=VALUES(macd_dif), macd_dea=VALUES(macd_dea),
                pct_since_add=VALUES(pct_since_add), rps_change=VALUES(rps_change),
                signals=VALUES(signals), alert_level=VALUES(alert_level)
        '''
        execute_many(sql, records, env=env)

    summary = {'monitored': len(stocks), 'alerts': alert_counts, 'trade_date': latest_date}
    logger.info('[candidate_pool] monitor done: %s', summary)
    return summary


# ---------------------------------------------------------------------------
# Feishu push
# ---------------------------------------------------------------------------

def push_feishu_daily_report(env: str = 'online') -> bool:
    """Build and push daily monitor summary to Feishu webhook."""
    webhook = FEISHU_WEBHOOK
    if not webhook:
        logger.warning('[feishu] FEISHU_WEBHOOK_URL not set, skip push')
        return False

    stocks = list_stocks()
    if not stocks:
        return False

    today_str = _today()
    red = [s for s in stocks if s.get('alert_level') == 'red' and s.get('monitor_date') == today_str]
    yellow = [s for s in stocks if s.get('alert_level') == 'yellow' and s.get('monitor_date') == today_str]
    green = [s for s in stocks if s.get('alert_level') == 'green' and s.get('monitor_date') == today_str]

    def stock_line(s: dict) -> str:
        name = s['stock_name'] or s['stock_code']
        code = s['stock_code']
        sigs = ', '.join(s.get('signals') or []) or '无信号'
        pct = s.get('pct_since_add')
        pct_str = (f'+{pct:.1f}%' if pct and pct > 0 else f'{pct:.1f}%') if pct is not None else '--'
        rps = s.get('rps_250')
        rps_str = f'{rps:.1f}' if rps is not None else '--'
        return f'  {name} ({code}): RPS={rps_str}, 加入以来{pct_str} | {sigs}'

    lines = [f'[候选池每日监控] {today_str}', '']

    if red:
        lines.append(f'[RED] 需关注 ({len(red)}只)')
        for s in red:
            lines.append(stock_line(s))
        lines.append('')

    if yellow:
        lines.append(f'[YELLOW] 提醒 ({len(yellow)}只)')
        for s in yellow:
            lines.append(stock_line(s))
        lines.append('')

    if green:
        lines.append(f'[GREEN] 积极信号 ({len(green)}只)')
        for s in green:
            lines.append(stock_line(s))
        lines.append('')

    # overall pnl summary
    pcts = [s['pct_since_add'] for s in stocks if s.get('pct_since_add') is not None]
    if pcts:
        avg_pct = sum(pcts) / len(pcts)
        best = max(stocks, key=lambda x: x.get('pct_since_add') or -999)
        worst = min(stocks, key=lambda x: x.get('pct_since_add') or 999)
        avg_str = f'+{avg_pct:.1f}%' if avg_pct > 0 else f'{avg_pct:.1f}%'
        lines.append(f'候选池总览 ({len(stocks)}只): 平均 {avg_str}')
        lines.append(f'  最强: {best["stock_name"]} {best.get("pct_since_add", 0):+.1f}%')
        lines.append(f'  最弱: {worst["stock_name"]} {worst.get("pct_since_add", 0):+.1f}%')

    content = '\n'.join(lines)

    payload = {
        'msg_type': 'text',
        'content': {'text': content},
    }

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info('[feishu] push success: %s', resp.status_code)
        return True
    except Exception as e:
        logger.error('[feishu] push failed: %s', e)
        return False


# ---------------------------------------------------------------------------
# Stock screener (based on trade_stock_info)
# ---------------------------------------------------------------------------

def get_screen_options() -> dict:
    """Return distinct provinces and industries for filter dropdowns."""
    provinces = execute_query(
        'SELECT DISTINCT province FROM trade_stock_info WHERE province IS NOT NULL ORDER BY province',
        env=_DB_ENV,
    )
    industries = execute_query(
        'SELECT DISTINCT industry FROM trade_stock_info WHERE industry IS NOT NULL ORDER BY industry',
        env=_DB_ENV,
    )
    return {
        'provinces': [r['province'] for r in provinces if r['province']],
        'industries': [r['industry'] for r in industries if r['industry']],
    }


def screen_stocks(
    province: Optional[str] = None,
    industry: Optional[str] = None,
    keyword: Optional[str] = None,
    listed_years_min: Optional[int] = None,
    listed_years_max: Optional[int] = None,
    min_rps: float = 0,
    sort_by: str = 'rps_250',
    limit: int = 200,
) -> list:
    """
    Screen stocks from trade_stock_info with multi-dimension filters.
    Joins RPS + price data and checks candidate pool membership.

    Filters:
      - province: exact match
      - industry: exact match (trade_stock_info.industry)
      - keyword: LIKE search on main_business + business_scope + company_intro
      - listed_years_min/max: years since listed_date
      - min_rps: minimum rps_250
    """
    where = ['1=1']
    params = []

    if province:
        where.append('i.province = %s')
        params.append(province)

    if industry:
        where.append('i.industry = %s')
        params.append(industry)

    if keyword:
        kw = f'%{keyword}%'
        where.append('(i.main_business LIKE %s OR i.business_scope LIKE %s OR i.company_intro LIKE %s)')
        params.extend([kw, kw, kw])

    if listed_years_min is not None:
        where.append('i.listed_date <= DATE_SUB(CURDATE(), INTERVAL %s YEAR)')
        params.append(listed_years_min)

    if listed_years_max is not None:
        where.append('i.listed_date >= DATE_SUB(CURDATE(), INTERVAL %s YEAR)')
        params.append(listed_years_max)

    where_sql = ' AND '.join(where)

    rows = execute_query(
        f'''SELECT i.stock_code, i.stock_name, i.province, i.city,
                   i.industry, i.listed_date,
                   LEFT(i.main_business, 80) AS main_business_short
            FROM trade_stock_info i
            WHERE {where_sql}
            ORDER BY i.stock_code
            LIMIT 2000''',
        tuple(params) if params else None,
        env=_DB_ENV,
    )

    if not rows:
        return []

    codes_list = [r['stock_code'] for r in rows]

    # Fetch latest RPS
    latest_date = _latest_trade_date()
    CHUNK = 200
    rps_map = {}
    for i in range(0, len(codes_list), CHUNK):
        chunk = codes_list[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        rps_rows = execute_query(
            f'SELECT stock_code, rps_20, rps_120, rps_250, rps_slope '
            f'FROM trade_stock_rps WHERE stock_code IN ({ph}) AND trade_date = %s',
            tuple(chunk) + (latest_date,), env=_DB_ENV,
        )
        for r in rps_rows:
            rps_map[r['stock_code']] = r

    # Fetch latest close price
    price_map = {}
    for i in range(0, len(codes_list), CHUNK):
        chunk = codes_list[i:i + CHUNK]
        ph = ','.join(['%s'] * len(chunk))
        price_rows = execute_query(
            f'SELECT stock_code, close_price FROM trade_stock_daily '
            f'WHERE stock_code IN ({ph}) AND trade_date = %s',
            tuple(chunk) + (latest_date,), env=_DB_ENV,
        )
        for r in price_rows:
            price_map[r['stock_code']] = float(r['close_price']) if r.get('close_price') is not None else None

    # Check candidate pool membership
    pool_codes = set()
    existing = execute_query('SELECT stock_code FROM candidate_pool_stocks', env=_DB_ENV)
    for r in existing:
        pool_codes.add(r['stock_code'])

    # Assemble result
    result = []
    for r in rows:
        code = r['stock_code']
        rps = rps_map.get(code, {})
        rps_250 = float(rps['rps_250']) if rps.get('rps_250') is not None else None

        if min_rps > 0 and (rps_250 is None or rps_250 < min_rps):
            continue

        result.append({
            'stock_code': code,
            'stock_name': r['stock_name'],
            'province': r['province'],
            'city': r['city'],
            'industry': r['industry'],
            'listed_date': str(r['listed_date']) if r['listed_date'] else None,
            'main_business_short': r['main_business_short'],
            'close': price_map.get(code),
            'rps_250': rps_250,
            'rps_120': float(rps['rps_120']) if rps.get('rps_120') is not None else None,
            'rps_20': float(rps['rps_20']) if rps.get('rps_20') is not None else None,
            'rps_slope': float(rps['rps_slope']) if rps.get('rps_slope') is not None else None,
            'in_pool': code in pool_codes,
            'trade_date': latest_date,
        })

    # Sort
    valid_sorts = {'rps_250', 'rps_120', 'rps_20', 'rps_slope'}
    if sort_by not in valid_sorts:
        sort_by = 'rps_250'
    result.sort(key=lambda x: (x[sort_by] is None, -(x[sort_by] or 0)))
    return result[:limit]
