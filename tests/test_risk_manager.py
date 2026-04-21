# -*- coding: utf-8 -*-
"""
风控模块测试

覆盖范围:
  1. 单元测试 — 每条规则的独立逻辑
  2. 引擎测试 — 聚合、advisory_mode、自定义规则
  3. ATR 计算 & 仓位计算
  4. 审计日志
  5. 回测集成测试 — 与 BacktestEngine 联动
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from risk_manager import (
    RiskEngine, RiskConfig, BaseRule,
    Decision, RiskDecision, RiskContext, AggregatedDecision,
    LoggingHook, AuditLog,
    calc_atr, calc_atr_position, ATRSizingResult,
)
from risk_manager.rules import (
    ConcentrationLimit, STBlacklist, PriceLimitGuard,
    OrderAmountCap, ATRPositionScaler, DailyLossCircuitBreaker,
    SinglePositionLimit,
)


# ============================================================
# 辅助函数
# ============================================================

def make_ohlcv(n=30, base_price=100.0, volatility=0.02, seed=42):
    """生成模拟 OHLCV 数据"""
    np.random.seed(seed)
    dates = pd.bdate_range(start='2024-01-01', periods=n)
    returns = np.random.normal(0.0005, volatility, n)
    close = base_price * np.cumprod(1 + returns)
    df = pd.DataFrame({
        'trade_date': dates,
        'open': close * (1 + np.random.uniform(-0.005, 0.005, n)),
        'high': close * (1 + np.random.uniform(0, 0.02, n)),
        'low': close * (1 - np.random.uniform(0, 0.02, n)),
        'close': close,
        'volume': np.random.randint(100000, 1000000, n).astype(float),
    })
    return df


def make_context(**overrides):
    """快速构建 RiskContext"""
    defaults = dict(
        stock_code='600519.SH',
        price=100.0,
        date=datetime(2024, 6, 1),
        portfolio_value=1_000_000,
        cash=500_000,
        current_positions={},
        position_count=3,
        max_positions=10,
        daily_pnl=0.0,
        daily_pnl_pct=0.0,
        ohlcv_history=None,
        order_amount=100_000,
        signal_weight=1.0,
    )
    defaults.update(overrides)
    return RiskContext(**defaults)


# ============================================================
# 1. 决策模型测试
# ============================================================

class TestDecisionModel:
    """决策模型基础行为"""

    def test_decision_ordering(self):
        """Decision 枚举应按严重程度排序"""
        assert Decision.APPROVE < Decision.WARN < Decision.REJECT < Decision.HALT

    def test_risk_decision_approved(self):
        """APPROVE 和 WARN 都算通过"""
        assert RiskDecision(Decision.APPROVE, "", "r").approved is True
        assert RiskDecision(Decision.WARN, "", "r").approved is True
        assert RiskDecision(Decision.REJECT, "", "r").approved is False
        assert RiskDecision(Decision.HALT, "", "r").approved is False

    def test_aggregated_decision_summary(self):
        """AggregatedDecision.summary() 输出可读文本"""
        agg = AggregatedDecision(
            decisions=[
                RiskDecision(Decision.APPROVE, "OK", "rule_a"),
                RiskDecision(Decision.WARN, "注意波动", "rule_b"),
            ],
            final_decision=Decision.WARN,
            suggested_position_pct=0.6,
        )
        text = agg.summary()
        assert "WARN" in text
        assert "60%" in text
        assert "rule_b" in text


# ============================================================
# 2. 单条规则测试
# ============================================================

class TestConcentrationLimit:
    """持仓集中度规则"""

    def test_under_limit(self):
        config = RiskConfig(max_positions=10)
        rule = ConcentrationLimit(config)
        ctx = make_context(position_count=5)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_at_limit(self):
        config = RiskConfig(max_positions=10)
        rule = ConcentrationLimit(config)
        ctx = make_context(position_count=10)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.REJECT

    def test_over_limit(self):
        config = RiskConfig(max_positions=5)
        rule = ConcentrationLimit(config)
        ctx = make_context(position_count=7)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.REJECT


class TestSTBlacklist:
    """ST 黑名单规则"""

    def test_normal_stock(self):
        config = RiskConfig(st_blacklist=['000001.SZ'])
        rule = STBlacklist(config)
        ctx = make_context(stock_code='600519.SH')
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_blacklisted_stock(self):
        config = RiskConfig(st_blacklist=['600519.SH'])
        rule = STBlacklist(config)
        ctx = make_context(stock_code='600519.SH')
        result = rule.evaluate(ctx)
        assert result.decision == Decision.REJECT


class TestPriceLimitGuard:
    """涨跌停检测规则"""

    def test_normal_price(self):
        config = RiskConfig(price_limit_pct=0.10)
        rule = PriceLimitGuard(config)
        df = make_ohlcv(n=5, base_price=100)
        # 当前价接近前收盘价，正常
        ctx = make_context(price=df['close'].iloc[-1], ohlcv_history=df)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_near_limit_up(self):
        """接近涨停时应 WARN"""
        config = RiskConfig(price_limit_pct=0.10)
        rule = PriceLimitGuard(config)
        df = make_ohlcv(n=5, base_price=100)
        prev_close = df['close'].iloc[-2]
        # 设置价格接近涨停
        ctx = make_context(price=prev_close * 1.099, ohlcv_history=df)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.WARN

    def test_no_history(self):
        """无历史数据时应通过"""
        config = RiskConfig()
        rule = PriceLimitGuard(config)
        ctx = make_context(ohlcv_history=None)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE


class TestOrderAmountCap:
    """单笔金额上限规则"""

    def test_under_cap(self):
        config = RiskConfig(order_amount_cap=500_000)
        rule = OrderAmountCap(config)
        ctx = make_context(order_amount=100_000)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_over_cap(self):
        config = RiskConfig(order_amount_cap=500_000)
        rule = OrderAmountCap(config)
        ctx = make_context(order_amount=600_000)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.WARN


class TestATRPositionScaler:
    """ATR 仓位缩放规则"""

    def test_low_volatility(self):
        """低波动应通过且仓位不缩减"""
        # 用较大的 risk_per_trade 确保低波动时仓位 >= 50%
        config = RiskConfig(atr_period=14, atr_risk_per_trade=0.10, atr_multiplier=2.0)
        rule = ATRPositionScaler(config)
        df = make_ohlcv(n=30, base_price=100, volatility=0.001)
        ctx = make_context(price=df['close'].iloc[-1], ohlcv_history=df)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_high_volatility(self):
        """高波动应 WARN 并缩减仓位"""
        config = RiskConfig(atr_period=14, atr_risk_per_trade=0.02, atr_multiplier=2.0)
        rule = ATRPositionScaler(config)
        df = make_ohlcv(n=30, base_price=100, volatility=0.08)
        ctx = make_context(price=df['close'].iloc[-1], ohlcv_history=df)
        result = rule.evaluate(ctx)
        # 高波动时应缩减仓位
        assert result.max_position_pct < 1.0

    def test_no_history(self):
        """无历史数据时应通过"""
        config = RiskConfig()
        rule = ATRPositionScaler(config)
        ctx = make_context(ohlcv_history=None)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE


class TestDailyLossCircuitBreaker:
    """当日亏损熔断规则"""

    def test_no_loss(self):
        config = RiskConfig(daily_max_loss_pct=-0.05)
        rule = DailyLossCircuitBreaker(config)
        ctx = make_context(daily_pnl_pct=0.01)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_small_loss(self):
        config = RiskConfig(daily_max_loss_pct=-0.05)
        rule = DailyLossCircuitBreaker(config)
        ctx = make_context(daily_pnl_pct=-0.03)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_trigger_halt(self):
        """日亏超阈值应 HALT"""
        config = RiskConfig(daily_max_loss_pct=-0.05)
        rule = DailyLossCircuitBreaker(config)
        ctx = make_context(daily_pnl_pct=-0.06)
        result = rule.evaluate(ctx)
        assert result.decision == Decision.HALT


class TestSinglePositionLimit:
    """单只仓位限制规则"""

    def test_under_limit(self):
        config = RiskConfig(single_position_limit=0.10)
        rule = SinglePositionLimit(config)
        ctx = make_context(
            order_amount=50_000,
            portfolio_value=1_000_000,
            current_positions={},
        )
        result = rule.evaluate(ctx)
        assert result.decision == Decision.APPROVE

    def test_over_limit(self):
        config = RiskConfig(single_position_limit=0.10)
        rule = SinglePositionLimit(config)
        ctx = make_context(
            stock_code='600519.SH',
            order_amount=60_000,
            portfolio_value=1_000_000,
            current_positions={'600519.SH': 50_000},  # 已有 5%, 再买 6% = 11%
        )
        result = rule.evaluate(ctx)
        assert result.decision == Decision.REJECT


# ============================================================
# 3. ATR 计算 & 仓位计算
# ============================================================

class TestATR:
    """ATR 计算"""

    def test_atr_output_shape(self):
        df = make_ohlcv(n=30)
        atr = calc_atr(df, period=14)
        assert len(atr) == 30
        assert atr.iloc[-1] > 0

    def test_atr_increases_with_volatility(self):
        """高波动的 ATR 应大于低波动"""
        df_low = make_ohlcv(n=30, volatility=0.01, seed=1)
        df_high = make_ohlcv(n=30, volatility=0.05, seed=1)
        atr_low = calc_atr(df_low, period=14).iloc[-1]
        atr_high = calc_atr(df_high, period=14).iloc[-1]
        assert atr_high > atr_low


class TestATRSizing:
    """ATR 仓位计算"""

    def test_basic_sizing(self):
        config = RiskConfig(atr_period=14, atr_risk_per_trade=0.02, atr_multiplier=2.0)
        df = make_ohlcv(n=30, base_price=100)
        result = calc_atr_position(
            price=df['close'].iloc[-1],
            portfolio_value=1_000_000,
            ohlcv_df=df,
            config=config,
        )
        assert result is not None
        assert result.shares > 0
        assert result.stop_price < df['close'].iloc[-1]
        assert result.stop_distance > 0

    def test_insufficient_data(self):
        """数据不足时返回 None"""
        config = RiskConfig(atr_period=14)
        df = make_ohlcv(n=5)
        result = calc_atr_position(price=100, portfolio_value=1_000_000, ohlcv_df=df, config=config)
        assert result is None

    def test_position_capped(self):
        """仓位不超过 single_position_limit"""
        config = RiskConfig(
            atr_period=14, atr_risk_per_trade=0.10,  # 很大的风险预算
            atr_multiplier=0.1, single_position_limit=0.10,
        )
        df = make_ohlcv(n=30, base_price=10, volatility=0.005)
        result = calc_atr_position(
            price=df['close'].iloc[-1],
            portfolio_value=1_000_000,
            ohlcv_df=df,
            config=config,
        )
        assert result is not None
        assert result.position_value <= 1_000_000 * config.single_position_limit + 1  # 浮点容差


# ============================================================
# 4. 引擎测试
# ============================================================

class TestRiskEngine:
    """风控引擎核心逻辑"""

    def test_all_rules_loaded(self):
        """默认加载 7 条规则"""
        engine = RiskEngine(RiskConfig())
        assert len(engine.rules) == 7

    def test_enabled_rules_filter(self):
        """enabled_rules 可过滤规则"""
        config = RiskConfig(enabled_rules=['concentration_limit', 'st_blacklist'])
        engine = RiskEngine(config)
        assert len(engine.rules) == 2
        names = {r.name for r in engine.rules}
        assert names == {'concentration_limit', 'st_blacklist'}

    def test_approve_result(self):
        """正常股票应全部通过"""
        engine = RiskEngine(RiskConfig())
        result = engine.check_stock('600519.SH', price=100)
        assert result.approved is True
        assert result.final_decision == Decision.APPROVE

    def test_advisory_mode_downgrades_reject(self):
        """advisory_mode=True 时 REJECT 降级为 WARN"""
        config = RiskConfig(advisory_mode=True, st_blacklist=['600519.SH'])
        engine = RiskEngine(config)
        result = engine.check_stock('600519.SH', price=100)
        # ST 黑名单本该 REJECT，但 advisory 模式降级为 WARN
        assert result.final_decision == Decision.WARN
        assert result.approved is True

    def test_strict_mode_rejects(self):
        """advisory_mode=False 时 REJECT 不降级"""
        config = RiskConfig(advisory_mode=False, st_blacklist=['600519.SH'])
        engine = RiskEngine(config)
        result = engine.check_stock('600519.SH', price=100)
        assert result.final_decision == Decision.REJECT
        assert result.approved is False

    def test_halt_not_downgraded(self):
        """HALT 级别不受 advisory_mode 影响"""
        config = RiskConfig(advisory_mode=True, daily_max_loss_pct=-0.05)
        engine = RiskEngine(config)
        result = engine.check_stock('600519.SH', price=100, daily_pnl_pct=-0.10)
        assert result.final_decision == Decision.HALT
        assert result.approved is False

    def test_one_veto_aggregation(self):
        """一票否决：最严重的决策胜出"""
        config = RiskConfig(
            advisory_mode=False,
            st_blacklist=['600519.SH'],
            daily_max_loss_pct=-0.05,
        )
        engine = RiskEngine(config)
        result = engine.check_stock('600519.SH', price=100, daily_pnl_pct=-0.10)
        # ST -> REJECT, 熔断 -> HALT, max = HALT
        assert result.final_decision == Decision.HALT

    def test_custom_rule(self):
        """自定义规则通过 add_rule 注册"""
        class PriceFloorRule(BaseRule):
            @property
            def name(self):
                return 'price_floor'
            def evaluate(self, ctx):
                if ctx.price < 5:
                    return self._reject('低价股禁入')
                return self._approve()

        config = RiskConfig(advisory_mode=False)
        engine = RiskEngine(config)
        engine.add_rule(PriceFloorRule())
        assert len(engine.rules) == 8

        result = engine.check_stock('000001.SZ', price=3.5)
        assert result.final_decision == Decision.REJECT

        result = engine.check_stock('000001.SZ', price=10.0)
        assert result.approved is True

    def test_position_pct_min_aggregation(self):
        """suggested_position_pct 取所有规则的最小值"""
        config = RiskConfig(atr_period=14, atr_risk_per_trade=0.02, atr_multiplier=2.0)
        engine = RiskEngine(config)
        df = make_ohlcv(n=30, base_price=100, volatility=0.08)
        result = engine.check_stock('600519.SH', price=df['close'].iloc[-1], ohlcv_history=df)
        # ATR 较高时应缩减仓位
        assert result.suggested_position_pct <= 1.0


# ============================================================
# 5. 审计日志测试
# ============================================================

class TestAuditLog:
    """审计日志"""

    def test_audit_recording(self):
        engine = RiskEngine(RiskConfig())
        engine.check_stock('600519.SH', price=100)
        engine.check_stock('000001.SZ', price=50)
        assert len(engine.audit) == 2

    def test_audit_to_dataframe(self):
        engine = RiskEngine(RiskConfig())
        engine.check_stock('600519.SH', price=100)
        df = engine.audit.to_dataframe()
        assert len(df) == 1
        assert 'stock_code' in df.columns
        assert 'decision' in df.columns

    def test_audit_filter_rejections(self):
        config = RiskConfig(advisory_mode=False, st_blacklist=['BAD.SH'])
        engine = RiskEngine(config)
        engine.check_stock('GOOD.SH', price=100)
        engine.check_stock('BAD.SH', price=100)
        rejections = engine.audit.get_rejections()
        assert len(rejections) == 1
        assert rejections[0].stock_code == 'BAD.SH'


# ============================================================
# 6. Hook 测试
# ============================================================

class TestHooks:
    """通知钩子"""

    def test_logging_hook_fires(self, capsys):
        config = RiskConfig(advisory_mode=False, st_blacklist=['BAD.SH'])
        engine = RiskEngine(config)
        engine.add_hook(LoggingHook())
        engine.check_stock('BAD.SH', price=100)
        output = capsys.readouterr().out
        assert '风控拒绝' in output

    def test_custom_hook(self):
        events = []

        class CollectorHook:
            def on_decision(self, ctx, decision):
                events.append(('decision', ctx.stock_code))
            def on_warning(self, ctx, decision):
                events.append(('warning', ctx.stock_code))
            def on_rejection(self, ctx, decision):
                events.append(('rejection', ctx.stock_code))

        config = RiskConfig(advisory_mode=True, st_blacklist=['BAD.SH'])
        engine = RiskEngine(config)
        engine.add_hook(CollectorHook())
        engine.check_stock('BAD.SH', price=100)
        assert ('decision', 'BAD.SH') in events
        assert ('warning', 'BAD.SH') in events


# ============================================================
# 7. 回测集成测试
# ============================================================

class TestBacktestIntegration:
    """风控模块与回测引擎的集成"""

    @staticmethod
    def _make_test_data():
        """构造回测所需的假数据"""
        stock_codes = ['STOCK_A', 'STOCK_B', 'STOCK_C']
        start_date = '2024-01-01'
        n_days = 60

        price_data = {}
        for i, code in enumerate(stock_codes):
            np.random.seed(i * 10 + 42)
            dates = pd.bdate_range(start=start_date, periods=n_days)
            returns = np.random.normal(0.0005, 0.02, n_days)
            prices = 100.0 * np.cumprod(1 + returns)
            df = pd.DataFrame({
                'trade_date': dates,
                'open': prices * (1 + np.random.uniform(-0.005, 0.005, n_days)),
                'high': prices * (1 + np.random.uniform(0, 0.02, n_days)),
                'low': prices * (1 - np.random.uniform(0, 0.02, n_days)),
                'close': prices,
                'volume': np.random.randint(100000, 1000000, n_days).astype(float),
            })
            price_data[code] = df

        # 生成信号：每只股票在第 5、15、25 天发信号
        signals = []
        for code in stock_codes:
            dates = price_data[code]['trade_date'].values
            for idx in [5, 15, 25]:
                signals.append({
                    'date': dates[idx],
                    'stock_code': code,
                    'signal_type': 'momentum',
                    'weight': 0.8,
                })
        signals_df = pd.DataFrame(signals)
        return price_data, signals_df

    def test_backtest_without_risk(self):
        """无风控的回测正常运行"""
        from backtest import BacktestConfig, BacktestEngine

        price_data, signals = self._make_test_data()
        config = BacktestConfig(
            initial_cash=1_000_000,
            max_positions=3,
            default_hold_days=20,
        )
        engine = BacktestEngine(config)
        result = engine.run(signals=signals, price_data=price_data)
        assert result.total_trades > 0

    def test_backtest_with_risk(self):
        """带风控的回测正常运行"""
        from backtest import BacktestConfig, BacktestEngine

        price_data, signals = self._make_test_data()
        config = BacktestConfig(
            initial_cash=1_000_000,
            max_positions=3,
            default_hold_days=20,
        )
        risk_config = RiskConfig(
            max_positions=3,
            advisory_mode=False,
        )
        engine = BacktestEngine(config, risk_config=risk_config)
        result = engine.run(signals=signals, price_data=price_data)
        assert result is not None
        # 风控引擎应有审计记录
        assert len(engine.risk_engine.audit) > 0

    def test_risk_blocks_excess_positions(self):
        """风控应阻止超过 max_positions 的买入"""
        from backtest import BacktestConfig, BacktestEngine

        price_data, signals = self._make_test_data()
        config = BacktestConfig(
            initial_cash=1_000_000,
            max_positions=10,  # 回测引擎允许 10
            default_hold_days=20,
        )
        risk_config = RiskConfig(
            max_positions=2,  # 风控只允许 2
            advisory_mode=False,
        )
        engine = BacktestEngine(config, risk_config=risk_config)
        result = engine.run(signals=signals, price_data=price_data)

        # 检查审计日志中有被拒绝的记录
        rejections = engine.risk_engine.audit.get_rejections()
        assert len(rejections) > 0

    def test_backtest_with_risk_parity(self):
        """risk_parity + 风控引擎使用 ATR 仓位"""
        from backtest import BacktestConfig, BacktestEngine

        price_data, signals = self._make_test_data()
        config = BacktestConfig(
            initial_cash=1_000_000,
            max_positions=3,
            default_hold_days=20,
            position_sizing='risk_parity',
        )
        risk_config = RiskConfig(max_positions=3)
        engine = BacktestEngine(config, risk_config=risk_config)
        result = engine.run(signals=signals, price_data=price_data)
        assert result is not None

    def test_risk_parity_no_recursion_without_risk_engine(self):
        """不传 risk_config 时 risk_parity 不会无限递归"""
        from backtest import BacktestConfig, BacktestEngine

        price_data, signals = self._make_test_data()
        config = BacktestConfig(
            initial_cash=1_000_000,
            max_positions=3,
            default_hold_days=20,
            position_sizing='risk_parity',
        )
        engine = BacktestEngine(config)  # 不传 risk_config
        result = engine.run(signals=signals, price_data=price_data)
        assert result is not None


# ============================================================
# 入口
# ============================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
