# -*- coding: utf-8 -*-
"""
ETF Log Bias service

Provides:
  - get_latest()   : latest trade date snapshot for all tracked ETFs
  - trigger_run()  : run daily log bias calculation in a background thread
"""
import logging
import threading
from datetime import date, datetime
from typing import Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')

LOG_BIAS_TIMEOUT_HOURS = 1

# Run-state table (one row per run_date, reuses trade_log_bias_run)
_RUN_DDL = """
CREATE TABLE IF NOT EXISTS trade_log_bias_run (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_date     DATE NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'pending',
    etf_count    INT NOT NULL DEFAULT 0,
    triggered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at  DATETIME,
    error_msg    VARCHAR(500),
    UNIQUE KEY uk_run_date (run_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='log bias daily run tracking';
"""


def _ensure_run_table() -> None:
    from config.db import get_connection
    conn = get_connection('online')
    try:
        cur = conn.cursor()
        cur.execute(_RUN_DDL)
        conn.commit()
        cur.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_latest() -> list[dict]:
    """
    Return the latest trade date's log_bias snapshot for all tracked ETFs.
    Falls back to last available date if today has no data.
    """
    rows = execute_query(
        """
        SELECT t.ts_code, t.trade_date, t.close_price, t.log_bias,
               t.signal_state, t.prev_state
        FROM trade_log_bias_daily t
        INNER JOIN (
            SELECT ts_code, MAX(trade_date) AS max_date
            FROM trade_log_bias_daily
            GROUP BY ts_code
        ) m ON t.ts_code = m.ts_code AND t.trade_date = m.max_date
        ORDER BY t.ts_code
        """,
        env='online',
    )
    if not rows:
        return []

    from strategist.log_bias.config import DEFAULT_ETFS
    result = []
    for r in rows:
        code = r['ts_code']
        result.append({
            'ts_code': code,
            'name': DEFAULT_ETFS.get(code, code),
            'trade_date': str(r['trade_date']),
            'close': float(r['close_price']) if r['close_price'] is not None else None,
            'log_bias': float(r['log_bias']) if r['log_bias'] is not None else None,
            'signal_state': r['signal_state'] or 'normal',
            'prev_state': r['prev_state'] or '',
        })
    return result


def get_multi_day_table(days: int = 10) -> dict:
    """
    Return a multi-day log_bias matrix for all CSI thematic indices.

    Returns:
        {
          "dates": ["04-08", "04-09", ...],
          "rows": [
            {"code": "930713", "name": "人工智能", "values": [3.21, 2.85, ...], "signal_state": "normal"},
            ...
          ]
        }
    Rows sorted by latest day's log_bias descending.
    """
    from strategist.log_bias.config import DEFAULT_CSI_INDICES, DEFAULT_ETFS

    # Merge both name dicts for lookup
    all_names = {}
    all_names.update(DEFAULT_ETFS)
    all_names.update(DEFAULT_CSI_INDICES)

    # Get all CSI index codes
    csi_codes = list(DEFAULT_CSI_INDICES.keys())
    if not csi_codes:
        return {'dates': [], 'rows': []}

    placeholders = ','.join(['%s'] * len(csi_codes))

    # Step 1: find the last N distinct trade dates for these codes
    date_rows = execute_query(
        f"""
        SELECT DISTINCT trade_date
        FROM trade_log_bias_daily
        WHERE ts_code IN ({placeholders})
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (*csi_codes, days),
        env='online',
    )
    if not date_rows:
        return {'dates': [], 'rows': []}

    trade_dates = sorted([r['trade_date'] for r in date_rows])
    date_strs = [str(d) for d in trade_dates]
    date_labels = [str(d)[5:].replace('-', '/') for d in trade_dates]  # "04/08"

    # Step 2: fetch all log_bias values for these codes and dates
    date_placeholders = ','.join(['%s'] * len(date_strs))
    data_rows = execute_query(
        f"""
        SELECT ts_code, trade_date, log_bias, signal_state
        FROM trade_log_bias_daily
        WHERE ts_code IN ({placeholders})
          AND trade_date IN ({date_placeholders})
        ORDER BY ts_code, trade_date
        """,
        (*csi_codes, *date_strs),
        env='online',
    )
    if not data_rows:
        return {'dates': date_labels, 'rows': []}

    # Step 3: pivot into matrix
    # {ts_code: {date_str: {log_bias, signal_state}}}
    pivot = {}
    for r in data_rows:
        code = r['ts_code']
        d = str(r['trade_date'])
        if code not in pivot:
            pivot[code] = {}
        pivot[code][d] = {
            'log_bias': float(r['log_bias']) if r['log_bias'] is not None else None,
            'signal_state': r['signal_state'] or 'normal',
        }

    # Step 4: build rows, sorted by latest day's log_bias desc
    latest_date = date_strs[-1]
    rows = []
    for code in csi_codes:
        if code not in pivot:
            continue
        values = []
        for d in date_strs:
            cell = pivot[code].get(d)
            values.append(cell['log_bias'] if cell else None)
        latest_cell = pivot[code].get(latest_date, {})
        rows.append({
            'code': code,
            'name': all_names.get(code, code),
            'values': values,
            'signal_state': latest_cell.get('signal_state', 'normal'),
        })

    # Sort by latest value descending (None at bottom)
    rows.sort(key=lambda r: r['values'][-1] if r['values'][-1] is not None else -9999, reverse=True)

    return {'dates': date_labels, 'rows': rows}


def get_history(ts_code: str, days: int = 120) -> list[dict]:
    """Return last `days` rows of log_bias data for a single ETF."""
    rows = execute_query(
        """
        SELECT trade_date, close_price, log_bias, signal_state
        FROM trade_log_bias_daily
        WHERE ts_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (ts_code, days),
        env='online',
    )
    if not rows:
        return []
    from strategist.log_bias.config import DEFAULT_ETFS
    result = []
    for r in reversed(rows):  # ascending date order
        result.append({
            'trade_date': str(r['trade_date']),
            'close': float(r['close_price']) if r['close_price'] is not None else None,
            'log_bias': float(r['log_bias']) if r['log_bias'] is not None else None,
            'signal_state': r['signal_state'] or 'normal',
        })
    return result


