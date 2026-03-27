# -*- coding: utf-8 -*-
"""
持仓管理模块

负责轮次创建、持仓记录管理、买卖日期计算。
"""
import logging
from datetime import date
from typing import List, Optional

import pandas as pd

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from config.db import execute_query, execute_update
from .config import PaperTradingConfig

logger = logging.getLogger(__name__)


class PositionManager:
    """持仓管理器"""

    def __init__(self, config: PaperTradingConfig = None):
        self.config = config or PaperTradingConfig()

    # ========== 交易日历工具 ==========

    def get_next_trading_date(self, base_date: date, offset: int = 1) -> date:
        """
        获取 base_date 之后第 offset 个交易日。

        从 trade_stock_daily 表查询实际交易日历。

        Args:
            base_date: 基准日期
            offset: 向后偏移的交易日数

        Returns:
            第 offset 个交易日的 date 对象
        """
        sql = """
            SELECT DISTINCT trade_date
            FROM trade_stock_daily
            WHERE trade_date > %s
            ORDER BY trade_date ASC
            LIMIT %s
        """
        rows = execute_query(sql, (base_date.strftime('%Y-%m-%d'), offset))
        if len(rows) < offset:
            raise ValueError(
                f"交易日历不足：无法获取 {base_date} 后第 {offset} 个交易日，"
                f"仅有 {len(rows)} 个交易日"
            )
        return rows[-1]['trade_date']

    def is_trading_day(self, d: date) -> bool:
        """判断某日是否为交易日"""
        sql = """
            SELECT 1 FROM trade_stock_daily
            WHERE trade_date = %s LIMIT 1
        """
        rows = execute_query(sql, (d.strftime('%Y-%m-%d'),))
        return len(rows) > 0

    # ========== 轮次管理 ==========

    def create_round(
        self,
        signal_date: date,
        index_name: str,
        signals: pd.DataFrame,
    ) -> str:
        """
        创建新一轮记录，写入 pt_rounds 和 pt_positions。

        Args:
            signal_date: 信号生成日
            index_name: 指数池名称
            signals: DataFrame，列: stock_code, pred_score, pred_rank

        Returns:
            round_id
        """
        round_id = f"{signal_date.strftime('%Y%m%d')}_{index_name}"

        # 计算买卖日期
        buy_date = self.get_next_trading_date(signal_date, offset=1)
        sell_date = self.get_next_trading_date(buy_date, offset=self.config.hold_days)

        logger.info(f"创建轮次 {round_id}: buy={buy_date}, sell={sell_date}")

        # 写 pt_rounds（使用 ON DUPLICATE KEY 避免重复创建）
        execute_update("""
            INSERT INTO pt_rounds
                (round_id, signal_date, buy_date, sell_date,
                 index_name, hold_days, top_n, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            ON DUPLICATE KEY UPDATE status = VALUES(status)
        """, (
            round_id, signal_date, buy_date, sell_date,
            index_name, self.config.hold_days, self.config.top_n
        ))

        # 写 pt_positions
        if signals is not None and len(signals) > 0:
            for _, row in signals.iterrows():
                execute_update("""
                    INSERT INTO pt_positions
                        (round_id, stock_code, pred_score, pred_rank, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                    ON DUPLICATE KEY UPDATE
                        pred_score = VALUES(pred_score),
                        pred_rank = VALUES(pred_rank)
                """, (
                    round_id,
                    row['stock_code'],
                    float(row['pred_score']),
                    int(row['pred_rank']),
                ))

        return round_id

    # ========== 查询方法 ==========

    def get_rounds_to_settle(self) -> List[dict]:
        """
        查询所有 sell_date <= today 且 status='active' 的轮次（需要结算）。
        """
        sql = """
            SELECT * FROM pt_rounds
            WHERE sell_date <= CURDATE()
            AND status = 'active'
            ORDER BY sell_date ASC
        """
        return execute_query(sql)

    def get_pending_buy_rounds(self) -> List[dict]:
        """
        查询所有 buy_date <= today 且 status='pending' 的轮次（需要记录买入价）。
        """
        sql = """
            SELECT * FROM pt_rounds
            WHERE buy_date <= CURDATE()
            AND status = 'pending'
            ORDER BY buy_date ASC
        """
        return execute_query(sql)

    def get_round(self, round_id: str) -> Optional[dict]:
        """查询单个轮次信息"""
        rows = execute_query(
            "SELECT * FROM pt_rounds WHERE round_id = %s",
            (round_id,)
        )
        return rows[0] if rows else None

    def get_positions(self, round_id: str, status: str = None) -> List[dict]:
        """查询轮次的持仓明细"""
        if status:
            sql = "SELECT * FROM pt_positions WHERE round_id = %s AND status = %s"
            return execute_query(sql, (round_id, status))
        return execute_query(
            "SELECT * FROM pt_positions WHERE round_id = %s",
            (round_id,)
        )

    def get_all_settled_rounds(self, index_name: str = None) -> List[dict]:
        """查询所有已结算轮次"""
        if index_name:
            return execute_query("""
                SELECT * FROM pt_rounds
                WHERE status = 'settled' AND index_name = %s
                ORDER BY signal_date ASC
            """, (index_name,))
        return execute_query("""
            SELECT * FROM pt_rounds
            WHERE status = 'settled'
            ORDER BY signal_date ASC
        """)

    def get_rounds_by_status(self, status: str) -> List[dict]:
        """按状态查询轮次"""
        return execute_query(
            "SELECT * FROM pt_rounds WHERE status = %s ORDER BY signal_date ASC",
            (status,)
        )

    # ========== 状态管理 ==========

    def cancel_round(self, round_id: str):
        """取消轮次"""
        execute_update("""
            UPDATE pt_rounds SET status = 'cancelled' WHERE round_id = %s
        """, (round_id,))
        execute_update("""
            UPDATE pt_positions SET status = 'cancelled' WHERE round_id = %s
        """, (round_id,))
