# -*- coding: utf-8 -*-
"""
预设策略服务

管理预设策略的触发、执行状态跟踪和结果查询。
"""
import json
import logging
import math
import threading
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')

STRATEGY_RUN_TIMEOUT_HOURS = 3

PRESET_STRATEGIES = [
    {
        'key': 'momentum_reversal',
        'name': '动量反转策略',
        'description': '基于RPS动量+价格底部反转的两阶段选股，覆盖全A股5000+只，每日盘后运行',
        'params_desc': 'RPS阈值: 95 / 反转分位: 35% / 大盘过滤: MA50/MA120',
        'warnings': [],
    },
    {
        'key': 'microcap_pure_mv',
        'name': '微盘股策略',
        'description': '全市场市值后20%微盘股，财务风控过滤（排除亏损/高负债/负现金流），每日盘后更新持仓候选',
        'params_desc': '因子: pure_mv（纯市值排序）/ 选股: 15只 / 持有: 20日 / 财务风控: 开启',
        'warnings': [
            {
                'type': 'danger',
                'title': '[RED] 高风险月份',
                'body': '1月（量化踩踏/年末资金回笼）、4月（年报披露截止4/30）、8月（半年报截止8/31）、12月（机构调仓抛压）历史亏损显著，建议减仓或暂停',
            },
            {
                'type': 'warning',
                'title': '[WARN] 止损设置',
                'body': '历史最大回撤约 -48%，单次极端月份最大跌幅 -23.59%（2024-01）。建议：大盘跌破MA60时暂停建仓；单月亏损超15%强制止损；严格控制单策略仓位上限',
            },
            {
                'type': 'info',
                'title': '[INFO] 流动性风险',
                'body': '微盘股日均成交额小，实际滑点高于回测假设（0.1%），建议成交额<500万的个股分批轻仓，避免冲击成本过高',
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_summary(row: dict) -> dict:
    """Convert a DB row dict to PresetRunSummary-compatible dict."""
    return {
        'id': row['id'],
        'run_date': str(row['run_date']),
        'status': row['status'],
        'signal_count': row['signal_count'],
        'momentum_count': row['momentum_count'],
        'reversal_count': row['reversal_count'],
        'market_status': row['market_status'],
        'market_message': row['market_message'],
        'triggered_at': str(row['triggered_at']),
        'finished_at': str(row['finished_at']) if row.get('finished_at') else None,
        'error_msg': row.get('error_msg'),
    }


def _is_timeout(row: dict) -> bool:
    """Check whether a 'running' row has exceeded the timeout threshold."""
    triggered_at = row.get('triggered_at')
    if not isinstance(triggered_at, datetime):
        return False
    now = datetime.now()
    delta = now - triggered_at.replace(tzinfo=None)
    return delta.total_seconds() > STRATEGY_RUN_TIMEOUT_HOURS * 3600


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_preset_strategies() -> List[dict]:
    """
    Return all preset strategies, each augmented with:
      - today_run: today's run summary (or None)
      - recent_runs: last 5 run summaries
    """
    today_str = date.today().isoformat()
    result = []
    for strategy in PRESET_STRATEGIES:
        key = strategy['key']
        recent_runs = get_strategy_runs(key, limit=5)
        today_run = None
        for run in recent_runs:
            if run['run_date'] == today_str:
                today_run = run
                break
        result.append({
            'meta': strategy,
            'today_run': today_run,
            'recent_runs': recent_runs,
        })
    return result


def get_strategy_runs(strategy_key: str, limit: int = 5) -> List[dict]:
    """Return the most recent `limit` run summaries for a strategy."""
    rows = execute_query(
        """
        SELECT id, run_date, status, signal_count, momentum_count, reversal_count,
               market_status, market_message, triggered_at, finished_at, error_msg
        FROM trade_preset_strategy_run
        WHERE strategy_key = %s
        ORDER BY run_date DESC, id DESC
        LIMIT %s
        """,
        (strategy_key, limit),
    )
    return [_row_to_summary(dict(r)) for r in (rows or [])]


def get_run_detail(run_id: int) -> Optional[dict]:
    """Return full run detail including parsed signals list."""
    rows = execute_query(
        'SELECT * FROM trade_preset_strategy_run WHERE id = %s',
        (run_id,),
    )
    if not rows:
        return None
    row = dict(rows[0])
    summary = _row_to_summary(row)
    try:
        signals = json.loads(row.get('signals_json') or '[]')
    except (ValueError, TypeError):
        signals = []
    summary['signals'] = signals
    return summary


def trigger_strategy_run(strategy_key: str) -> dict:
    """
    Trigger a new preset strategy run for today.

    Rules:
    - status pending/running (not timed out) -> 409 already in progress
    - status done -> 409 already done today
    - status running but timed out -> mark failed, allow re-trigger
    - status failed -> allow re-trigger
    - no record today -> insert new record
    """
    # Validate strategy key
    valid_keys = {s['key'] for s in PRESET_STRATEGIES}
    if strategy_key not in valid_keys:
        raise HTTPException(status_code=404, detail=f'Strategy {strategy_key!r} not found')

    today_str = date.today().isoformat()

    rows = execute_query(
        """
        SELECT id, status, triggered_at
        FROM trade_preset_strategy_run
        WHERE strategy_key = %s AND run_date = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (strategy_key, today_str),
    )

    if rows:
        row = dict(rows[0])
        status = row['status']

        if status == 'done':
            raise HTTPException(status_code=409, detail='今日已完成，不可重复触发')

        if status in ('pending', 'running'):
            if _is_timeout(row):
                execute_update(
                    "UPDATE trade_preset_strategy_run SET status = 'failed', error_msg = 'execution timeout' WHERE id = %s",
                    (row['id'],),
                )
            else:
                raise HTTPException(status_code=409, detail='今日任务已在执行中')

        # failed (any reason) or timed-out running: delete old record so INSERT succeeds
        execute_update(
            'DELETE FROM trade_preset_strategy_run WHERE id = %s',
            (row['id'],),
        )

    # Insert new pending record
    execute_update(
        """
        INSERT INTO trade_preset_strategy_run
            (strategy_key, run_date, status, triggered_at,
             signal_count, momentum_count, reversal_count,
             market_status, market_message)
        VALUES (%s, %s, 'pending', NOW(), 0, 0, 0, '', '')
        """,
        (strategy_key, today_str),
    )

    # Fetch the new run_id
    id_rows = execute_query(
        """
        SELECT id FROM trade_preset_strategy_run
        WHERE strategy_key = %s AND run_date = %s
        ORDER BY id DESC LIMIT 1
        """,
        (strategy_key, today_str),
    )
    run_id = id_rows[0]['id'] if id_rows else None

    # Launch background thread
    thread = threading.Thread(
        target=_execute_in_background,
        args=(run_id, strategy_key),
        daemon=True,
    )
    thread.start()

    return {'run_id': run_id, 'status': 'pending'}


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------

def _execute_in_background(run_id: int, strategy_key: str) -> None:
    """Run the selected strategy in a background thread and persist results."""
    logger.info('[PRESET] Starting background run %s for strategy %s', run_id, strategy_key)

    # Mark as running
    execute_update(
        "UPDATE trade_preset_strategy_run SET status = 'running' WHERE id = %s",
        (run_id,),
    )

    try:
        if strategy_key == 'momentum_reversal':
            _run_momentum_reversal(run_id)
        elif strategy_key == 'microcap_pure_mv':
            _run_microcap_pure_mv(run_id)
        else:
            raise ValueError(f'Unknown strategy key: {strategy_key}')
    except Exception as exc:
        error_msg = str(exc)[:500]
        logger.error('[PRESET] Run %s failed: %s', run_id, error_msg)
        try:
            execute_update(
                """
                UPDATE trade_preset_strategy_run
                SET status = 'failed', error_msg = %s, finished_at = NOW()
                WHERE id = %s
                """,
                (error_msg, run_id),
            )
        except Exception as update_exc:
            logger.error('[PRESET] Failed to update error status for run %s: %s', run_id, update_exc)


def _safe_float(v) -> Optional[float]:
    """Convert value to float, returning None for NaN/Inf."""
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _run_momentum_reversal(run_id: int) -> None:
    """Execute momentum reversal screener and persist results."""
    import os
    import sys

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from strategist.doctor_tao.signal_screener import SignalScreener

    screener = SignalScreener()
    result_df = screener.run_screener(output_csv=False)

    # Build signals list
    signal_cols = ['stock_code', 'stock_name', 'signal_type', 'rps', 'close', 'ma20', 'ma250', 'volume_ratio']
    signals = []
    if result_df is not None and len(result_df) > 0:
        available_cols = [c for c in signal_cols if c in result_df.columns]
        for _, row in result_df[available_cols].iterrows():
            record = {}
            for col in available_cols:
                val = row[col]
                if col in ('rps', 'close', 'ma20', 'ma250', 'volume_ratio'):
                    record[col] = _safe_float(val)
                else:
                    record[col] = '' if (val is None or (isinstance(val, float) and math.isnan(val))) else str(val)
            signals.append(record)

    signals_json = json.dumps(signals, ensure_ascii=False)

    # Compute counts
    signal_count = len(signals)
    momentum_count = sum(1 for s in signals if s.get('signal_type') == 'momentum')
    reversal_count = sum(1 for s in signals if s.get('signal_type') == 'reversal')

    # Market status from first signal row (all rows carry same market info)
    market_status = ''
    market_message = ''
    if result_df is not None and len(result_df) > 0:
        if 'market_status' in result_df.columns:
            market_status = str(result_df['market_status'].iloc[0] or '')
        if 'market_message' in result_df.columns:
            market_message = str(result_df['market_message'].iloc[0] or '')[:200]

    execute_update(
        """
        UPDATE trade_preset_strategy_run
        SET status = 'done',
            signal_count = %s,
            momentum_count = %s,
            reversal_count = %s,
            market_status = %s,
            market_message = %s,
            signals_json = %s,
            finished_at = NOW()
        WHERE id = %s
        """,
        (signal_count, momentum_count, reversal_count,
         market_status, market_message, signals_json, run_id),
    )
    logger.info('[PRESET] Run %s completed: %s signals', run_id, signal_count)


def _run_microcap_pure_mv(run_id: int) -> None:
    """Select today's microcap candidate stocks (pure_mv factor with financial filters)."""
    import os
    import sys

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from config.db import execute_query as db_query

    # Get latest trade date
    date_rows = db_query(
        "SELECT MAX(trade_date) AS latest_date FROM trade_stock_daily_basic",
        (),
    )
    if not date_rows or not date_rows[0].get('latest_date'):
        raise ValueError('No trade date found in trade_stock_daily_basic')
    trade_date = str(date_rows[0]['latest_date'])

    # Get microcap universe: bottom 20% by market cap, financial risk filters
    from strategist.microcap.universe import get_daily_universe
    universe = get_daily_universe(
        trade_date=trade_date,
        percentile=0.20,
        exclude_st=True,
        require_positive_pe=False,  # pure_mv doesn't require positive PE
        min_avg_turnover=5_000_000.0,
        exclude_risk=True,
        max_debt_ratio=0.70,
        require_positive_profit=True,
        require_positive_cashflow=True,
    )

    if not universe:
        logger.warning('[PRESET] microcap_pure_mv: empty universe for %s', trade_date)
        execute_update(
            """
            UPDATE trade_preset_strategy_run
            SET status = 'done', signal_count = 0, momentum_count = 0, reversal_count = 0,
                market_status = '', market_message = %s, signals_json = '[]', finished_at = NOW()
            WHERE id = %s
            """,
            (f'no universe data for {trade_date}', run_id),
        )
        return

    # Fetch market cap and stock name for universe stocks, sort by total_mv ASC, take top 15
    top_n = 15
    placeholders = ','.join(['%s'] * len(universe))
    rows = db_query(
        f"""
        SELECT b.stock_code, b.total_mv, b.circ_mv, b.pe_ttm, b.pb,
               s.stock_name
        FROM trade_stock_daily_basic b
        LEFT JOIN trade_stock_basic s
            ON b.stock_code COLLATE utf8mb4_unicode_ci = s.stock_code COLLATE utf8mb4_unicode_ci
        WHERE b.trade_date = %s
          AND b.stock_code IN ({placeholders})
        ORDER BY b.total_mv ASC
        LIMIT %s
        """,
        [trade_date] + list(universe) + [top_n],
    )

    signals = []
    for row in (rows or []):
        signals.append({
            'stock_code': str(row['stock_code']),
            'stock_name': str(row.get('stock_name') or ''),
            'signal_type': 'microcap',
            'total_mv': _safe_float(row.get('total_mv')),   # 万元
            'circ_mv': _safe_float(row.get('circ_mv')),
            'pe_ttm': _safe_float(row.get('pe_ttm')),
            'pb': _safe_float(row.get('pb')),
        })

    signals_json = json.dumps(signals, ensure_ascii=False)
    signal_count = len(signals)

    execute_update(
        """
        UPDATE trade_preset_strategy_run
        SET status = 'done',
            signal_count = %s,
            momentum_count = 0,
            reversal_count = 0,
            market_status = '',
            market_message = %s,
            signals_json = %s,
            finished_at = NOW()
        WHERE id = %s
        """,
        (signal_count, f'trade_date={trade_date}', signals_json, run_id),
    )
    logger.info('[PRESET] microcap_pure_mv run %s completed: %s candidates for %s',
                run_id, signal_count, trade_date)
