# -*- coding: utf-8 -*-
"""Celery tasks for Strategy Simulation Pool (SimPool)."""

import logging
from datetime import date, timedelta

from api.tasks.celery_app import celery_app
from config.db import execute_query

logger = logging.getLogger('myTrader.sim_pool')


def _is_trading_day(check_date: date, env: str = 'online') -> bool:
    """Check if check_date is a trading day by querying trade_stock_daily."""
    rows = execute_query(
        "SELECT COUNT(*) AS cnt FROM trade_stock_daily WHERE trade_date=%s LIMIT 1",
        (check_date.strftime('%Y-%m-%d'),), env=env,
    )
    return bool(rows and rows[0]['cnt'] > 0)


# ------------------------------------------------------------------
# T2.5: Create pool from strategy signals (triggered by API endpoint)
# ------------------------------------------------------------------

@celery_app.task(bind=True, name='tasks.create_sim_pool', max_retries=2)
def create_sim_pool_task(self, strategy_type: str, signal_date: str,
                         config_dict: dict, user_id: int):
    """
    1. Instantiate StrategyAdapter by strategy_type
    2. Run adapter.run(signal_date, params) -> signals DataFrame
    3. Call PoolManager.create_pool() -> pool_id
    4. Return pool_id
    """
    try:
        from strategist.sim_pool.strategies.momentum import MomentumAdapter
        from strategist.sim_pool.strategies.industry import IndustryAdapter
        from strategist.sim_pool.strategies.micro_cap import MicroCapAdapter
        from strategist.sim_pool.pool_manager import PoolManager
        from strategist.sim_pool.config import SimPoolConfig

        adapters = {
            'momentum': MomentumAdapter,
            'industry': IndustryAdapter,
            'micro_cap': MicroCapAdapter,
        }
        if strategy_type not in adapters:
            raise ValueError(f'Unknown strategy_type: {strategy_type}')

        adapter = adapters[strategy_type]()
        params = config_dict.get('strategy_params', {})
        signals_df = adapter.run(signal_date=signal_date, params=params)

        if signals_df is None or signals_df.empty:
            logger.warning('[create_sim_pool] No signals on %s for %s', signal_date, strategy_type)
            return {'pool_id': None, 'reason': 'no_signals'}

        sim_config = SimPoolConfig.from_dict(config_dict)
        mgr = PoolManager(sim_config)
        pool_id = mgr.create_pool(
            strategy_type=strategy_type,
            signal_date=signal_date,
            signals_df=signals_df,
            user_id=user_id,
        )
        logger.info('[create_sim_pool] Created pool %d for %s on %s', pool_id, strategy_type, signal_date)
        return {'pool_id': pool_id, 'signal_count': len(signals_df)}

    except Exception as exc:
        logger.exception('[create_sim_pool] Failed: %s', exc)
        raise self.retry(exc=exc, countdown=60)


# ------------------------------------------------------------------
# T2.5: Fill entry prices on T+1 open (09:35 every trading day)
# ------------------------------------------------------------------

@celery_app.task(bind=True, name='tasks.fill_entry_prices', max_retries=1)
def fill_entry_prices_task(self):
    """
    Every trading day at 09:35.
    For all pools in status='pending': confirm today is trading day,
    then call PositionTracker.fill_entry_prices(today).
    """
    try:
        from strategist.sim_pool.position_tracker import PositionTracker
        from strategist.sim_pool.config import SimPoolConfig

        today = date.today()
        env = SimPoolConfig().db_env

        if not _is_trading_day(today, env=env):
            logger.info('[fill_entry_prices] %s is not a trading day, skip', today)
            return {'skipped': True, 'reason': 'not_trading_day'}

        pending_pools = execute_query(
            "SELECT id FROM sim_pool WHERE status='pending'",
            env=env,
        )
        if not pending_pools:
            return {'filled': 0}

        tracker = PositionTracker()
        filled_count = 0
        for row in pending_pools:
            pool_id = row['id']
            try:
                tracker.fill_entry_prices(pool_id=pool_id, entry_date=today)
                filled_count += 1
                logger.info('[fill_entry_prices] pool %d filled on %s', pool_id, today)
            except Exception as e:
                logger.error('[fill_entry_prices] pool %d error: %s', pool_id, e)

        return {'filled': filled_count, 'date': today.isoformat()}

    except Exception as exc:
        logger.exception('[fill_entry_prices] Failed: %s', exc)
        raise self.retry(exc=exc, countdown=120)


