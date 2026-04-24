# -*- coding: utf-8 -*-
"""
Celery tasks for preset strategies (momentum_reversal, microcap_pure_mv)
"""
import logging
import traceback
from datetime import date

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')


@celery_app.task(bind=True, name='tasks.run_preset_strategy')
def run_preset_strategy(self, run_id: int, strategy_key: str, env: str = 'online'):
    """
    Execute a preset strategy run in Celery.

    Args:
        run_id: Database record ID
        strategy_key: Strategy identifier (momentum_reversal or microcap_pure_mv)
        env: Database environment (default: online)

    Returns:
        dict with execution results
    """
    logger.info('[CELERY] Starting preset strategy run: run_id=%d strategy=%s', run_id, strategy_key)

    # Import inside function to avoid circular imports
    from config.db import execute_update, execute_query

    # Update status to running
    execute_update(
        "UPDATE trade_preset_strategy_run SET status = 'running' WHERE id = %s",
        (run_id,),
        env=env,
    )

    try:
        if strategy_key == 'momentum_reversal':
            result = _run_momentum_reversal(run_id, env)
        elif strategy_key == 'microcap_pure_mv':
            result = _run_microcap_pure_mv(run_id, env)
        else:
            raise ValueError(f'Unknown strategy key: {strategy_key}')

        logger.info('[CELERY] Completed preset strategy run: run_id=%d strategy=%s result=%s',
                    run_id, strategy_key, result)
        return {
            'run_id': run_id,
            'strategy_key': strategy_key,
            'status': 'done',
            **result,
        }

    except Exception as exc:
        error_msg = f'{str(exc)[:500]}\n{traceback.format_exc()}'
        logger.error('[CELERY] Preset strategy failed: run_id=%d strategy=%s error=%s',
                     run_id, strategy_key, error_msg)

        # Update database with error
        try:
            execute_update(
                """
                UPDATE trade_preset_strategy_run
                SET status = 'failed', error_msg = %s, finished_at = NOW()
                WHERE id = %s
                """,
                (error_msg[:500], run_id),
                env=env,
            )
        except Exception as update_exc:
            logger.error('[CELERY] Failed to update error status for run_id=%d: %s', run_id, update_exc)

        # Re-raise so Celery can track failure
        self.update_state(state='FAILURE', meta={'error': error_msg[:500]})
        raise


def _run_momentum_reversal(run_id: int, env: str) -> dict:
    """Execute momentum reversal screener and persist results (memory-optimized batch processing)."""
    import os
    import sys

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from strategist.doctor_tao.signal_screener_batch import SignalScreenerBatch
    from config.db import execute_update, execute_query
    import json

    screener = SignalScreenerBatch()
    result_df = screener.run_screener(output_csv=False)

    # Build signals list and add occurrence count
    signal_cols = ['stock_code', 'stock_name', 'signal_type', 'rps', 'close', 'ma20', 'ma250', 'volume_ratio']
    signals = []
    if result_df is not None and len(result_df) > 0:
        # Get recent 5-day occurrence counts for all signal stocks
        stock_codes = result_df['stock_code'].unique().tolist()
        occurrence_counts = _get_recent_occurrence_counts(stock_codes, days=5, env=env)

        available_cols = [c for c in signal_cols if c in result_df.columns]
        for _, row in result_df[available_cols].iterrows():
            record = {}
            for col in available_cols:
                val = row[col]
                if col in ('rps', 'close', 'ma20', 'ma250', 'volume_ratio'):
                    record[col] = _safe_float(val)
                else:
                    record[col] = '' if (val is None or (isinstance(val, float) and __import__('math').isnan(val))) else str(val)

            # Add occurrence count
            stock_code = record.get('stock_code', '')
            record['recent_occurrences'] = occurrence_counts.get(stock_code, 0)

            signals.append(record)

    signals_json = json.dumps(signals, ensure_ascii=False)

    # Compute counts
    signal_count = len(signals)
    momentum_count = sum(1 for s in signals if s.get('signal_type') == 'momentum')
    reversal_count = sum(1 for s in signals if s.get('signal_type') == 'reversal')

    # Market status from first signal row
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
        env=env,
    )
    logger.info('[CELERY] momentum_reversal run %s completed: %s signals', run_id, signal_count)

    return {
        'signal_count': signal_count,
        'momentum_count': momentum_count,
        'reversal_count': reversal_count,
    }


