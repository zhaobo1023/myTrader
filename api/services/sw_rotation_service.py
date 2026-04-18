# -*- coding: utf-8 -*-
"""
SW Rotation service: trigger weekly rotation analysis and persist results.
"""
import json
import logging
import threading
from datetime import date, datetime

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')

SW_ROTATION_TIMEOUT_HOURS = 3


def _get_week_info(d: date) -> dict:
    """返回日期的周信息（第几周）"""
    from datetime import timedelta

    # 使用 ISO 周数（一年中的第几周）
    iso_year, iso_week, _ = d.isocalendar()

    # 计算周的周一和周日
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)

    return {
        'year': iso_year,
        'week_number': iso_week,
        'week_label': f'{iso_year}年第{iso_week}周',
        'monday': monday.strftime('%Y-%m-%d'),
        'sunday': sunday.strftime('%Y-%m-%d'),
    }


def _friday_of_week(d: date) -> date:
    """Return the Friday of the given date's week (Mon=0 ... Sun=6)."""
    days_ahead = 4 - d.weekday()  # 4 = Friday
    if days_ahead < 0:
        days_ahead += 7
    return d + __import__('datetime').timedelta(days=days_ahead)


def _current_run_date() -> str:
    """Use today's Friday as run_date key."""
    friday = _friday_of_week(date.today())
    return friday.strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_runs(limit: int = 5) -> list[dict]:
    """Return recent N rotation runs (summary, no scores_json)."""
    rows = execute_query(
        """SELECT id, run_date, status, industry_count, hot_count, rising_count,
                  startup_count, retreat_count, triggered_at, finished_at, error_msg
           FROM trade_sw_rotation_run
           ORDER BY run_date DESC, id DESC
           LIMIT %s""",
        (limit,)
    )
    return [_fmt_row(r) for r in (rows or [])]


def get_run_detail(run_id: int) -> dict:
    rows = execute_query(
        'SELECT * FROM trade_sw_rotation_run WHERE id = %s', (run_id,)
    )
    if not rows:
        return {}
    r = rows[0]
    out = _fmt_row(r)
    raw = r.get('scores_json') or '[]'
    try:
        out['scores'] = json.loads(raw)
    except Exception:
        out['scores'] = []
    return out


def trigger_run() -> dict:
    """
    Trigger a new rotation run for the current week's Friday.
    - If done already -> 409
    - If pending/running (not timed out) -> 409
    - If running > TIMEOUT -> mark failed, allow re-insert
    - If failed -> delete old record, insert new
    """
    return _trigger_run(force=False)


def force_trigger_run() -> dict:
    """
    Force re-run even if already done.

    Requires explicit call (separate endpoint) to avoid accidental re-runs.
    """
    return _trigger_run(force=True)


def _trigger_run(force: bool = False) -> dict:
    """
    Internal trigger implementation.

    Args:
        force: If True, allow re-running even if status is 'done'
    """
    today_str = _current_run_date()

    rows = execute_query(
        'SELECT id, status, triggered_at FROM trade_sw_rotation_run WHERE run_date = %s',
        (today_str,)
    )
    if rows:
        row = rows[0]
        status = row['status']
        if status == 'done' and not force:
            raise _conflict('本周已完成，不可重复触发')
        if status == 'done' and force:
            # Force mode: delete old record and create new one
            execute_update(
                'DELETE FROM trade_sw_rotation_run WHERE id = %s', (row['id'],)
            )
            logger.info('[SW_ROTATION] Force re-run: deleted old run %d', row['id'])
        if status in ('pending', 'running'):
            # check timeout
            triggered_at = row['triggered_at']
            if isinstance(triggered_at, str):
                triggered_at = datetime.fromisoformat(triggered_at)
            elapsed = (datetime.now() - triggered_at).total_seconds() / 3600
            if elapsed < SW_ROTATION_TIMEOUT_HOURS:
                raise _conflict('本周任务正在执行中，请稍后再试')
            # timed out
            execute_update(
                "UPDATE trade_sw_rotation_run SET status='failed', error_msg='execution timeout' WHERE id = %s",
                (row['id'],)
            )
        if status == 'failed':
            execute_update(
                'DELETE FROM trade_sw_rotation_run WHERE id = %s', (row['id'],)
            )

    execute_update(
        """INSERT INTO trade_sw_rotation_run
               (run_date, status, triggered_at,
                industry_count, hot_count, rising_count, startup_count, retreat_count)
           VALUES (%s, 'pending', NOW(), 0, 0, 0, 0, 0)""",
        (today_str,)
    )
    rows2 = execute_query(
        'SELECT id FROM trade_sw_rotation_run WHERE run_date = %s ORDER BY id DESC LIMIT 1',
        (today_str,)
    )
    run_id = rows2[0]['id']

    threading.Thread(
        target=_execute_in_background,
        args=(run_id,),
        daemon=True,
    ).start()

    return {'run_id': run_id, 'status': 'pending', 'run_date': today_str}


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------

