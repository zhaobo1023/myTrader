# -*- coding: utf-8 -*-
"""PoolManager: create, query and close sim pools."""

import json
import logging
import math
import os
import sys
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.db import execute_query, execute_update
from strategist.sim_pool.config import SimPoolConfig

logger = logging.getLogger('myTrader.sim_pool')


class PoolManager:

    def __init__(self, config: Optional[SimPoolConfig] = None):
        self.config = config or SimPoolConfig()
        self._env = self.config.db_env

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_pool(
        self,
        strategy_id: int,
        strategy_type: str,
        name: str,
        signal_date: date,
        signals_df: pd.DataFrame,
        config: Optional[SimPoolConfig] = None,
        user_id: Optional[int] = None,
    ) -> int:
        """
        Write sim_pool (pending) + sim_position * N (pending).

        Args:
            strategy_id:    FK to strategies table
            strategy_type:  'momentum' | 'industry' | 'micro_cap' | 'custom'
            name:           Pool display name
            signal_date:    Date the screener was run
            signals_df:     Must have columns: stock_code, stock_name
                            Optional: signal_meta (JSON string)
            config:         Override default config
            user_id:        Owner user id

        Returns:
            pool_id (int)
        """
        cfg = config or self.config
        env = cfg.db_env

        # Cap positions
        if len(signals_df) > cfg.max_positions:
            signals_df = signals_df.head(cfg.max_positions).copy()

        n = len(signals_df)
        if n == 0:
            raise ValueError('signals_df is empty, cannot create pool')

        weight = round(1.0 / n, 6)

        # Insert sim_pool
        execute_update(
            """
            INSERT INTO sim_pool
                (strategy_id, strategy_type, name, signal_date, initial_cash,
                 status, stock_count, benchmark_code, params, user_id)
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s)
            """,
            (
                strategy_id,
                strategy_type,
                name,
                signal_date.isoformat() if isinstance(signal_date, date) else signal_date,
                cfg.initial_cash,
                n,
                cfg.benchmark_code,
                json.dumps(cfg.to_dict()),
                user_id,
            ),
            env=env,
        )

        # Fetch pool_id
        rows = execute_query(
            "SELECT id FROM sim_pool WHERE strategy_id=%s AND name=%s ORDER BY id DESC LIMIT 1",
            (strategy_id, name),
            env=env,
        )
        if not rows:
            raise RuntimeError('Failed to retrieve pool_id after insert')
        pool_id = rows[0]['id']

        # Insert sim_position rows
        for _, row in signals_df.iterrows():
            meta = row.get('signal_meta', None)
            if isinstance(meta, dict):
                meta = json.dumps(meta, ensure_ascii=False)
            execute_update(
                """
                INSERT INTO sim_position
                    (pool_id, stock_code, stock_name, weight, status, signal_meta)
                VALUES (%s, %s, %s, %s, 'pending', %s)
                """,
                (pool_id, row['stock_code'], row.get('stock_name', ''), weight, meta),
                env=env,
            )

        logger.info('[PoolManager] created pool %d: %s (%d stocks)', pool_id, name, n)
        return pool_id

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_pool(self, pool_id: int) -> Optional[dict]:
        """Return pool dict with 'positions' list attached."""
        rows = execute_query(
            "SELECT * FROM sim_pool WHERE id=%s",
            (pool_id,),
            env=self._env,
        )
        if not rows:
            return None
        pool = dict(rows[0])
        if pool.get('params'):
            try:
                pool['params'] = json.loads(pool['params'])
            except Exception:
                pass

        pool['positions'] = self.get_positions(pool_id)
        return pool

    def list_pools(
        self,
        strategy_id: Optional[int] = None,
        strategy_type: Optional[str] = None,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[dict]:
        """Query pool list with optional filters."""
        wheres = []
        params = []
        if strategy_id is not None:
            wheres.append('strategy_id=%s')
            params.append(strategy_id)
        if strategy_type:
            wheres.append('strategy_type=%s')
            params.append(strategy_type)
        if status:
            wheres.append('status=%s')
            params.append(status)
        if user_id is not None:
            wheres.append('user_id=%s')
            params.append(user_id)
        params.append(limit)
        where_sql = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
        sql = f"SELECT * FROM sim_pool {where_sql} ORDER BY id DESC LIMIT %s"
        rows = execute_query(sql, tuple(params), env=self._env)
        result = []
        for r in rows:
            d = dict(r)
            if d.get('params'):
                try:
                    d['params'] = json.loads(d['params'])
                except Exception:
                    pass
            result.append(d)
        return result

    def get_positions(self, pool_id: int, status: Optional[str] = None) -> List[dict]:
        """Return positions for a pool."""
        wheres = ['pool_id=%s']
        params = [pool_id]
        if status:
            wheres.append('status=%s')
            params.append(status)
        sql = f"SELECT * FROM sim_position WHERE {' AND '.join(wheres)} ORDER BY id"
        rows = execute_query(sql, tuple(params), env=self._env)
        result = []
        for r in rows:
            d = dict(r)
            if d.get('signal_meta'):
                try:
                    d['signal_meta'] = json.loads(d['signal_meta'])
                except Exception:
                    pass
            result.append(d)
        return result

    # ------------------------------------------------------------------
    # Update metrics summary
    # ------------------------------------------------------------------

    def update_pool_metrics(self, pool_id: int, metrics: dict) -> None:
        """Write performance summary fields back to sim_pool."""
        execute_update(
            """
            UPDATE sim_pool SET
                total_return=%s, benchmark_return=%s,
                max_drawdown=%s, sharpe_ratio=%s, win_rate=%s
            WHERE id=%s
            """,
            (
                metrics.get('total_return'),
                metrics.get('benchmark_return'),
                metrics.get('max_drawdown'),
                metrics.get('sharpe_ratio'),
                metrics.get('win_rate'),
                pool_id,
            ),
            env=self._env,
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close_pool(self, pool_id: int, reason: str = 'manual') -> None:
        """
        Force-close pool: mark remaining active positions as exited
        with exit_reason=reason, set pool status=closed.
        Note: does not fill exit_price (caller should call PositionTracker first).
        """
        execute_update(
            """
            UPDATE sim_position
            SET status='exited', exit_reason=%s, exit_date=CURDATE()
            WHERE pool_id=%s AND status='active'
            """,
            (reason, pool_id),
            env=self._env,
        )
        execute_update(
            "UPDATE sim_pool SET status='closed', closed_at=NOW() WHERE id=%s",
            (pool_id,),
            env=self._env,
        )
        logger.info('[PoolManager] pool %d closed (reason=%s)', pool_id, reason)