def _get_recent_occurrence_counts(stock_codes: list, days: int = 5, env: str = 'online') -> dict:
    """
    统计每只股票在最近N日(不含当日)的出现次数。
    stock codes are stored inside signals_json, so we use JSON_TABLE to extract them.

    Args:
        stock_codes: 股票代码列表
        days: 统计最近几天
        env: 数据库环境

    Returns:
        dict {stock_code: count}
    """
    if not stock_codes:
        return {}

    from config.db import execute_query

    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT sig.stock_code, COUNT(DISTINCT r.run_date) AS count
        FROM trade_preset_strategy_run r
        CROSS JOIN JSON_TABLE(
            r.signals_json,
            '$[*]' COLUMNS(
                stock_code VARCHAR(20) PATH '$.stock_code'
            )
        ) AS sig
        WHERE r.strategy_key = 'momentum_reversal'
          AND r.status = 'done'
          AND r.run_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
          AND r.run_date < CURDATE()
          AND sig.stock_code IN ({placeholders})
        GROUP BY sig.stock_code
    """
    try:
        rows = execute_query(sql, (days,) + tuple(stock_codes), env=env)
        return {row['stock_code']: row['count'] for row in rows}
    except Exception as e:
        logger.warning(f'[CELERY] Failed to get occurrence counts: {e}')
        return {}


def _run_microcap_pure_mv(run_id: int, env: str) -> dict:
    """Select microcap candidate stocks (pure_mv factor with financial filters)."""
    import os
    import sys

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from config.db import execute_update, execute_query as db_query
    import json

    # Get run_date from database record (set by trigger_strategy_run)
    run_date_rows = db_query(
        "SELECT run_date FROM trade_preset_strategy_run WHERE id = %s",
        (run_id,),
        env=env,
    )
    if not run_date_rows or not run_date_rows[0].get('run_date'):
        raise ValueError(f'No run_date found for run_id {run_id}')
    trade_date = str(run_date_rows[0]['run_date'])
    logger.info('[CELERY] microcap_pure_mv run %d: using trade_date %s', run_id, trade_date)

    # Get microcap universe: bottom 20% by market cap, financial risk filters
    from strategist.microcap.universe import get_daily_universe
    universe = get_daily_universe(
        trade_date=trade_date,
        percentile=0.20,
        exclude_st=True,
        require_positive_pe=False,
        min_avg_turnover=5_000_000.0,
        exclude_risk=True,
        max_debt_ratio=0.70,
        require_positive_profit=True,
        require_positive_cashflow=True,
        env=env,
    )

    if not universe:
        logger.warning('[CELERY] microcap_pure_mv: empty universe for %s', trade_date)
        execute_update(
            """
            UPDATE trade_preset_strategy_run
            SET status = 'done', signal_count = 0, momentum_count = 0, reversal_count = 0,
                market_status = '', market_message = %s, signals_json = '[]', finished_at = NOW()
            WHERE id = %s
            """,
            (f'no universe data for {trade_date}', run_id),
            env=env,
        )
        return {'signal_count': 0}

    # Fetch market cap and stock name, sort by total_mv ASC, take top 15
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
        env=env,
    )

    signals = []
    for row in (rows or []):
        signals.append({
            'stock_code': str(row['stock_code']),
            'stock_name': str(row.get('stock_name') or ''),
            'signal_type': 'microcap',
            'total_mv': _safe_float(row.get('total_mv')),
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
        env=env,
    )
    logger.info('[CELERY] microcap_pure_mv run %s completed: %s candidates for %s',
                run_id, signal_count, trade_date)

    return {'signal_count': signal_count}


def _safe_float(v):
    """Convert value to float, returning None for NaN/Inf."""
    try:
        import math
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None
