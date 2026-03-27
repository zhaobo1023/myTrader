# -*- coding: utf-8 -*-
"""
收益结算模块

在到期后从行情表读取价格，计算各项收益指标。
支持:
- T+1 买入价填充（收盘价）
- T+N 卖出结算
- Spearman IC 计算
- 基准收益对比
"""
import logging
from datetime import date
from typing import List, Optional

import numpy as np
from scipy.stats import spearmanr

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from config.db import execute_query, execute_update
from .config import PaperTradingConfig

logger = logging.getLogger(__name__)


class SettlementEngine:
    """收益结算引擎"""

    def __init__(self, config: PaperTradingConfig = None):
        self.config = config or PaperTradingConfig()

    # ========== 价格查询 ==========

    def _get_close_price(self, trade_date, stock_code: str) -> Optional[float]:
        """查询某只股票某日的收盘价"""
        if isinstance(trade_date, date):
            trade_date = trade_date.strftime('%Y-%m-%d')
        rows = execute_query("""
            SELECT close_price FROM trade_stock_daily
            WHERE trade_date = %s AND stock_code = %s
        """, (trade_date, stock_code))
        if rows and rows[0]['close_price'] is not None:
            return float(rows[0]['close_price'])
        return None

    # ========== 买入价填充 ==========

    def fill_buy_prices(self, round_id: str, buy_date):
        """
        T+1 日收盘后，将买入价写入 pt_positions。

        买入价 = buy_date 的收盘价。
        更严格可改用开盘价（open_price）。

        Args:
            round_id: 轮次 ID
            buy_date: 买入日期
        """
        if isinstance(buy_date, str):
            buy_date = date.fromisoformat(buy_date)

        positions = execute_query(
            "SELECT * FROM pt_positions WHERE round_id = %s AND status = 'pending'",
            (round_id,)
        )

        if not positions:
            logger.warning(f"轮次 {round_id} 没有 pending 状态的持仓")
            return

        filled = 0
        for pos in positions:
            buy_price = self._get_close_price(buy_date, pos['stock_code'])
            if buy_price is not None:
                execute_update("""
                    UPDATE pt_positions
                    SET buy_price = %s, status = 'active'
                    WHERE id = %s
                """, (buy_price, pos['id']))
                filled += 1
            else:
                logger.warning(
                    f"轮次 {round_id} 股票 {pos['stock_code']} "
                    f"买入日 {buy_date} 无价格数据，跳过"
                )

        # 更新轮次状态为 active
        if filled > 0:
            execute_update(
                "UPDATE pt_rounds SET status = 'active' WHERE round_id = %s AND status = 'pending'",
                (round_id,)
            )
            logger.info(f"轮次 {round_id}: 填入 {filled}/{len(positions)} 只股票买入价")

    # ========== 卖出结算 ==========

    def settle_round(
        self,
        round_id: str,
        sell_date,
        benchmark_ret: float = None,
    ) -> Optional[dict]:
        """
        卖出日结算：读取卖出价，计算收益，写回 pt_rounds。

        Args:
            round_id: 轮次 ID
            sell_date: 卖出日期
            benchmark_ret: 基准收益（%），从行情数据自动计算或手动传入

        Returns:
            结算结果字典，或 None（无有效持仓时）
        """
        if isinstance(sell_date, str):
            sell_date = date.fromisoformat(sell_date)

        positions = execute_query(
            "SELECT * FROM pt_positions WHERE round_id = %s AND status = 'active'",
            (round_id,)
        )

        if not positions:
            logger.warning(f"轮次 {round_id} 没有 active 状态的持仓")
            return None

        stock_rets = []
        skipped = 0

        for pos in positions:
            sell_price = self._get_close_price(sell_date, pos['stock_code'])
            buy_price = float(pos['buy_price']) if pos['buy_price'] else None

            if sell_price is None or buy_price is None:
                skipped += 1
                continue

            gross_ret = (sell_price - buy_price) / buy_price * 100
            net_ret = gross_ret - self.config.cost_rate * 100  # 扣交易成本

            execute_update("""
                UPDATE pt_positions
                SET sell_price = %s, gross_ret = %s, net_ret = %s,
                    status = 'settled', settled_at = NOW()
                WHERE id = %s
            """, (sell_price, round(gross_ret, 6), round(net_ret, 6), pos['id']))

            stock_rets.append({
                'stock_code': pos['stock_code'],
                'pred_score': float(pos['pred_score']),
                'net_ret': net_ret,
            })

        if skipped > 0:
            logger.warning(f"轮次 {round_id}: {skipped} 只股票停牌或数据缺失")

        if not stock_rets:
            logger.warning(f"轮次 {round_id}: 无有效持仓可结算")
            return None

        # 计算组合收益（等权）
        portfolio_ret = np.mean([s['net_ret'] for s in stock_rets])

        # 计算 Spearman IC
        scores = [s['pred_score'] for s in stock_rets]
        actuals = [s['net_ret'] for s in stock_rets]
        if len(scores) >= 3:
            ic, _ = spearmanr(scores, actuals)
        else:
            ic = None

        # 更新实际排名到 pt_positions（用于 RankIC）
        sorted_by_ret = sorted(stock_rets, key=lambda x: -x['net_ret'])
        for rank_i, s in enumerate(sorted_by_ret, 1):
            execute_update("""
                UPDATE pt_positions SET actual_rank = %s
                WHERE round_id = %s AND stock_code = %s
            """, (rank_i, round_id, s['stock_code']))

        # 自动计算基准收益
        if benchmark_ret is None:
            benchmark_ret = self._calc_benchmark_ret(round_id, sell_date)

        excess_ret = (
            round(portfolio_ret - benchmark_ret, 6)
            if benchmark_ret is not None else None
        )

        # 计算 RankIC
        pred_ranks = [s['pred_score'] for s in stock_rets]
        actual_ranks = [s['net_ret'] for s in stock_rets]
        if len(pred_ranks) >= 3:
            rank_ic, _ = spearmanr(
                range(len(pred_ranks)),  # pred 排名（已按 score 排序）
                [actual_ranks[i] for i in np.argsort(pred_ranks)[::-1]]
            )
        else:
            rank_ic = None

        # 写回 pt_rounds
        execute_update("""
            UPDATE pt_rounds
            SET portfolio_ret = %s, benchmark_ret = %s, excess_ret = %s,
                ic = %s, rank_ic = %s,
                status = 'settled', settled_at = NOW()
            WHERE round_id = %s
        """, (
            round(portfolio_ret, 6),
            round(benchmark_ret, 6) if benchmark_ret is not None else None,
            excess_ret,
            round(ic, 6) if ic is not None else None,
            round(rank_ic, 6) if rank_ic is not None else None,
            round_id,
        ))

        result = {
            'round_id': round_id,
            'portfolio_ret': round(portfolio_ret, 4),
            'benchmark_ret': round(benchmark_ret, 4) if benchmark_ret is not None else None,
            'excess_ret': excess_ret,
            'ic': round(ic, 4) if ic is not None else None,
            'rank_ic': round(rank_ic, 4) if rank_ic is not None else None,
            'n_stocks': len(stock_rets),
            'n_skipped': skipped,
        }

        bm_str = f"{result['benchmark_ret']:.2f}%" if result['benchmark_ret'] is not None else "N/A"
        ex_str = f"{result['excess_ret']:.2f}%" if result['excess_ret'] is not None else "N/A"
        ic_str = f"{result['ic']:.4f}" if result['ic'] is not None else "N/A"

        logger.info(
            f"轮次 {round_id} 结算完成: "
            f"策略 {result['portfolio_ret']:.2f}%, "
            f"基准 {bm_str}, "
            f"超额 {ex_str}, "
            f"IC={ic_str}, "
            f"有效 {result['n_stocks']} 只"
        )

        return result

    # ========== 基准收益计算 ==========

    def _calc_benchmark_ret(self, round_id: str, sell_date: date) -> Optional[float]:
        """
        从 pt_benchmark 表自动计算区间收益。

        Returns:
            基准区间收益率（%），或 None（无数据时）
        """
        round_info = execute_query(
            "SELECT * FROM pt_rounds WHERE round_id = %s",
            (round_id,)
        )
        if not round_info:
            return None

        round_info = round_info[0]
        buy_date = round_info['buy_date']

        prices = execute_query("""
            SELECT trade_date, close_price FROM pt_benchmark
            WHERE index_name = %s AND trade_date IN (%s, %s)
            ORDER BY trade_date
        """, (round_info['index_name'], buy_date, sell_date))

        if len(prices) < 2:
            # 尝试从 trade_stock_daily 用指数代码查
            index_code = self.config.get_index_code(round_info['index_name'])
            if index_code:
                prices = execute_query("""
                    SELECT trade_date, close_price FROM trade_stock_daily
                    WHERE stock_code = %s AND trade_date IN (%s, %s)
                    ORDER BY trade_date
                """, (index_code, buy_date, sell_date))

            if len(prices) < 2:
                logger.warning(
                    f"轮次 {round_id} 基准 {round_info['index_name']} 价格数据不足"
                )
                return None

        buy_p = float(prices[0]['close_price'])
        sell_p = float(prices[1]['close_price'])
        return (sell_p - buy_p) / buy_p * 100

    # ========== 批量结算 ==========

    def settle_all_pending(self) -> List[dict]:
        """结算所有到期轮次"""
        from .position_manager import PositionManager
        pm = PositionManager(self.config)

        to_settle = pm.get_rounds_to_settle()
        results = []

        for r in to_settle:
            result = self.settle_round(r['round_id'], r['sell_date'])
            if result:
                results.append(result)

        return results

    def fill_all_pending_buys(self) -> int:
        """填充所有待买入轮次的买入价"""
        from .position_manager import PositionManager
        pm = PositionManager(self.config)

        pending = pm.get_pending_buy_rounds()
        count = 0

        for r in pending:
            self.fill_buy_prices(r['round_id'], r['buy_date'])
            count += 1

        return count
