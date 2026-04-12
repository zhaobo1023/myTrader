# -*- coding: utf-8 -*-
"""signal state machine with cooldown logic"""

import logging
import pandas as pd
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SIGNAL_LABELS = {
    'overheat': '[RED] overheat',
    'breakout': '[YELLOW] breakout',
    'pullback': '[GREEN] pullback',
    'normal': '[GRAY] normal',
    'stall': '[RED] stall',
}


class SignalDetector:
    """5-state signal machine: overheat / breakout / pullback / normal / stall"""

    def __init__(self, cooldown_days: int = 10,
                 breakout_threshold: float = 5.0,
                 overheat_threshold: float = 15.0,
                 stall_threshold: float = -5.0):
        self.cooldown_days = cooldown_days
        self.breakout_threshold = breakout_threshold
        self.overheat_threshold = overheat_threshold
        self.stall_threshold = stall_threshold

    def detect(self, curr: dict, prev: dict) -> dict:
        """
        detect signal for a single day

        Args:
            curr: {'log_bias': float, 'trade_date': date}
            prev: {'log_bias': float, 'signal_state': str,
                   'last_breakout_date': date|None, 'last_stall_date': date|None}

        Returns:
            dict with signal_state, last_breakout_date, last_stall_date, prev_state
        """
        lb = curr['log_bias']
        # use the current row's date, not date.today(), to correctly replay history
        current_date = curr.get('trade_date') or date.today()
        if not isinstance(current_date, date):
            current_date = pd.to_datetime(current_date).date()

        prev_state = prev.get('signal_state', 'normal')
        last_stall_date = prev.get('last_stall_date')
        last_breakout_date = prev.get('last_breakout_date')

        # check cooldown: if stall happened within cooldown_days, suppress breakout
        in_cooldown = False
        if last_stall_date is not None:
            if not isinstance(last_stall_date, date):
                last_stall_date = pd.to_datetime(last_stall_date).date()
            if (current_date - last_stall_date).days < self.cooldown_days:
                in_cooldown = True

        # determine state by priority: overheat > stall > breakout > pullback > normal
        if lb > self.overheat_threshold:
            state = 'overheat'
        elif lb < self.stall_threshold:
            state = 'stall'
            last_stall_date = current_date
        elif lb >= self.breakout_threshold:
            if in_cooldown:
                state = 'normal'
            else:
                state = 'breakout'
                last_breakout_date = current_date
        elif lb >= 0:
            # pullback: log_bias in [0, breakout_threshold) AND recently was above breakout
            if prev_state in ('breakout', 'pullback', 'overheat'):
                state = 'pullback'
            else:
                state = 'normal'
        else:
            state = 'normal'

        return {
            'signal_state': state,
            'prev_state': prev_state,
            'last_breakout_date': last_breakout_date,
            'last_stall_date': last_stall_date,
        }

    def detect_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        detect signals for entire DataFrame

        Args:
            df: must have 'log_bias' column (output of calculate_log_bias)

        Returns:
            DataFrame with added columns: signal_state, prev_state,
            last_breakout_date, last_stall_date
        """
        out = df.copy()
        out['signal_state'] = 'normal'
        out['prev_state'] = 'normal'
        out['last_breakout_date'] = None
        out['last_stall_date'] = None

        for i in range(len(out)):
            curr = {
                'log_bias': out['log_bias'].iloc[i],
                'trade_date': out['trade_date'].iloc[i] if 'trade_date' in out.columns else date.today(),
            }
            prev = {
                'log_bias': out['log_bias'].iloc[i - 1] if i > 0 else 0.0,
                'signal_state': out['signal_state'].iloc[i - 1] if i > 0 else 'normal',
                'last_breakout_date': out['last_breakout_date'].iloc[i - 1] if i > 0 else None,
                'last_stall_date': out['last_stall_date'].iloc[i - 1] if i > 0 else None,
            }
            result = self.detect(curr, prev)
            out.iloc[i, out.columns.get_loc('signal_state')] = result['signal_state']
            out.iloc[i, out.columns.get_loc('prev_state')] = result['prev_state']
            out.iloc[i, out.columns.get_loc('last_breakout_date')] = result['last_breakout_date']
            out.iloc[i, out.columns.get_loc('last_stall_date')] = result['last_stall_date']

        return out
