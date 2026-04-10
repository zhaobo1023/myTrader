# -*- coding: utf-8 -*-
"""
P2-1 单元测试: 退市归零处理

验证：
- 持仓期间连续 3 日无收盘价 → 归零卖出，return=-1.0
- 中间有 1 日恢复价格时计数重置，不触发归零
- 归零记录写入 trades，含 delist=True 标记
- 正常持仓不触发归零
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest


def make_bt():
    cfg = MicrocapConfig(start_date='2026-01-01', end_date='2026-01-15')
    bt = MicrocapBacktest(cfg)
    return bt


def inject_close(bt, trade_date, stock_code, close_p):
    """注入收盘价缓存（None 表示无数据）。"""
    if trade_date not in bt._price_cache:
        bt._price_cache[trade_date] = {'open': {}, 'high': {}, 'low': {}, 'close': {}}
    if close_p is not None:
        bt._price_cache[trade_date]['close'][stock_code] = close_p
    # 不注入 = 模拟数据缺失


DELIST_THRESHOLD = 3   # 与 backtest.py 中 DELIST_THRESHOLD 一致


class TestDelistDetection:

    def _simulate_nav_step(self, bt, holdings, code, trade_date, close_p):
        """模拟第4步：退市检测 + NAV 计算，返回是否触发归零。"""
        inject_close(bt, trade_date, code, close_p)

        triggered = False
        h = holdings.get(code)
        if h is None:
            return False

        current_price = bt._get_close_price(code, trade_date)
        if current_price is None or current_price <= 0:
            h['no_price_days'] += 1
            if h['no_price_days'] >= DELIST_THRESHOLD:
                pnl_pct = -1.0 - bt.config.buy_cost_rate
                bt.trades.append({
                    'buy_date':   h['buy_date'],
                    'sell_date':  trade_date,
                    'stock_code': code,
                    'buy_price':  h['buy_price'],
                    'sell_price': 0.0,
                    'hold_days':  bt.config.hold_days + h['delay_count'],
                    'delay_count': h['delay_count'],
                    'return':     pnl_pct,
                    'pnl':        -(h['units'] * h['buy_price']),
                    'delist':     True,
                })
                del holdings[code]
                triggered = True
        else:
            h['no_price_days'] = 0

        return triggered

    def test_delist_triggers_after_threshold(self):
        """连续 3 日无价格 → 第 3 日触发归零。"""
        bt = make_bt()
        code = '000001.SZ'
        holdings = {
            code: {
                'buy_date': '2026-01-02', 'buy_price': 10.0,
                'units': 100.0, 'sell_date': '2026-01-10',
                'delay_count': 0, 'no_price_days': 0,
            }
        }

        # Day 1: 无价格
        self._simulate_nav_step(bt, holdings, code, '2026-01-05', None)
        assert code in holdings, "第1天无价格，不应触发"
        assert holdings[code]['no_price_days'] == 1

        # Day 2: 无价格
        self._simulate_nav_step(bt, holdings, code, '2026-01-06', None)
        assert code in holdings, "第2天无价格，不应触发"
        assert holdings[code]['no_price_days'] == 2

        # Day 3: 无价格 → 触发归零
        triggered = self._simulate_nav_step(bt, holdings, code, '2026-01-07', None)
        assert triggered, "第3天应触发退市归零"
        assert code not in holdings, "归零后持仓应被清除"
        assert len(bt.trades) == 1, "应有一笔归零交易记录"
        assert bt.trades[0]['delist'] is True
        assert bt.trades[0]['sell_price'] == 0.0
        assert bt.trades[0]['return'] < -1.0   # -1.0 - buy_cost_rate

    def test_recovery_resets_counter(self):
        """第2天恢复价格 → 计数归零，不触发退市。"""
        bt = make_bt()
        code = '000002.SZ'
        holdings = {
            code: {
                'buy_date': '2026-01-02', 'buy_price': 10.0,
                'units': 100.0, 'sell_date': '2026-01-10',
                'delay_count': 0, 'no_price_days': 0,
            }
        }

        self._simulate_nav_step(bt, holdings, code, '2026-01-05', None)   # day1: 无价格
        assert holdings[code]['no_price_days'] == 1

        self._simulate_nav_step(bt, holdings, code, '2026-01-06', 9.5)    # day2: 恢复
        assert holdings[code]['no_price_days'] == 0, "恢复价格后计数应清零"
        assert code in holdings, "不应触发归零"

        self._simulate_nav_step(bt, holdings, code, '2026-01-07', None)   # day3: 无价格（重新计）
        assert holdings[code]['no_price_days'] == 1, "重新计数应从1开始"

    def test_normal_holding_never_delisted(self):
        """正常持仓（每天有价格）不触发归零。"""
        bt = make_bt()
        code = '000003.SZ'
        holdings = {
            code: {
                'buy_date': '2026-01-02', 'buy_price': 10.0,
                'units': 100.0, 'sell_date': '2026-01-10',
                'delay_count': 0, 'no_price_days': 0,
            }
        }

        prices = [10.1, 10.2, 9.8, 10.0, 10.3]
        dates  = [f'2026-01-0{d}' for d in range(2, 7)]
        for d, p in zip(dates, prices):
            triggered = self._simulate_nav_step(bt, holdings, code, d, p)
            assert not triggered
        assert code in holdings
        assert len(bt.trades) == 0

    def test_trade_record_fields_on_delist(self):
        """归零交易记录字段完整性检查。"""
        bt = make_bt()
        code = '000004.SZ'
        buy_price = 12.5
        units = 80.0
        holdings = {
            code: {
                'buy_date': '2026-01-02', 'buy_price': buy_price,
                'units': units, 'sell_date': '2026-01-10',
                'delay_count': 1, 'no_price_days': 0,
            }
        }

        for d in ['2026-01-05', '2026-01-06', '2026-01-07']:
            self._simulate_nav_step(bt, holdings, code, d, None)

        assert len(bt.trades) == 1
        trade = bt.trades[0]
        assert trade['stock_code'] == code
        assert trade['buy_price']  == buy_price
        assert trade['sell_price'] == 0.0
        assert trade['delist']     is True
        assert abs(trade['pnl'] - (-(units * buy_price))) < 1e-6