def get_run_status() -> Optional[dict]:
    """Return today's run record if exists."""
    today = date.today().isoformat()
    rows = execute_query(
        "SELECT * FROM trade_log_bias_run WHERE run_date = %s ORDER BY id DESC LIMIT 1",
        (today,),
        env='online',
    )
    if not rows:
        return None
    return _fmt_run(rows[0])


def trigger_run(force: bool = False) -> dict:
    """Trigger log bias daily calculation for the latest trade date."""
    _ensure_run_table()

    # Get the latest trade date from database
    trade_date_rows = execute_query(
        "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily WHERE stock_code LIKE '%%.SZ' OR stock_code LIKE '%%.SH'",
        env='online',
    )
    if not trade_date_rows or not trade_date_rows[0]['max_date']:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail='无法获取最新交易日数据')
    trade_date = str(trade_date_rows[0]['max_date'])

    rows = execute_query(
        "SELECT id, status, triggered_at FROM trade_log_bias_run WHERE run_date = %s ORDER BY id DESC LIMIT 1",
        (trade_date,),
        env='online',
    )
    if rows:
        row = rows[0]
        status = row['status']
        if status == 'done' and not force:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail=f'交易日 {trade_date} 已完成，不可重复触发')
        if status in ('pending', 'running') and not force:
            triggered_at = row['triggered_at']
            if isinstance(triggered_at, str):
                triggered_at = datetime.fromisoformat(triggered_at)
            elapsed = (datetime.now() - triggered_at.replace(tzinfo=None)).total_seconds() / 3600
            if elapsed < LOG_BIAS_TIMEOUT_HOURS:
                from fastapi import HTTPException
                raise HTTPException(status_code=409, detail=f'交易日 {trade_date} 任务正在执行中')
            execute_update(
                "UPDATE trade_log_bias_run SET status='failed', error_msg='execution timeout' WHERE id = %s",
                (row['id'],),
                env='online',
            )
        execute_update(
            "DELETE FROM trade_log_bias_run WHERE run_date = %s",
            (trade_date,),
            env='online',
        )

    execute_update(
        "INSERT INTO trade_log_bias_run (run_date, status, triggered_at) VALUES (%s, 'pending', NOW())",
        (trade_date,),
        env='online',
    )
    id_rows = execute_query(
        "SELECT id FROM trade_log_bias_run WHERE run_date = %s ORDER BY id DESC LIMIT 1",
        (trade_date,),
        env='online',
    )
    run_id = id_rows[0]['id']

    threading.Thread(target=_run_in_background, args=(run_id, trade_date), daemon=True).start()
    return {'run_id': run_id, 'status': 'pending', 'run_date': trade_date}


