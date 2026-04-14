# -*- coding: utf-8 -*-
"""NavCalculator: compute daily NAV, drawdown, benchmark comparison."""

import logging
import os
import sys
from datetime import date
from typing import List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.db import execute_query, execute_update
from strategist.sim_pool.config import SimPoolConfig

logger = logging.getLogger('myTrader.sim_pool')


class NavCalculator:

    def __init__(self, config: Optional[SimPoolConfig] = None):
        self.config = config or SimPoolConfig()
        self._env = self.config.db_env

    # ------------------------------------------------------------------
    # Daily NAV calculation
    # ------------------------------------------------------------------

    def calculate_daily_nav(self, pool_id: int, nav_date: date) -> Optional[dict]:
        """
        Compute and persist today's NAV.

        portfolio_value = sum(active_position.shares * current_price)
        cash = initial_cash - sum(entry_cost) + sum(net_proceeds from exits today)
        nav = total_value / initial_cash
        drawdown = (nav - peak_nav) / peak_nav

        Returns nav dict or None on error.
        """
        import json
        date_str = nav_date.isoformat() if isinstance(nav_date, date) else nav_date

        pool_rows = execute_query(
            "SELECT initial_cash, params FROM sim_pool WHERE id=%s", (pool_id,), env=self._env
        )
        if not pool_rows:
            return None
        pool = pool_rows[0]
        initial_cash = float(pool['initial_cash'])
        cfg = self.config
        if pool.get('params'):
            try:
                cfg = SimPoolConfig.from_dict(json.loads(pool['params']))
            except Exception:
                pass

        # Active positions market value
        active_pos = execute_query(
            """
            SELECT shares, current_price, entry_cost
            FROM sim_position WHERE pool_id=%s AND status='active'
            """,
            (pool_id,), env=self._env,
        )
        portfolio_value = sum(
            float(p['shares'] or 0) * float(p['current_price'] or 0)
            for p in active_pos
        )
        total_entry_cost = sum(float(p['entry_cost'] or 0) for p in active_pos)

        # Cash = initial_cash - all buy costs + all sell proceeds (from trade_log)
        buy_rows = execute_query(
            "SELECT SUM(entry_cost) AS total FROM sim_position WHERE pool_id=%s AND status IN ('active','exited')",
            (pool_id,), env=self._env,
        )
        total_buy_cost = float((buy_rows[0]['total'] or 0)) if buy_rows else 0

        sell_rows = execute_query(
            "SELECT SUM(net_amount) AS total FROM sim_trade_log WHERE pool_id=%s AND action='sell'",
            (pool_id,), env=self._env,
        )
        total_sell_proceeds = float((sell_rows[0]['total'] or 0)) if sell_rows else 0

        cash = initial_cash - total_buy_cost + total_sell_proceeds
        total_value = portfolio_value + cash
        nav = total_value / initial_cash if initial_cash > 0 else 1.0

        # Drawdown: compare to historical peak nav
        prev_rows = execute_query(
            "SELECT MAX(nav) AS peak FROM sim_daily_nav WHERE pool_id=%s",
            (pool_id,), env=self._env,
        )
        peak_nav = float((prev_rows[0]['peak'] or 1.0)) if prev_rows else 1.0
        peak_nav = max(peak_nav, nav)  # today may be new high
        drawdown = (nav - peak_nav) / peak_nav if peak_nav > 0 else 0.0

        # Daily return
        prev_nav_rows = execute_query(
            "SELECT nav FROM sim_daily_nav WHERE pool_id=%s ORDER BY nav_date DESC LIMIT 1",
            (pool_id,), env=self._env,
        )
        prev_nav = float(prev_nav_rows[0]['nav']) if prev_nav_rows else 1.0
        daily_return = (nav - prev_nav) / prev_nav if prev_nav > 0 else 0.0

        # Benchmark
        benchmark_code = cfg.benchmark_code
        bm_close, bm_nav = self._get_benchmark_nav(pool_id, benchmark_code, nav_date)

        # Active count
        active_count = len(active_pos)

        # Upsert sim_daily_nav
        execute_update(
            """
            INSERT INTO sim_daily_nav
                (pool_id, nav_date, portfolio_value, cash, total_value,
                 nav, daily_return, benchmark_close, benchmark_nav,
                 drawdown, active_positions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                portfolio_value=VALUES(portfolio_value),
                cash=VALUES(cash),
                total_value=VALUES(total_value),
                nav=VALUES(nav),
                daily_return=VALUES(daily_return),
                benchmark_close=VALUES(benchmark_close),
                benchmark_nav=VALUES(benchmark_nav),
                drawdown=VALUES(drawdown),
                active_positions=VALUES(active_positions)
            """,
            (
                pool_id, date_str,
                round(portfolio_value, 2), round(cash, 2), round(total_value, 2),
                round(nav, 6), round(daily_return, 6),
                bm_close, round(bm_nav, 6),
                round(drawdown, 6), active_count,
            ),
            env=self._env,
        )

        result = {
            'pool_id': pool_id,
            'nav_date': date_str,
            'portfolio_value': round(portfolio_value, 2),
            'cash': round(cash, 2),
            'total_value': round(total_value, 2),
            'nav': round(nav, 6),
            'daily_return': round(daily_return, 6),
            'benchmark_nav': round(bm_nav, 6),
            'drawdown': round(drawdown, 6),
            'active_positions': active_count,
        }
        logger.info('[NavCalculator] pool %d nav on %s: %.4f (dd=%.2f%%)',
                    pool_id, date_str, nav, drawdown * 100)
        return result

    # ------------------------------------------------------------------
    # Benchmark helpers
    # ------------------------------------------------------------------

    def _get_benchmark_nav(
        self, pool_id: int, benchmark_code: str, nav_date: date
    ) -> tuple:
        """
        Return (benchmark_close, benchmark_nav).
        benchmark_nav = today_close / first_close (base=1.0 on pool entry_date).
        """
        date_str = nav_date.isoformat() if isinstance(nav_date, date) else nav_date
        bare = benchmark_code.split('.')[0] if '.' in benchmark_code else benchmark_code

        close_rows = execute_query(
            """
            SELECT close FROM trade_stock_daily
            WHERE trade_date=%s
              AND (stock_code=%s OR stock_code=%s OR SUBSTRING_INDEX(stock_code,'.',1)=%s)
            LIMIT 1
            """,
            (date_str, benchmark_code, bare, bare),
            env=self._env,
        )
        if not close_rows or close_rows[0]['close'] is None:
            return None, 1.0
        today_close = float(close_rows[0]['close'])

        # First close: pool entry_date benchmark close
        pool_rows = execute_query(
            "SELECT entry_date FROM sim_pool WHERE id=%s", (pool_id,), env=self._env
        )
        if not pool_rows or not pool_rows[0].get('entry_date'):
            return today_close, 1.0
        entry_date = pool_rows[0]['entry_date']

        first_rows = execute_query(
            """
            SELECT close FROM trade_stock_daily
            WHERE trade_date=%s
              AND (stock_code=%s OR stock_code=%s OR SUBSTRING_INDEX(stock_code,'.',1)=%s)
            LIMIT 1
            """,
            (entry_date, benchmark_code, bare, bare),
            env=self._env,
        )
        if not first_rows or first_rows[0]['close'] is None:
            return today_close, 1.0
        first_close = float(first_rows[0]['close'])
        bm_nav = today_close / first_close if first_close > 0 else 1.0
        return today_close, bm_nav

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_nav_series(self, pool_id: int) -> List[dict]:
        """Return full NAV series ordered by date."""
        rows = execute_query(
            """
            SELECT nav_date, nav, benchmark_nav, daily_return, drawdown, active_positions
            FROM sim_daily_nav WHERE pool_id=%s ORDER BY nav_date
            """,
            (pool_id,), env=self._env,
        )
        return [dict(r) for r in rows]

    def get_benchmark_nav_series(
        self, pool_id: int, start_date: date, end_date: date
    ) -> List[dict]:
        """Return benchmark close price series for date range."""
        import json
        pool_rows = execute_query(
            "SELECT benchmark_code FROM sim_pool WHERE id=%s", (pool_id,), env=self._env
        )
        if not pool_rows:
            return []
        bm_code = pool_rows[0].get('benchmark_code') or self.config.benchmark_code
        bare = bm_code.split('.')[0] if '.' in bm_code else bm_code
        rows = execute_query(
            """
            SELECT trade_date, close FROM trade_stock_daily
            WHERE trade_date BETWEEN %s AND %s
              AND (stock_code=%s OR SUBSTRING_INDEX(stock_code,'.',1)=%s)
            ORDER BY trade_date
            """,
            (start_date, end_date, bm_code, bare),
            env=self._env,
        )
        return [dict(r) for r in rows]
