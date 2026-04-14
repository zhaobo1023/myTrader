# -*- coding: utf-8 -*-
"""ReportGenerator: generate daily/weekly/final performance reports."""

import json
import logging
import os
import sys
from datetime import date, timedelta
from typing import Optional

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.db import execute_query, execute_update
from strategist.sim_pool.config import SimPoolConfig

logger = logging.getLogger('myTrader.sim_pool')


class ReportGenerator:

    def __init__(self, config: Optional[SimPoolConfig] = None):
        self.config = config or SimPoolConfig()
        self._env = self.config.db_env

    # ------------------------------------------------------------------
    # Internal: build DataFrames for MetricsCalculator
    # ------------------------------------------------------------------

    def _build_daily_df(self, pool_id: int,
                        start_date: Optional[date] = None,
                        end_date: Optional[date] = None) -> pd.DataFrame:
        """Build daily_df [date, total_value] from sim_daily_nav."""
        wheres = ['pool_id=%s']
        params = [pool_id]
        if start_date:
            wheres.append('nav_date >= %s')
            params.append(start_date)
        if end_date:
            wheres.append('nav_date <= %s')
            params.append(end_date)
        rows = execute_query(
            f"SELECT nav_date AS date, total_value FROM sim_daily_nav WHERE {' AND '.join(wheres)} ORDER BY nav_date",
            tuple(params), env=self._env,
        )
        if not rows:
            return pd.DataFrame(columns=['date', 'total_value'])
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df['total_value'] = df['total_value'].astype(float)
        return df

    def _build_trades_df(self, pool_id: int) -> pd.DataFrame:
        """Build trades_df compatible with MetricsCalculator from sim_position."""
        rows = execute_query(
            """
            SELECT stock_code, entry_date AS date, exit_date,
                   net_return, exit_reason, status
            FROM sim_position
            WHERE pool_id=%s AND status='exited'
            """,
            (pool_id,), env=self._env,
        )
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # MetricsCalculator expects: date, stock_code, action, net_return, signal_type
        df['action'] = 'sell'
        df['signal_type'] = 'momentum'   # default; actual type in signal_meta
        df['net_return'] = df['net_return'].astype(float)
        return df

    def _build_benchmark_df(self, pool_id: int) -> Optional[pd.DataFrame]:
        """Build benchmark_df [date, close] from sim_daily_nav benchmark_close."""
        rows = execute_query(
            "SELECT nav_date AS date, benchmark_close AS close FROM sim_daily_nav WHERE pool_id=%s ORDER BY nav_date",
            (pool_id,), env=self._env,
        )
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df['close'] = pd.to_datetime(df['close'], errors='ignore')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        return df if not df.empty else None

    # ------------------------------------------------------------------
    # Public: generate reports
    # ------------------------------------------------------------------

    def _compute_metrics(
        self,
        pool_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        from strategist.backtest.metrics import MetricsCalculator

        pool_rows = execute_query(
            "SELECT initial_cash FROM sim_pool WHERE id=%s", (pool_id,), env=self._env
        )
        initial_cash = float(pool_rows[0]['initial_cash']) if pool_rows else 1_000_000.0

        daily_df = self._build_daily_df(pool_id, start_date, end_date)
        trades_df = self._build_trades_df(pool_id)
        benchmark_df = self._build_benchmark_df(pool_id)

        if daily_df.empty:
            return {'error': 'no nav data'}

        calc = MetricsCalculator()
        result = calc.calculate(
            daily_df=daily_df,
            trades_df=trades_df,
            initial_cash=initial_cash,
            benchmark_df=benchmark_df,
        )

        metrics = {
            'start_date': result.start_date,
            'end_date': result.end_date,
            'trading_days': result.trading_days,
            'initial_cash': result.initial_cash,
            'final_value': result.final_value,
            'total_return': result.total_return,
            'annual_return': result.annual_return,
            'benchmark_return': result.benchmark_return,
            'excess_return': result.excess_return,
            'max_drawdown': result.max_drawdown,
            'volatility': result.volatility,
            'sharpe_ratio': result.sharpe_ratio,
            'sortino_ratio': result.sortino_ratio,
            'calmar_ratio': result.calmar_ratio,
            'total_trades': result.total_trades,
            'win_trades': result.win_trades,
            'lose_trades': result.lose_trades,
            'win_rate': result.win_rate,
            'avg_return_per_trade': result.avg_return_per_trade,
            'avg_win': result.avg_win,
            'avg_loss': result.avg_loss,
            'profit_loss_ratio': result.profit_loss_ratio,
            'avg_hold_days': result.avg_hold_days,
        }
        return metrics

    def _persist_report(self, pool_id: int, report_date: date,
                        report_type: str, metrics: dict) -> None:
        date_str = report_date.isoformat() if isinstance(report_date, date) else report_date
        execute_update(
            """
            INSERT INTO sim_report (pool_id, report_date, report_type, metrics)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE metrics=VALUES(metrics)
            """,
            (pool_id, date_str, report_type,
             json.dumps(metrics, ensure_ascii=False, default=str)),
            env=self._env,
        )

    def generate_daily_report(self, pool_id: int, report_date: date) -> dict:
        """Generate and persist daily report for pool up to report_date."""
        metrics = self._compute_metrics(pool_id, end_date=report_date)
        self._persist_report(pool_id, report_date, 'daily', metrics)
        logger.info('[ReportGenerator] pool %d daily report %s done', pool_id, report_date)
        return metrics

    def generate_weekly_report(self, pool_id: int, week_end_date: date) -> dict:
        """Generate weekly report covering Mon-Fri of week_end_date's week."""
        # week_end_date is Friday; start is Monday
        week_start = week_end_date - timedelta(days=week_end_date.weekday())
        metrics = self._compute_metrics(pool_id, start_date=week_start, end_date=week_end_date)
        metrics['week_start'] = week_start.isoformat()
        metrics['week_end'] = week_end_date.isoformat()
        self._persist_report(pool_id, week_end_date, 'weekly', metrics)
        logger.info('[ReportGenerator] pool %d weekly report %s done', pool_id, week_end_date)
        return metrics

    def generate_final_report(self, pool_id: int) -> dict:
        """Generate final report after pool closes. Includes per-stock breakdown."""
        metrics = self._compute_metrics(pool_id)

        # Position contribution breakdown
        pos_rows = execute_query(
            """
            SELECT stock_code, stock_name, net_return, exit_reason, entry_date, exit_date
            FROM sim_position WHERE pool_id=%s AND status='exited'
            ORDER BY net_return DESC
            """,
            (pool_id,), env=self._env,
        )
        contributions = [
            {
                'stock_code': r['stock_code'],
                'stock_name': r['stock_name'],
                'net_return': float(r['net_return'] or 0),
                'exit_reason': r['exit_reason'],
                'entry_date': str(r['entry_date']),
                'exit_date': str(r['exit_date']),
            }
            for r in pos_rows
        ]
        metrics['position_contributions'] = contributions

        # Exit reason breakdown
        reason_counts = {}
        for p in pos_rows:
            reason = p['exit_reason'] or 'unknown'
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        metrics['exit_breakdown'] = reason_counts

        today = date.today()
        self._persist_report(pool_id, today, 'final', metrics)
        logger.info('[ReportGenerator] pool %d final report done', pool_id)
        return metrics

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_report(self, pool_id: int, report_date: date, report_type: str) -> Optional[dict]:
        date_str = report_date.isoformat() if isinstance(report_date, date) else report_date
        rows = execute_query(
            "SELECT * FROM sim_report WHERE pool_id=%s AND report_date=%s AND report_type=%s",
            (pool_id, date_str, report_type), env=self._env,
        )
        if not rows:
            return None
        r = dict(rows[0])
        if r.get('metrics'):
            try:
                r['metrics'] = json.loads(r['metrics'])
            except Exception:
                pass
        return r

    def list_reports(self, pool_id: int, report_type: Optional[str] = None) -> list:
        wheres = ['pool_id=%s']
        params = [pool_id]
        if report_type:
            wheres.append('report_type=%s')
            params.append(report_type)
        rows = execute_query(
            f"SELECT id, pool_id, report_date, report_type, created_at FROM sim_report WHERE {' AND '.join(wheres)} ORDER BY report_date DESC",
            tuple(params), env=self._env,
        )
        return [dict(r) for r in rows]