def _execute_in_background(run_id: int) -> None:
    try:
        execute_update(
            "UPDATE trade_sw_rotation_run SET status='running' WHERE id = %s",
            (run_id,)
        )
        scores_df = _run_rotation()
        scores = scores_df.reset_index().to_dict(orient='records')
        # clean up non-serialisable values (bool, numpy types)
        clean_scores = []
        for row in scores:
            clean_row = {}
            for k, v in row.items():
                if hasattr(v, 'item'):
                    v = v.item()
                if isinstance(v, float) and (v != v):  # NaN check
                    v = None
                clean_row[str(k)] = v
            clean_scores.append(clean_row)

        scores_json = json.dumps(clean_scores, ensure_ascii=False)
        industry_count = len(clean_scores)
        hot_count     = sum(1 for r in clean_scores if r.get('过热'))
        rising_count  = sum(1 for r in clean_scores if r.get('连续上升'))
        startup_count = sum(1 for r in clean_scores if r.get('短强长弱'))
        retreat_count = sum(1 for r in clean_scores if r.get('长强短弱'))

        execute_update(
            """UPDATE trade_sw_rotation_run
               SET status='done', finished_at=NOW(),
                   scores_json=%s, industry_count=%s,
                   hot_count=%s, rising_count=%s,
                   startup_count=%s, retreat_count=%s
               WHERE id = %s""",
            (scores_json, industry_count,
             hot_count, rising_count, startup_count, retreat_count,
             run_id)
        )
        logger.info('[SW_ROTATION] run %d done, %d industries', run_id, industry_count)
    except Exception as exc:
        err = str(exc)[:500]
        logger.exception('[SW_ROTATION] run %d failed: %s', run_id, err)
        execute_update(
            "UPDATE trade_sw_rotation_run SET status='failed', error_msg=%s WHERE id = %s",
            (err, run_id)
        )


def _run_rotation():
    """Fetch SW industry data and return sig_df DataFrame."""
    import numpy as np
    import pandas as pd
    import akshare as ak

    logger.info('[SW_ROTATION] fetching sw_index_first_info ...')
    sw_df = ak.sw_index_first_info()
    # current akshare columns: '行业代码', '行业名称', ...
    code_col = '行业代码' if '行业代码' in sw_df.columns else '指数代码'
    name_col = '行业名称' if '行业名称' in sw_df.columns else '指数名称'

    all_close = {}
    for _, row in sw_df.iterrows():
        code = str(row[code_col]).split('.')[0]  # strip '.SI' suffix if present
        name = row[name_col]
        try:
            df = ak.index_hist_sw(symbol=code, period='day')
            if df is not None and len(df) > 0:
                df['日期'] = pd.to_datetime(df['日期'])
                df = df.set_index('日期').sort_index()
                close_col = '收盘' if '收盘' in df.columns else df.columns[0]
                all_close[name] = df[close_col].astype(float)
                logger.info('[SW_ROTATION] fetched %s', name)
        except Exception as e:
            logger.warning('[SW_ROTATION] skip %s: %s', name, e)

    price_df = pd.DataFrame(all_close).sort_index().dropna(how='all')
    logger.info('[SW_ROTATION] %d industries / %d days', len(price_df.columns), len(price_df))

    # filter to last 3 years to keep it fast
    price_df = price_df[price_df.index >= '2023-01-01']

    from data_analyst.sw_rotation.rotation_v2 import calc_all_metrics, detect_signals_v2
    metrics = calc_all_metrics(price_df, short_w=20, long_w=250, lookback=250)

    hist_short  = metrics['hist_short']
    hist_long   = metrics['hist_long']
    cross_short = metrics['cross_short']

    weekly_hist = hist_short.resample('W-FRI').last().iloc[:-1].tail(16)

    cur_hs = hist_short.iloc[-1].dropna()
    cur_hl = hist_long.iloc[-1].dropna()
    cur_cs = cross_short.iloc[-1].dropna()

    sig_df = detect_signals_v2(weekly_hist, cur_hs, cur_hl, cur_cs,
                                hot_thr=85, rise_w=3)
    return sig_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_row(r: dict) -> dict:
    def _dt(v):
        if v is None:
            return None
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return str(v)

    # 从 triggered_at 提取周信息
    week_info = None
    if r.get('triggered_at'):
        try:
            triggered_date = datetime.fromisoformat(str(r['triggered_at'])).date()
            week_info = _get_week_info(triggered_date)
        except Exception:
            pass

    return {
        'id': r['id'],
        'run_date': _dt(r['run_date']),
        'status': r['status'],
        'industry_count': r.get('industry_count', 0),
        'hot_count': r.get('hot_count', 0),
        'rising_count': r.get('rising_count', 0),
        'startup_count': r.get('startup_count', 0),
        'retreat_count': r.get('retreat_count', 0),
        'triggered_at': _dt(r.get('triggered_at')),
        'finished_at': _dt(r.get('finished_at')),
        'error_msg': r.get('error_msg'),
        # 新增周信息
        'week_label': week_info['week_label'] if week_info else None,
        'week_number': week_info['week_number'] if week_info else None,
        'week_year': week_info['year'] if week_info else None,
    }


def _conflict(msg: str):
    from fastapi import HTTPException
    return HTTPException(status_code=409, detail=msg)
