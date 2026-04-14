# -*- coding: utf-8 -*-
"""Abstract base class for strategy adapters."""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategyAdapter(ABC):

    @abstractmethod
    def run(self, signal_date: str, params: dict) -> pd.DataFrame:
        """
        Execute screening and return signals DataFrame.

        Required columns:  stock_code (str), stock_name (str)
        Optional columns:  signal_meta (dict or JSON string)

        Args:
            signal_date: 'YYYY-MM-DD' string
            params:      strategy-specific parameters

        Returns:
            pd.DataFrame with at least [stock_code, stock_name]
        """

    @abstractmethod
    def strategy_type(self) -> str:
        """Return strategy type identifier string."""