# ------------------------------------------------------------------
# T2.5: Daily update for all active pools (16:30 every trading day)
# ------------------------------------------------------------------

@celery_app.task(bind=True, name='tasks.daily_sim_pool_update', max_retries=1)
def daily_sim_pool_update_task(self):
    """
    Every trading day at 16:30.
    For each active pool:
      1. update_prices(today)
      2. check_exits(today)
      3. calculate_daily_nav(today)
      4. generate_daily_report(pool_id, today)
      5. if Friday -> generate_weekly_report
      6. if all positions exited -> generate_final_report + close pool
    """
    try:
        from strategist.sim_pool.position_tracker import PositionTracker
        from strategist.sim_pool.nav_calculator import NavCalculator
        from strategist.sim_pool.report_generator import ReportGenerator
        from strategist.sim_pool.pool_manager import PoolManager
        from strategist.sim_pool.config import SimPoolConfig

        today = date.today()
        env = SimPoolConfig().db_env

        if not _is_trading_day(today, env=env):
            logger.info('[daily_update] %s is not a trading day, skip', today)
            return {'skipped': True, 'reason': 'not_trading_day'}

        is_friday = today.weekday() == 4

        active_pools = execute_query(
            "SELECT id FROM sim_pool WHERE status='active'",
            env=env,
        )
        if not active_pools:
            return {'updated': 0}

        tracker = PositionTracker()
        nav_calc = NavCalculator()
        reporter = ReportGenerator()
        mgr = PoolManager()
        results = []

        for row in active_pools:
            pool_id = row['id']
            try:
                # 1. Update prices (marks suspended days)
                tracker.update_prices(pool_id=pool_id, price_date=today)

                # 2. Force-exit long-suspended positions
                suspended_exits = tracker.handle_suspended(pool_id=pool_id, price_date=today)

                # 3. Check and execute normal exits (stop_loss / take_profit / max_hold)
                exit_summary = tracker.check_exits(pool_id=pool_id, price_date=today)
                exit_summary = list(exit_summary) + suspended_exits

                # 3. Calculate NAV
                nav_calc.calculate_daily_nav(pool_id=pool_id, nav_date=today)

                # 4. Daily report
                reporter.generate_daily_report(pool_id=pool_id, report_date=today)

                # 5. Weekly report on Friday
                if is_friday:
                    reporter.generate_weekly_report(pool_id=pool_id, week_end_date=today)

                # 6. Check if all positions exited
                open_positions = execute_query(
                    "SELECT COUNT(*) AS cnt FROM sim_position WHERE pool_id=%s AND status='open'",
                    (pool_id,), env=env,
                )
                all_exited = not open_positions or open_positions[0]['cnt'] == 0

                if all_exited:
                    reporter.generate_final_report(pool_id=pool_id)
                    mgr.close_pool(pool_id=pool_id)
                    logger.info('[daily_update] pool %d closed (all positions exited)', pool_id)

                results.append({'pool_id': pool_id, 'exits': exit_summary, 'closed': all_exited})

            except Exception as e:
                logger.error('[daily_update] pool %d error: %s', pool_id, e)
                results.append({'pool_id': pool_id, 'error': str(e)})

        return {'updated': len(active_pools), 'date': today.isoformat(), 'results': results}

    except Exception as exc:
        logger.exception('[daily_update] Failed: %s', exc)
        raise self.retry(exc=exc, countdown=120)
