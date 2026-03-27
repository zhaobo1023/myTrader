# -*- coding: utf-8 -*-
"""
Paper Trading 调度器

每个交易日自动执行对应操作:
    - pending 轮次: 填入买入价 (pending -> active)
    - active 到期轮次: 结算收益 (active -> settled)
    - 信号日: 生成新信号

时间轴（以 hold_days=5 为例）:
    周五(信号日) -> 下周一(T+1买入) -> 下下周五(T+5卖出)
                   -> 同时生成新一轮信号
"""
import logging
from datetime import date

from .config import PaperTradingConfig
from .position_manager import PositionManager
from .signal_generator import SignalGenerator
from .settlement import SettlementEngine
from .evaluator import PerformanceEvaluator

logger = logging.getLogger(__name__)


class PaperTradingScheduler:
    """Paper Trading 调度器"""

    def __init__(self, config: PaperTradingConfig = None):
        self.config = config or PaperTradingConfig()
        self.pm = PositionManager(self.config)
        self.se = SettlementEngine(self.config)
        self.sg = SignalGenerator(self.config)
        self.ev = PerformanceEvaluator()

    def run(
        self,
        today: date = None,
        index_name: str = None,
        is_signal_day: bool = False,
    ) -> dict:
        """
        执行当天所有待处理任务。

        Args:
            today: 运行日期（默认今天）
            index_name: 指数池名称
            is_signal_day: 是否为信号日（强制生成信号）

        Returns:
            运行结果摘要
        """
        today = today or date.today()
        index_name = index_name or self.config.default_index

        result = {
            'date': today,
            'index': index_name,
            'buys_filled': 0,
            'rounds_settled': 0,
            'settlement_details': [],
            'signal_generated': False,
            'signal_round_id': None,
        }

        logger.info(f"[PaperTrading] 开始运行，日期={today}，指数={index_name}")

        # Step 1: 填入买入价（pending -> active）
        pending = self.pm.get_pending_buy_rounds()
        for r in pending:
            buy_date = r['buy_date']
            if hasattr(buy_date, 'strftime'):
                buy_date_str = buy_date.strftime('%Y-%m-%d')
            else:
                buy_date_str = str(buy_date)

            if buy_date_str <= today.strftime('%Y-%m-%d'):
                logger.info(f"[填入买入价] {r['round_id']}, buy_date={buy_date}")
                self.se.fill_buy_prices(r['round_id'], buy_date)
                result['buys_filled'] += 1

        # Step 2: 结算到期轮次（active -> settled）
        to_settle = self.pm.get_rounds_to_settle()
        for r in to_settle:
            logger.info(f"[结算] {r['round_id']}, sell_date={r['sell_date']}")
            settle_result = self.se.settle_round(r['round_id'], r['sell_date'])
            if settle_result:
                result['rounds_settled'] += 1
                result['settlement_details'].append(settle_result)

        # Step 3: 生成新信号（仅在信号日执行）
        if is_signal_day:
            logger.info(f"[生成信号] {today} {index_name}")
            try:
                signals = self.sg.generate(today, index_name)
                round_id = self.pm.create_round(today, index_name, signals)
                result['signal_generated'] = True
                result['signal_round_id'] = round_id
                logger.info(f"  -> 创建轮次 {round_id}，选出 {len(signals)} 只股票")
                next_buy = self.pm.get_next_trading_date(today, 1)
                logger.info(f"  -> 买入日: {next_buy}")
            except Exception as e:
                logger.error(f"[生成信号] 失败: {e}")
                result['signal_error'] = str(e)

        # Step 4: 打印当前评估
        df = self.ev.load_settled_rounds(index_name)
        if df is not None:
            metrics = self.ev.compute_metrics(df)
            print(f"\n{'='*50}")
            print(f"[{index_name}] 已结算 {metrics['n_rounds']} 轮")
            print(self.ev.interpret(metrics))
            print(f"{'='*50}")

        return result

    def run_history_replay(
        self,
        signal_dates: list,
        index_name: str = None,
    ) -> list:
        """
        历史回放：用历史数据模拟完整的信号->买入->结算流程。

        用于在真实信号积累前验证系统逻辑。

        Args:
            signal_dates: 信号日列表
            index_name: 指数池名称

        Returns:
            每个信号日的运行结果列表
        """
        index_name = index_name or self.config.default_index
        all_results = []

        for i, sig_date in enumerate(signal_dates):
            logger.info(f"\n{'='*60}")
            logger.info(f"回放 {i+1}/{len(signal_dates)}: 信号日 {sig_date}")
            logger.info(f"{'='*60}")

            # 生成信号
            try:
                signals = self.sg.generate(sig_date, index_name)
                round_id = self.pm.create_round(sig_date, index_name, signals)
                logger.info(f"  -> 信号生成完成: {round_id}")
            except Exception as e:
                logger.error(f"  -> 信号生成失败: {e}")
                all_results.append({'signal_date': sig_date, 'error': str(e)})
                continue

            # 模拟买入日
            buy_date = self.pm.get_next_trading_date(sig_date, 1)
            logger.info(f"  -> 模拟买入日: {buy_date}")
            self.se.fill_buy_prices(round_id, buy_date)

            # 模拟卖出日
            sell_date = self.pm.get_next_trading_date(buy_date, self.config.hold_days)
            logger.info(f"  -> 模拟卖出日: {sell_date}")
            settle_result = self.se.settle_round(round_id, sell_date)

            all_results.append({
                'signal_date': sig_date,
                'round_id': round_id,
                'buy_date': buy_date,
                'sell_date': sell_date,
                'settlement': settle_result,
            })

        # 最终评估
        if all_results:
            print(f"\n{'#'*60}")
            print(f"  历史回放完成: {len(signal_dates)} 轮")
            print(f"{'#'*60}")
            self.ev.print_report(index_name, min_rounds=1)

        return all_results