def trigger_index_run(force: bool = False) -> dict:
    """Trigger CSI index log bias calculation in a background thread."""
    _ensure_run_table()

    run_date = date.today().isoformat()

    # Check for existing index run (use run_date with a suffix marker)
    run_key = f'{run_date}_index'
    rows = execute_query(
        "SELECT id, status, triggered_at FROM trade_log_bias_run WHERE run_date = %s ORDER BY id DESC LIMIT 1",
        (run_key,),
        env='online',
    )
    if rows and not force:
        row = rows[0]
        status = row['status']
        if status == 'done':
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail=f'CSI 指数计算已完成，不可重复触发')
        if status in ('pending', 'running'):
            triggered_at = row['triggered_at']
            if isinstance(triggered_at, str):
                triggered_at = datetime.fromisoformat(triggered_at)
            elapsed = (datetime.now() - triggered_at.replace(tzinfo=None)).total_seconds() / 3600
            if elapsed < LOG_BIAS_TIMEOUT_HOURS:
                from fastapi import HTTPException
                raise HTTPException(status_code=409, detail='CSI 指数计算正在执行中')
            execute_update(
                "UPDATE trade_log_bias_run SET status='failed', error_msg='execution timeout' WHERE id = %s",
                (row['id'],),
                env='online',
            )

    if rows:
        execute_update(
            "DELETE FROM trade_log_bias_run WHERE run_date = %s",
            (run_key,),
            env='online',
        )

    execute_update(
        "INSERT INTO trade_log_bias_run (run_date, status, triggered_at) VALUES (%s, 'pending', NOW())",
        (run_key,),
        env='online',
    )
    id_rows = execute_query(
        "SELECT id FROM trade_log_bias_run WHERE run_date = %s ORDER BY id DESC LIMIT 1",
        (run_key,),
        env='online',
    )
    run_id = id_rows[0]['id']

    threading.Thread(target=_run_indices_in_background, args=(run_id,), daemon=True).start()
    return {'run_id': run_id, 'status': 'pending', 'run_date': run_date, 'type': 'index'}


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------

def _run_in_background(run_id: int, run_date: str) -> None:
    try:
        execute_update(
            "UPDATE trade_log_bias_run SET status='running' WHERE id = %s",
            (run_id,),
            env='online',
        )
        logger.info('[LOG_BIAS] run %d starting', run_id)

        import os
        from strategist.log_bias.config import LogBiasConfig
        from strategist.log_bias.run_daily import run_daily
        config = LogBiasConfig()
        config.db_env = 'online'
        # 覆盖报告输出目录，避免写入其他用户目录
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config.output_dir = os.path.join(_root, 'output', 'log_bias')
        os.makedirs(config.output_dir, exist_ok=True)
        run_daily(config, target_date=run_date)

        # count ETFs with data on the latest available trade date
        rows = execute_query(
            """SELECT COUNT(*) AS cnt FROM trade_log_bias_daily
               WHERE trade_date = (SELECT MAX(trade_date) FROM trade_log_bias_daily)""",
            env='online',
        )
        etf_count = rows[0]['cnt'] if rows else 0

        execute_update(
            "UPDATE trade_log_bias_run SET status='done', finished_at=NOW(), etf_count=%s WHERE id = %s",
            (etf_count, run_id),
            env='online',
        )
        logger.info('[LOG_BIAS] run %d done, %d ETFs', run_id, etf_count)
    except Exception as exc:
        err = str(exc)[:500]
        logger.exception('[LOG_BIAS] run %d failed: %s', run_id, err)
        execute_update(
            "UPDATE trade_log_bias_run SET status='failed', error_msg=%s, finished_at=NOW() WHERE id = %s",
            (err, run_id),
            env='online',
        )


def _run_indices_in_background(run_id: int) -> None:
    try:
        execute_update(
            "UPDATE trade_log_bias_run SET status='running' WHERE id = %s",
            (run_id,),
            env='online',
        )
        logger.info('[LOG_BIAS] index run %d starting', run_id)

        from strategist.log_bias.config import LogBiasConfig
        from strategist.log_bias.run_daily import run_daily_indices
        config = LogBiasConfig()
        config.db_env = 'online'
        ok_count = run_daily_indices(config)

        execute_update(
            "UPDATE trade_log_bias_run SET status='done', finished_at=NOW(), etf_count=%s WHERE id = %s",
            (ok_count, run_id),
            env='online',
        )
        logger.info('[LOG_BIAS] index run %d done, %d indices', run_id, ok_count)
    except Exception as exc:
        err = str(exc)[:500]
        logger.exception('[LOG_BIAS] index run %d failed: %s', run_id, err)
        execute_update(
            "UPDATE trade_log_bias_run SET status='failed', error_msg=%s, finished_at=NOW() WHERE id = %s",
            (err, run_id),
            env='online',
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_run(r) -> dict:
    def _dt(v):
        if v is None:
            return None
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return str(v)
    return {
        'id': r['id'],
        'run_date': _dt(r['run_date']),
        'status': r['status'],
        'etf_count': r.get('etf_count', 0),
        'triggered_at': _dt(r.get('triggered_at')),
        'finished_at': _dt(r.get('finished_at')),
        'error_msg': r.get('error_msg'),
    }
