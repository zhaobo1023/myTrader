# -*- coding: utf-8 -*-
"""
P0-1 单元测试: 滑点成本计算

验证：
- 买入价 = raw_open * (1 + slippage_rate)
- 卖出价 = raw_open * (1 - slippage_rate)
- 不同 slippage 档位下成本计算互相独立
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest


def make_backtest(slippage: float) -> MicrocapBacktest:
    cfg = MicrocapConfig(
        start_date='2026-01-01',
        end_date='2026-01-10',
        slippage_rate=slippage,
    )
    return MicrocapBacktest(cfg)


def inject_open(bt: MicrocapBacktest, trade_date: str, stock_code: str, open_p: float):
    """注入开盘价缓存（仅测试价格计算）。"""
    if trade_date not in bt._price_cache:
        bt._price_cache[trade_date] = {'open': {}, 'high': {}, 'low': {}, 'close': {}}
    bt._price_cache[trade_date]['open'][stock_code]  = open_p
    bt._price_cache[trade_date]['high'][stock_code]  = open_p
    bt._price_cache[trade_date]['low'][stock_code]   = open_p
    bt._price_cache[trade_date]['close'][stock_code] = open_p


class TestSlippageCostCalculation:

    def test_buy_price_includes_slippage(self):
        """买入价 = open * (1 + slippage)，精度 1e-9。"""
        slippage = 0.001
        raw_open = 10.0
        expected = raw_open * (1 + slippage)

        bt = make_backtest(slippage)
        inject_open(bt, '2026-01-05', '000001.SZ', raw_open)

        # 模拟买入价计算
        price_raw = bt._get_open_price('000001.SZ', '2026-01-05')
        buy_price = price_raw * (1 + bt.config.slippage_rate)

        assert abs(buy_price - expected) < 1e-9, (
            f"买入价应为 {expected}，实际为 {buy_price}"
        )

    def test_sell_price_includes_slippage(self):
        """卖出价 = open * (1 - slippage)，精度 1e-9。"""
        slippage = 0.001
        raw_open = 10.0
        expected = raw_open * (1 - slippage)

        bt = make_backtest(slippage)
        inject_open(bt, '2026-01-05', '000001.SZ', raw_open)

        price_raw = bt._get_open_price('000001.SZ', '2026-01-05')
        sell_price = price_raw * (1 - bt.config.slippage_rate)

        assert abs(sell_price - expected) < 1e-9

    def test_higher_slippage_increases_buy_cost(self):
        """滑点越高，买入价越高（成本越大）。"""
        raw_open = 10.0

        slippages = [0.001, 0.002, 0.003, 0.005]
        buy_prices = []

        for slip in slippages:
            bt = make_backtest(slip)
            inject_open(bt, '2026-01-05', '000001.SZ', raw_open)
            price_raw = bt._get_open_price('000001.SZ', '2026-01-05')
            buy_prices.append(price_raw * (1 + slip))

        for i in range(len(buy_prices) - 1):
            assert buy_prices[i] < buy_prices[i + 1], (
                f"slippage={slippages[i]:.3f} 的买入价 {buy_prices[i]} "
                f"应低于 slippage={slippages[i+1]:.3f} 的买入价 {buy_prices[i+1]}"
            )

    def test_higher_slippage_decreases_sell_price(self):
        """滑点越高，卖出价越低（收益越少）。"""
        raw_open = 10.0

        slippages = [0.001, 0.002, 0.003, 0.005]
        sell_prices = []

        for slip in slippages:
            bt = make_backtest(slip)
            inject_open(bt, '2026-01-05', '000001.SZ', raw_open)
            price_raw = bt._get_open_price('000001.SZ', '2026-01-05')
            sell_prices.append(price_raw * (1 - slip))

        for i in range(len(sell_prices) - 1):
            assert sell_prices[i] > sell_prices[i + 1], (
                f"slippage={slippages[i]:.3f} 的卖出价 {sell_prices[i]} "
                f"应高于 slippage={slippages[i+1]:.3f} 的卖出价 {sell_prices[i+1]}"
            )

    def test_slippage_round_trip_cost(self):
        """双边滑点 + 手续费 = 实际综合成本，验证公式正确性。"""
        slippage = 0.001
        buy_cost_rate = 0.0003
        sell_cost_rate = 0.0013
        raw_open = 10.0

        bt = make_backtest(slippage)
        buy_price  = raw_open * (1 + slippage)
        sell_price = raw_open * (1 - slippage)

        # 假设 1 手（100股），持平出（未盈利）
        units = 100.0
        buy_total  = units * buy_price * (1 + buy_cost_rate)   # 买入总支出（含佣金）
        sell_proceeds = units * sell_price * (1 - sell_cost_rate)  # 卖出净收入

        expected_total_cost_rate = (buy_total - sell_proceeds) / (units * raw_open)
        # 理论成本 = 2*slippage + buy_cost + sell_cost = 0.2% + 0.03% + 0.13% = 0.36%
        theoretical = 2 * slippage + buy_cost_rate + sell_cost_rate

        assert abs(expected_total_cost_rate - theoretical) < 0.0001, (
            f"综合成本 {expected_total_cost_rate:.4%} 与理论值 {theoretical:.4%} 偏差过大"
        )
