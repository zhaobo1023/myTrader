# -*- coding: utf-8 -*-
"""PositionTracker: fill entry prices, update prices, check exit conditions."""

import logging
import math
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


class PositionTracker:

    def __init__(self, config: Optional[SimPoolConfig] = None):
        self.config = config or SimPoolConfig()
        self._env = self.config.db_env

    # ------------------------------------------------------------------
    # Fetch prices from trade_stock_daily
    # ------------------------------------------------------------------

    def _get_close_prices(self, stock_codes: List[str], trade_date: date) -> dict:
        """Return {stock_code: close_price} for given date.
        stock_code in DB is 'XXXXXX.SH' or 'XXXXXX.SZ'; input may be bare 6-digit."""
        if not stock_codes:
            return {}
        date_str = trade_date.isoformat() if isinstance(trade_date, date) else trade_date
        placeholders = ','.join(['%s'] * len(stock_codes))
        # Try both bare and suffixed codes
        bare_codes = [c.split('.')[0] if '.' in c else c for c in stock_codes]
        rows = execute_query(
            f"""
            SELECT stock_code, close FROM trade_stock_daily
            WHERE trade_date=%s
              AND (stock_code IN ({placeholders})
                OR SUBSTRING_INDEX(stock_code, '.', 1) IN ({placeholders}))
            """,
            tuple([date_str] + stock_codes + bare_codes),
            env=self._env,
        )
        result = {}
        for r in rows:
            full = r['stock_code']
            bare = full.split('.')[0] if '.' in full else full
            close = float(r['close']) if r['close'] is not None else None
            result[full] = close
            result[bare] = close
        return result

    def _is_trading_day(self, check_date: date) -> bool:
        """Return True if trade_stock_daily has any record for this date."""
        date_str = check_date.isoformat() if isinstance(check_date, date) else check_date
        rows = execute_query(
            "SELECT 1 FROM trade_stock_daily WHERE trade_date=%s LIMIT 1",
            (date_str,),
            env=self._env,
        )
        return bool(rows)

    # ------------------------------------------------------------------
    # T1.4a  fill_entry_prices
    # ------------------------------------------------------------------

    def fill_entry_prices(self, pool_id: int, entry_date: date) -> int:
        """
        Fill T+1 buy prices for all pending positions in the pool.

        Buy price = close * (1 + slippage)
        Commission = amount * commission_rate
        Shares = floor(cash_alloc / buy_price / 100) * 100  (round lot)
        entry_cost = shares * buy_price + commission

        Returns number of positions successfully filled.
        """
        cfg = self.config

        # Load pool to get initial_cash and params
        pool_rows = execute_query(
            "SELECT id, initial_cash, params FROM sim_pool WHERE id=%s", (pool_id,), env=self._env
        )
        if not pool_rows:
            logger.error('[PositionTracker] pool %d not found', pool_id)
            return 0
        import json
        pool = pool_rows[0]
        if pool.get('params'):
            try:
                p = json.loads(pool['params'])
                cfg = SimPoolConfig.from_dict(p)
            except Exception:
                pass
        initial_cash = float(pool['initial_cash'])

        # Load pending positions
        positions = execute_query(
            "SELECT * FROM sim_position WHERE pool_id=%s AND status='pending'",
            (pool_id,),
            env=self._env,
        )
        if not positions:
            logger.info('[PositionTracker] pool %d: no pending positions', pool_id)
            return 0

        codes = [p['stock_code'] for p in positions]
        prices = self._get_close_prices(codes, entry_date)

        filled = 0
        date_str = entry_date.isoformat() if isinstance(entry_date, date) else entry_date

        for pos in positions:
            code = pos['stock_code']
            bare = code.split('.')[0] if '.' in code else code
            close = prices.get(code) or prices.get(bare)

            if close is None or close <= 0:
                logger.warning('[PositionTracker] no price for %s on %s', code, date_str)
                continue

            weight = float(pos['weight'])
            cash_alloc = initial_cash * weight

            # Buy price includes slippage (pay more when buying)
            buy_price = close * (1 + cfg.slippage)
            # Round-lot shares (multiple of 100)
            raw_shares = cash_alloc / buy_price
            shares = math.floor(raw_shares / 100) * 100
            if shares <= 0:
                logger.warning('[PositionTracker] %s: not enough cash for 1 lot', code)
                continue

            amount = shares * buy_price
            commission = amount * cfg.commission
            entry_cost = amount + commission
            slippage_cost = shares * close * cfg.slippage

            # Update sim_position
            execute_update(
                """
                UPDATE sim_position SET
                    entry_price=%s, entry_date=%s, shares=%s,
                    entry_cost=%s, current_price=%s, status='active'
                WHERE id=%s
                """,
                (close, date_str, shares, entry_cost, close, pos['id']),
                env=self._env,
            )

            # Write trade log
            execute_update(
                """
                INSERT INTO sim_trade_log
                    (pool_id, position_id, stock_code, trade_date, action,
                     price, shares, amount, commission, slippage_cost,
                     stamp_tax, net_amount, trigger)
                VALUES (%s, %s, %s, %s, 'buy', %s, %s, %s, %s, %s, 0, %s, 'entry')
                """,
                (
                    pool_id, pos['id'], code, date_str,
                    buy_price, shares, amount,
                    commission, slippage_cost,
                    -(amount + commission),   # cash outflow
                ),
                env=self._env,
            )
            filled += 1

        if filled > 0:
            execute_update(
                "UPDATE sim_pool SET status='active', entry_date=%s WHERE id=%s",
                (date_str, pool_id),
                env=self._env,
            )

        logger.info('[PositionTracker] pool %d: filled %d/%d positions on %s',
                    pool_id, filled, len(positions), date_str)
        return filled

    # ------------------------------------------------------------------
    # T1.4b  update_prices
    # ------------------------------------------------------------------

    def update_prices(self, pool_id: int, price_date: date) -> None:
        """Fetch latest close prices and update sim_position.current_price."""
        positions = execute_query(
            "SELECT id, stock_code FROM sim_position WHERE pool_id=%s AND status='active'",
            (pool_id,),
            env=self._env,
        )
        if not positions:
            return

        codes = [p['stock_code'] for p in positions]
        prices = self._get_close_prices(codes, price_date)

        for pos in positions:
            code = pos['stock_code']
            bare = code.split('.')[0] if '.' in code else code
            close = prices.get(code) or prices.get(bare)

            if close is None:
                # Mark as suspended
                execute_update(
                    "UPDATE sim_position SET suspended_days=suspended_days+1 WHERE id=%s",
                    (pos['id'],),
                    env=self._env,
                )
            else:
                execute_update(
                    "UPDATE sim_position SET current_price=%s, suspended_days=0 WHERE id=%s",
                    (close, pos['id']),
                    env=self._env,
                )

    # ------------------------------------------------------------------
    # T1.4c  check_exits
    # ------------------------------------------------------------------

    def check_exits(self, pool_id: int, price_date: date) -> List[int]:
        """
        Check stop-loss / take-profit / max_hold / suspension exit conditions.
        For triggered positions: execute sell, update sim_position, write sim_trade_log.
        Returns list of exited position IDs.
        """
        import json
        pool_rows = execute_query(
            "SELECT initial_cash, entry_date, params FROM sim_pool WHERE id=%s",
            (pool_id,), env=self._env,
        )
        if not pool_rows:
            return []
        pool = pool_rows[0]
        cfg = self.config
        if pool.get('params'):
            try:
                cfg = SimPoolConfig.from_dict(json.loads(pool['params']))
            except Exception:
                pass

        entry_date_raw = pool.get('entry_date')

        positions = execute_query(
            """
            SELECT id, stock_code, shares, entry_cost, current_price,
                   entry_date, suspended_days
            FROM sim_position WHERE pool_id=%s AND status='active'
            """,
            (pool_id,), env=self._env,
        )

        exited = []
        date_str = price_date.isoformat() if isinstance(price_date, date) else price_date

        for pos in positions:
            pos_id = pos['id']
            code = pos['stock_code']
            shares = pos['shares'] or 0
            entry_cost = float(pos['entry_cost'] or 0)
            current_price = float(pos['current_price'] or 0)
            suspended_days = int(pos['suspended_days'] or 0)

            if shares <= 0 or entry_cost <= 0:
                continue

            # Calculate current return (gross, before exit costs)
            market_value = shares * current_price
            gross_return = (market_value - entry_cost) / entry_cost if entry_cost > 0 else 0

            # Determine exit reason (priority: stop_loss > take_profit > max_hold > suspended)
            exit_reason = None

            if current_price > 0:
                if gross_return <= cfg.stop_loss:
                    exit_reason = 'stop_loss'
                elif gross_return >= cfg.take_profit:
                    exit_reason = 'take_profit'

            # Hold days check using entry_date from position or pool
            pos_entry = pos.get('entry_date') or entry_date_raw
            if pos_entry and exit_reason is None:
                if isinstance(pos_entry, str):
                    from datetime import datetime as _dt
                    pos_entry = _dt.strptime(pos_entry[:10], '%Y-%m-%d').date()
                _price_date = price_date if isinstance(price_date, date) else date.fromisoformat(price_date)
                hold_days = (_price_date - pos_entry).days
                if hold_days >= cfg.max_hold_days:
                    exit_reason = 'max_hold'

            # Suspension check
            if exit_reason is None and suspended_days >= cfg.max_suspended_days:
                exit_reason = 'strategy'

            if exit_reason is None:
                continue

            # Execute sell
            if current_price <= 0:
                # Use entry price as fallback for suspended
                current_price = float(pos.get('entry_price') or entry_cost / shares)

            sell_price = current_price * (1 - cfg.slippage)
            sell_amount = shares * sell_price
            commission = sell_amount * cfg.commission
            stamp_tax = sell_amount * cfg.stamp_tax
            net_proceeds = sell_amount - commission - stamp_tax

            net_return = (net_proceeds - entry_cost) / entry_cost

            execute_update(
                """
                UPDATE sim_position SET
                    exit_price=%s, exit_date=%s, exit_reason=%s,
                    gross_return=%s, net_return=%s, status='exited'
                WHERE id=%s
                """,
                (sell_price, date_str, exit_reason,
                 round(gross_return, 6), round(net_return, 6), pos_id),
                env=self._env,
            )
            execute_update(
                """
                INSERT INTO sim_trade_log
                    (pool_id, position_id, stock_code, trade_date, action,
                     price, shares, amount, commission, slippage_cost,
                     stamp_tax, net_amount, trigger)
                VALUES (%s, %s, %s, %s, 'sell', %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    pool_id, pos_id, code, date_str,
                    sell_price, shares, sell_amount,
                    commission,
                    shares * current_price * cfg.slippage,
                    stamp_tax,
                    net_proceeds,    # cash inflow
                    exit_reason,
                ),
                env=self._env,
            )
            exited.append(pos_id)
            logger.info('[PositionTracker] pool %d: %s exited (%s) ret=%.2f%%',
                        pool_id, code, exit_reason, net_return * 100)

        return exited

    # ------------------------------------------------------------------
    # T2.6  handle_suspended (already integrated into update_prices + check_exits)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # T2.6  handle_suspended  (standalone, also called from daily update)
    # ------------------------------------------------------------------

    def handle_suspended(self, pool_id: int, price_date: date) -> List[int]:
        """
        Force-exit positions that have been suspended for > max_suspended_days
        consecutive trading days. Uses the last known current_price as exit price.
        Returns list of force-exited position IDs.
        """
        import json
        pool_rows = execute_query(
            "SELECT params FROM sim_pool WHERE id=%s", (pool_id,), env=self._env
        )
        cfg = self.config
        if pool_rows and pool_rows[0].get('params'):
            try:
                cfg = SimPoolConfig.from_dict(json.loads(pool_rows[0]['params']))
            except Exception:
                pass

        suspended = execute_query(
            """
            SELECT id, stock_code, shares, entry_cost, current_price, suspended_days, entry_price
            FROM sim_position
            WHERE pool_id=%s AND status='active' AND suspended_days >= %s
            """,
            (pool_id, cfg.max_suspended_days),
            env=self._env,
        )
        if not suspended:
            return []

        date_str = price_date.isoformat() if isinstance(price_date, date) else price_date
        exited = []

        for pos in suspended:
            pos_id = pos['id']
            code = pos['stock_code']
            shares = int(pos['shares'] or 0)
            entry_cost = float(pos['entry_cost'] or 0)
            # Use last known price; fallback to entry_price / shares
            current_price = float(pos['current_price'] or 0)
            if current_price <= 0 and shares > 0:
                current_price = float(pos.get('entry_price') or 0)
            if current_price <= 0 or shares <= 0:
                continue

            # Sell at last known price with slippage
            sell_price = current_price * (1 - cfg.slippage)
            sell_amount = shares * sell_price
            commission = sell_amount * cfg.commission
            stamp_tax = sell_amount * cfg.stamp_tax
            net_proceeds = sell_amount - commission - stamp_tax
            gross_return = (shares * current_price - entry_cost) / entry_cost if entry_cost > 0 else 0
            net_return = (net_proceeds - entry_cost) / entry_cost if entry_cost > 0 else 0

            execute_update(
                """
                UPDATE sim_position SET
                    exit_price=%s, exit_date=%s, exit_reason='strategy',
                    gross_return=%s, net_return=%s, status='exited'
                WHERE id=%s
                """,
                (sell_price, date_str, round(gross_return, 6), round(net_return, 6), pos_id),
                env=self._env,
            )
            execute_update(
                """
                INSERT INTO sim_trade_log
                    (pool_id, position_id, stock_code, trade_date, action,
                     price, shares, amount, commission, slippage_cost,
                     stamp_tax, net_amount, trigger)
                VALUES (%s, %s, %s, %s, 'sell', %s, %s, %s, %s, %s, %s, %s, 'suspended')
                """,
                (
                    pool_id, pos_id, code, date_str,
                    sell_price, shares, sell_amount,
                    commission,
                    shares * current_price * cfg.slippage,
                    stamp_tax,
                    net_proceeds,
                ),
                env=self._env,
            )
            exited.append(pos_id)
            logger.info('[PositionTracker] pool %d: %s force-exited (suspended %d days)',
                        pool_id, code, pos['suspended_days'])

        return exited

    def get_active_positions(self, pool_id: int) -> list:
        rows = execute_query(
            "SELECT * FROM sim_position WHERE pool_id=%s AND status='active'",
            (pool_id,), env=self._env,
        )
        return [dict(r) for r in rows]

    @staticmethod
    def calc_current_return(entry_cost: float, current_price: float, shares: int) -> float:
        if entry_cost <= 0:
            return 0.0
        return (current_price * shares - entry_cost) / entry_cost
