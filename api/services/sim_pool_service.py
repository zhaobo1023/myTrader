# -*- coding: utf-8 -*-
"""Service layer for Strategy Simulation Pool (SimPool)."""

import logging
from datetime import date
from typing import Optional

from config.db import execute_query
from strategist.sim_pool.config import SimPoolConfig

logger = logging.getLogger('myTrader.sim_pool')


class SimPoolService:
    """Business logic layer between API router and sim_pool engine."""

    def __init__(self):
        self._config = SimPoolConfig()
        self._env = self._config.db_env

    # ------------------------------------------------------------------
    # Pool CRUD
    # ------------------------------------------------------------------

    def list_pools(self, user_id: Optional[int] = None,
                   strategy_type: Optional[str] = None,
                   status: Optional[str] = None) -> list:
        wheres = []
        params = []
        if user_id is not None:
            wheres.append('user_id=%s')
            params.append(user_id)
        if strategy_type:
            wheres.append('strategy_type=%s')
            params.append(strategy_type)
        if status:
            wheres.append('status=%s')
            params.append(status)

        where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
        rows = execute_query(
            f"""
            SELECT id, strategy_type, signal_date, status, initial_cash,
                   current_value, total_return, max_drawdown, sharpe_ratio,
                   created_at, closed_at
            FROM sim_pool {where_clause}
            ORDER BY created_at DESC
            """,
            tuple(params), env=self._env,
        )
        return [dict(r) for r in rows]

    def get_pool(self, pool_id: int) -> Optional[dict]:
        from strategist.sim_pool.pool_manager import PoolManager
        return PoolManager().get_pool(pool_id)

    def get_positions(self, pool_id: int, status: Optional[str] = None) -> list:
        from strategist.sim_pool.pool_manager import PoolManager
        return PoolManager().get_positions(pool_id, status=status)

    def get_nav_series(self, pool_id: int,
                       start_date: Optional[date] = None,
                       end_date: Optional[date] = None) -> list:
        from strategist.sim_pool.nav_calculator import NavCalculator
        series = NavCalculator().get_nav_series(pool_id)
        if start_date:
            series = [r for r in series if str(r.get('nav_date', '')) >= start_date.isoformat()]
        if end_date:
            series = [r for r in series if str(r.get('nav_date', '')) <= end_date.isoformat()]
        return series

    def get_benchmark_nav_series(self, pool_id: int) -> list:
        from strategist.sim_pool.nav_calculator import NavCalculator
        from datetime import date, timedelta
        # Use full date range from pool creation to today
        pool = self.get_pool(pool_id)
        if not pool:
            return []
        start = date.fromisoformat(str(pool.get('signal_date', ''))[:10]) if pool.get('signal_date') else date.today() - timedelta(days=365)
        end = date.today()
        return NavCalculator().get_benchmark_nav_series(pool_id, start_date=start, end_date=end)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def list_reports(self, pool_id: int, report_type: Optional[str] = None) -> list:
        from strategist.sim_pool.report_generator import ReportGenerator
        return ReportGenerator().list_reports(pool_id, report_type=report_type)

    def get_report(self, pool_id: int, report_date: date, report_type: str) -> Optional[dict]:
        from strategist.sim_pool.report_generator import ReportGenerator
        return ReportGenerator().get_report(pool_id, report_date, report_type)

    def get_trade_log(self, pool_id: int) -> list:
        rows = execute_query(
            """
            SELECT id, pool_id, position_id, stock_code, trade_date, action,
                   price, shares, amount, commission, slippage_cost, stamp_tax,
                   net_amount, trigger, created_at
            FROM sim_trade_log WHERE pool_id=%s ORDER BY trade_date, id
            """,
            (pool_id,), env=self._env,
        )
        return [dict(r) for r in rows]

    def force_close_pool(self, pool_id: int) -> None:
        """Force-exit all open positions at current price then close pool."""
        from strategist.sim_pool.position_tracker import PositionTracker
        from strategist.sim_pool.pool_manager import PoolManager
        from strategist.sim_pool.report_generator import ReportGenerator
        from datetime import date
        today = date.today()
        tracker = PositionTracker()
        # handle_suspended covers price-unknown positions; check_exits won't fire
        # since no condition is met — so we use close_pool directly which just
        # marks remaining actives as exited without computing sell costs.
        PoolManager().close_pool(pool_id, reason='manual')
        ReportGenerator().generate_final_report(pool_id)

    # ------------------------------------------------------------------
    # Trigger (async via Celery)
    # ------------------------------------------------------------------

    def trigger_create_pool(self, strategy_type: str, signal_date: str,
                            config_dict: dict, user_id: int) -> str:
        """Dispatch Celery task and return task_id."""
        from api.tasks.sim_pool_tasks import create_sim_pool_task
        task = create_sim_pool_task.delay(
            strategy_type=strategy_type,
            signal_date=signal_date,
            config_dict=config_dict,
            user_id=user_id,
        )
        return task.id

    def get_task_result(self, task_id: str) -> dict:
        from celery.result import AsyncResult
        result = AsyncResult(task_id)
        return {
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
        }
