# -*- coding: utf-8 -*-
"""
P0-2 单元测试: 涨跌停处理

覆盖场景：
- _is_limit_down / _is_limit_up 判断逻辑
- 正常交易日（high != low）不触发
- 无前收数据不触发
- 卖出遇跌停顺延（最多 5 天）
- 买入遇涨停跳过
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest


def make_backtest() -> MicrocapBacktest:
    """创建一个不连接数据库的回测实例（仅测试辅助方法）。"""
    cfg = MicrocapConfig(start_date='2026-01-01', end_date='2026-01-10')
    bt = MicrocapBacktest(cfg)
    return bt


def inject_price(bt: MicrocapBacktest, trade_date: str,
                 stock_code: str, open_p: float, high_p: float,
                 low_p: float, close_p: float, prev_close: float = None):
    """向回测实例注入价格缓存，绕过数据库。"""
    if trade_date not in bt._price_cache:
        bt._price_cache[trade_date] = {'open': {}, 'high': {}, 'low': {}, 'close': {}}
    bt._price_cache[trade_date]['open'][stock_code]  = open_p
    bt._price_cache[trade_date]['high'][stock_code]  = high_p
    bt._price_cache[trade_date]['low'][stock_code]   = low_p
    bt._price_cache[trade_date]['close'][stock_code] = close_p
    if prev_close is not None:
        bt._prev_close[stock_code] = prev_close


class TestIsLimitDown:

    def test_one_direction_down_detected(self):
        """高低价相等且跌幅 > 4% → 一字跌停。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000001.SZ',
                     open_p=9.0, high_p=9.0, low_p=9.0, close_p=9.0,
                     prev_close=10.0)   # 跌幅 -10%
        assert bt._is_limit_down('000001.SZ', '2026-01-05') is True

    def test_st_limit_down_detected(self):
        """ST 股跌幅 -5% 也能被检测到（阈值 -4%）。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000002.SZ',
                     open_p=9.5, high_p=9.5, low_p=9.5, close_p=9.5,
                     prev_close=10.0)   # 跌幅 -5%
        assert bt._is_limit_down('000002.SZ', '2026-01-05') is True

    def test_normal_trading_day_not_limit_down(self):
        """高低价不等（正常交易） → 不是跌停。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000003.SZ',
                     open_p=9.5, high_p=10.2, low_p=9.3, close_p=9.8,
                     prev_close=10.0)
        assert bt._is_limit_down('000003.SZ', '2026-01-05') is False

    def test_small_drop_not_limit_down(self):
        """高低价相等但跌幅 < 4%（停牌/极小波动） → 不判定为跌停。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000004.SZ',
                     open_p=9.97, high_p=9.97, low_p=9.97, close_p=9.97,
                     prev_close=10.0)   # 跌幅 -0.3%
        assert bt._is_limit_down('000004.SZ', '2026-01-05') is False

    def test_no_prev_close_returns_false(self):
        """无前收价 → 无法判断，返回 False（不误触发顺延）。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000005.SZ',
                     open_p=9.0, high_p=9.0, low_p=9.0, close_p=9.0)
        # 不注入 prev_close
        assert bt._is_limit_down('000005.SZ', '2026-01-05') is False


class TestIsLimitUp:

    def test_one_direction_up_detected(self):
        """高低价相等且涨幅 > 4% → 一字涨停。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000001.SZ',
                     open_p=11.0, high_p=11.0, low_p=11.0, close_p=11.0,
                     prev_close=10.0)   # 涨幅 +10%
        assert bt._is_limit_up('000001.SZ', '2026-01-05') is True

    def test_normal_up_not_limit_up(self):
        """正常上涨（有价格区间） → 不是涨停。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000002.SZ',
                     open_p=10.2, high_p=10.8, low_p=10.1, close_p=10.5,
                     prev_close=10.0)
        assert bt._is_limit_up('000002.SZ', '2026-01-05') is False

    def test_no_prev_close_returns_false(self):
        """无前收价 → 返回 False。"""
        bt = make_backtest()
        inject_price(bt, '2026-01-05', '000003.SZ',
                     open_p=11.0, high_p=11.0, low_p=11.0, close_p=11.0)
        assert bt._is_limit_up('000003.SZ', '2026-01-05') is False


class TestSellDelayOnLimitDown:

    def _make_bt_with_trade_dates(self, dates):
        bt = make_backtest()
        bt._trade_dates = dates
        bt._date_to_idx = {d: i for i, d in enumerate(dates)}
        return bt

    def test_sell_delayed_once(self):
        """卖出日一字跌停 → sell_date 顺延到下一个交易日，delay_count=1。"""
        dates = ['2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07']
        bt = self._make_bt_with_trade_dates(dates)

        code = '000001.SZ'
        # 注入 2026-01-05 为一字跌停
        inject_price(bt, '2026-01-05', code,
                     open_p=9.0, high_p=9.0, low_p=9.0, close_p=9.0,
                     prev_close=10.0)

        holding = {'buy_date': '2026-01-02', 'buy_price': 10.0,
                   'units': 100.0, 'sell_date': '2026-01-05', 'delay_count': 0}
        bt.holdings = {code: holding}

        # 模拟主循环第2天：trade_date = 2026-01-05，sell_date 匹配
        trade_date = '2026-01-05'
        h = bt.holdings[code]
        if trade_date == h['sell_date']:
            if bt._is_limit_down(code, trade_date) and h['delay_count'] < 5:
                idx = bt._date_to_idx[trade_date]
                h['sell_date'] = bt._trade_dates[idx + 1]
                h['delay_count'] += 1
                bt._limit_down_delayed += 1

        assert h['sell_date'] == '2026-01-06'
        assert h['delay_count'] == 1
        assert bt._limit_down_delayed == 1

    def test_sell_delayed_max_5_times(self):
        """连续 5 天跌停 → delay_count 达到 5 后不再顺延。"""
        dates = [f'2026-01-0{i}' for i in range(2, 9)]  # 02~08
        bt = self._make_bt_with_trade_dates(dates)

        code = '000001.SZ'
        # 注入所有日期均为跌停
        for d in dates:
            inject_price(bt, d, code,
                         open_p=9.0, high_p=9.0, low_p=9.0, close_p=9.0,
                         prev_close=10.0)

        h = {'buy_date': '2026-01-02', 'buy_price': 10.0,
             'units': 100.0, 'sell_date': '2026-01-03', 'delay_count': 0}
        bt.holdings = {code: h}

        # 模拟 5 次顺延
        for day_idx in range(1, 7):
            trade_date = dates[day_idx]
            if trade_date == h['sell_date']:
                if bt._is_limit_down(code, trade_date) and h['delay_count'] < 5:
                    idx = bt._date_to_idx[trade_date]
                    if idx + 1 < len(dates):
                        h['sell_date'] = dates[idx + 1]
                        h['delay_count'] += 1
                        bt._limit_down_delayed += 1

        assert h['delay_count'] == 5
        # 第 6 次不顺延（delay_count 已达 5）

    def test_limit_up_skip_buy(self):
        """买入日一字涨停 → 跳过，limit_up_skipped 加 1。"""
        bt = make_backtest()
        code = '000001.SZ'
        inject_price(bt, '2026-01-05', code,
                     open_p=11.0, high_p=11.0, low_p=11.0, close_p=11.0,
                     prev_close=10.0)

        skipped = 0
        if bt._is_limit_up(code, '2026-01-05'):
            bt._limit_up_skipped += 1
            skipped += 1

        assert skipped == 1
        assert bt._limit_up_skipped == 1
