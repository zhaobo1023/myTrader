# -*- coding: utf-8 -*-
"""SimPool configuration dataclass."""

from dataclasses import dataclass


@dataclass
class SimPoolConfig:
    # --- Trading costs ---
    commission: float = 0.0003      # one-way commission rate 0.03%
    slippage: float = 0.001         # slippage rate 0.1%
    stamp_tax: float = 0.001        # stamp duty on sell only 0.1%

    # --- Exit conditions ---
    stop_loss: float = -0.10        # -10%
    take_profit: float = 0.20       # +20%
    max_hold_days: int = 60         # max holding calendar days
    max_suspended_days: int = 5     # force exit after N consecutive suspended days

    # --- Position sizing ---
    position_sizing: str = 'equal'  # only 'equal' supported currently
    max_positions: int = 10

    # --- Capital ---
    initial_cash: float = 1_000_000.0

    # --- Benchmark ---
    benchmark_code: str = '000300.SH'

    # --- DB env ---
    db_env: str = 'online'

    def to_dict(self) -> dict:
        return {
            'commission': self.commission,
            'slippage': self.slippage,
            'stamp_tax': self.stamp_tax,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'max_hold_days': self.max_hold_days,
            'max_suspended_days': self.max_suspended_days,
            'position_sizing': self.position_sizing,
            'max_positions': self.max_positions,
            'initial_cash': self.initial_cash,
            'benchmark_code': self.benchmark_code,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'SimPoolConfig':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
