# -*- coding: utf-8 -*-
"""
Factor freshness guard -- checks that upstream data tables are fresh
enough before running downstream strategies.

Usage:
    from scheduler.freshness_guard import check_freshness, ensure_factors_fresh

    # Low-level check
    ok, issues = check_freshness([
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
    ])

    # High-level guard (raises on failure)
    ensure_factors_fresh('log_bias', env='online')
"""
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy -> required tables mapping
# ---------------------------------------------------------------------------
STRATEGY_REQUIREMENTS = {
    'log_bias': [
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
    ],
    'doctor_tao': [
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        {'table': 'trade_stock_rps', 'date_col': 'trade_date', 'max_lag': 2},
    ],
    'xgboost': [
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        {'table': 'trade_stock_basic_factor', 'date_col': 'calc_date', 'max_lag': 2},
    ],
    'universe_scan': [
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
        {'table': 'trade_stock_rps', 'date_col': 'trade_date', 'max_lag': 2},
    ],
    'theme_score': [
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
    ],
    'candidate_monitor': [
        {'table': 'trade_stock_daily', 'date_col': 'trade_date', 'max_lag': 1},
    ],
}

# Table -> callable path that can refresh it
FACTOR_TRIGGERS = {
    'trade_stock_basic_factor': 'data_analyst.factors.basic_factor_calculator.calculate_and_save_factors',
    'trade_stock_extended_factor': 'data_analyst.factors.extended_factor_calculator.main',
    'trade_stock_rps': 'data_analyst.indicators.rps_calculator.rps_daily_update',
}


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def check_freshness(requirements: list, env: str = 'online'):
    """
    Check whether each table's latest date is within max_lag calendar days
    of today.

    Args:
        requirements: list of dicts with keys: table, date_col, max_lag
        env: database environment

    Returns:
        (all_fresh: bool, issues: list[str])
    """
    from config.db import execute_query

    today = date.today()
    issues = []

    for req in requirements:
        table = req['table']
        date_col = req['date_col']
        max_lag = req['max_lag']

        sql = f"SELECT MAX({date_col}) as d FROM {table}"
        try:
            rows = execute_query(sql, env=env)
        except Exception as e:
            issues.append(f"{table}: query failed -- {e}")
            continue

        if not rows or rows[0]['d'] is None:
            issues.append(f"{table}: no data at all")
            continue

        latest = rows[0]['d']
        if hasattr(latest, 'date'):
            latest = latest.date()
        elif isinstance(latest, str):
            from datetime import datetime
            latest = datetime.strptime(str(latest)[:10], '%Y-%m-%d').date()

        lag = (today - latest).days
        if lag > max_lag:
            issues.append(
                f"{table}: latest={latest.isoformat()}, lag={lag}d > max_lag={max_lag}d"
            )

    return (len(issues) == 0, issues)


# ---------------------------------------------------------------------------
# Auto-trigger
# ---------------------------------------------------------------------------

def _try_trigger(table: str, env: str = 'online') -> bool:
    """
    Attempt to trigger the computation for a stale table.
    Returns True if the trigger was invoked (does not guarantee success).
    """
    trigger_path = FACTOR_TRIGGERS.get(table)
    if not trigger_path:
        return False

    module_path, func_name = trigger_path.rsplit('.', 1)
    logger.info("[freshness_guard] Triggering %s.%s for stale table %s",
                module_path, func_name, table)
    try:
        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        func()
        return True
    except Exception as e:
        logger.error("[freshness_guard] Trigger %s failed: %s", trigger_path, e)
        return False


def ensure_factors_fresh(strategy_name: str, env: str = 'online'):
    """
    Pre-flight check for a strategy. If data is stale, tries to trigger
    a refresh, then re-checks. Raises RuntimeError if still stale.

    Args:
        strategy_name: key in STRATEGY_REQUIREMENTS
        env: database environment

    Raises:
        ValueError: unknown strategy_name
        RuntimeError: data still stale after trigger attempt
    """
    reqs = STRATEGY_REQUIREMENTS.get(strategy_name)
    if reqs is None:
        raise ValueError(f"Unknown strategy '{strategy_name}' -- "
                         f"add it to STRATEGY_REQUIREMENTS in freshness_guard.py")

    ok, issues = check_freshness(reqs, env=env)
    if ok:
        logger.info("[freshness_guard] All data fresh for strategy '%s'",
                     strategy_name)
        return

    # Identify stale tables and try to trigger refresh
    stale_tables = set()
    for issue in issues:
        # Parse table name from issue string (first token before ':')
        table = issue.split(':')[0].strip()
        stale_tables.add(table)

    triggered_any = False
    for table in stale_tables:
        if _try_trigger(table, env=env):
            triggered_any = True

    if not triggered_any:
        raise RuntimeError(
            f"[freshness_guard] Strategy '{strategy_name}' blocked -- "
            f"data stale and no trigger available: {issues}"
        )

    # Re-check after trigger
    ok2, issues2 = check_freshness(reqs, env=env)
    if ok2:
        logger.info("[freshness_guard] Data refreshed, strategy '%s' ready",
                     strategy_name)
        return

    raise RuntimeError(
        f"[freshness_guard] Strategy '{strategy_name}' still blocked after "
        f"trigger attempt: {issues2}"
    )
