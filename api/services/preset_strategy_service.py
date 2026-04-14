# -*- coding: utf-8 -*-
"""
预设策略服务

管理预设策略的触发、执行状态跟踪和结果查询。
使用 Celery 异步任务队列执行策略。
"""
import json
import logging
import math
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
    # Use UTC now for consistent comparison
    now = datetime.now(timezone.utc)
    # Remove timezone info from triggered_at if present for comparison
    if triggered_at.tzinfo:
        triggered_at_naive = triggered_at.replace(tzinfo=None)
        now_naive = now.replace(tzinfo=None)
    else:
        triggered_at_naive = triggered_at
        now_naive = now.replace(tzinfo=None)
    delta = now_naive - triggered_at_naive
    return delta.total_seconds() > STRATEGY_RUN_TIMEOUT_HOURS * 3600


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_preset_strategies() -> List[dict]:
    """
    Return all preset strategies, each augmented with:
      - latest_trade_date: latest trade date from database
      - latest_run: run summary for latest trade date (or None)
      - recent_runs: last 5 run summaries
    """
    # Get latest trade date from database
    trade_date_rows = execute_query(
        "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily",
        env='online',
    )
    latest_trade_date = trade_date_rows[0]['max_date'].isoformat() if trade_date_rows and trade_date_rows[0].get('max_date') else None

    result = []
    for strategy in PRESET_STRATEGIES:
        key = strategy['key']
        recent_runs = get_strategy_runs(key, limit=5)
        latest_run = None
        if latest_trade_date:
            for run in recent_runs:
                if run['run_date'] == latest_trade_date:
                    latest_run = run
                    break
        result.append({
            'meta': strategy,
            'latest_trade_date': latest_trade_date,
            'latest_run': latest_run,
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


def trigger_strategy_run(strategy_key: str, force: bool = False) -> dict:
    """
    Trigger a new preset strategy run for the latest trade date.

    Rules:
    - Uses latest trade date from database (not date.today())
    - status pending/running (not timed out) -> 409 already in progress
    - status done -> 409 already done for this trade date (unless force=True)
    - status running but timed out -> mark failed, allow re-trigger
    - status failed -> allow re-trigger
    - no record for trade date -> insert new record

    Args:
        strategy_key: Strategy identifier (e.g., 'microcap_pure_mv')
        force: If True, allow re-running even if already done
    """
    # Validate strategy key
    valid_keys = {s['key'] for s in PRESET_STRATEGIES}
    if strategy_key not in valid_keys:
        raise HTTPException(status_code=404, detail=f'Strategy {strategy_key!r} not found')

    # Get latest trade date from database
    trade_date_rows = execute_query(
        "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily",
        env='online',
    )
    if not trade_date_rows or not trade_date_rows[0].get('max_date'):
        raise HTTPException(status_code=500, detail='无法获取最新交易日数据')
    trade_date_str = str(trade_date_rows[0]['max_date'])

    rows = execute_query(
        """
        SELECT id, status, triggered_at,
               TIMESTAMPDIFF(HOUR, triggered_at, NOW()) AS hours_since_trigger
        FROM trade_preset_strategy_run
        WHERE strategy_key = %s AND run_date = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (strategy_key, trade_date_str),
    )

    if rows:
        row = dict(rows[0])
        status = row['status']
        hours_since = row.get('hours_since_trigger', 0)

        if status == 'done':
            if not force:
                raise HTTPException(
                    status_code=409,
                    detail=f'交易日 {trade_date_str} 已完成，不可重复触发'
                )
            # force=True: delete the completed run and allow re-trigger
            logger.info('[PRESET] Force re-trigger for %s on %s, deleting previous run %s',
                       strategy_key, trade_date_str, row['id'])

        if status in ('pending', 'running'):
            if hours_since > STRATEGY_RUN_TIMEOUT_HOURS:
                execute_update(
                    "UPDATE trade_preset_strategy_run SET status = 'failed', error_msg = 'execution timeout' WHERE id = %s",
                    (row['id'],),
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f'交易日 {trade_date_str} 任务已在执行中'
                )

        # failed (any reason) or timed-out running: delete old record so INSERT succeeds
        execute_update(
            'DELETE FROM trade_preset_strategy_run WHERE id = %s',
            (row['id'],),
        )

    # Insert new pending record with actual trade date
    execute_update(
        """
        INSERT INTO trade_preset_strategy_run
            (strategy_key, run_date, status, triggered_at,
             signal_count, momentum_count, reversal_count,
             market_status, market_message)
        VALUES (%s, %s, 'pending', NOW(), 0, 0, 0, '', '')
        """,
        (strategy_key, trade_date_str),
    )

    # Fetch the new run_id
    id_rows = execute_query(
        """
        SELECT id FROM trade_preset_strategy_run
        WHERE strategy_key = %s AND run_date = %s
        ORDER BY id DESC LIMIT 1
        """,
        (strategy_key, trade_date_str),
    )
    run_id = id_rows[0]['id'] if id_rows else None

    # Submit to Celery task queue
    from api.tasks.preset_strategies import run_preset_strategy
    task = run_preset_strategy.apply_async(args=[run_id, strategy_key, 'online'])
    logger.info('[PRESET] Submitted Celery task: run_id=%d task_id=%s strategy=%s trade_date=%s',
                run_id, task.id, strategy_key, trade_date_str)

    return {'run_id': run_id, 'status': 'pending', 'task_id': task.id, 'run_date': trade_date_str}


