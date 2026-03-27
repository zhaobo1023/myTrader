# -*- coding: utf-8 -*-
"""
绩效评估模块

汇总多轮 Paper Trading 数据，计算 IC、ICIR、超额收益、夏普等指标。
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from config.db import execute_query

logger = logging.getLogger(__name__)


class PerformanceEvaluator:
    """Paper Trading 绩效评估器"""

    def __init__(self, min_rounds: int = 4):
        self.min_rounds = min_rounds

    # ========== 数据加载 ==========

    def load_settled_rounds(
        self,
        index_name: str = None,
        min_rounds: int = None,
    ) -> Optional[pd.DataFrame]:
        """
        加载已结算的轮次数据。

        Args:
            index_name: 指数池名称过滤（None 表示全部）
            min_rounds: 最少轮次数

        Returns:
            DataFrame 或 None（数据不足时）
        """
        min_rounds = min_rounds or self.min_rounds

        if index_name:
            sql = """
                SELECT * FROM pt_rounds
                WHERE status = 'settled' AND index_name = %s
                ORDER BY signal_date ASC
            """
            rows = execute_query(sql, (index_name,))
        else:
            sql = """
                SELECT * FROM pt_rounds
                WHERE status = 'settled'
                ORDER BY signal_date ASC
            """
            rows = execute_query(sql)

        if not rows or len(rows) < min_rounds:
            return None

        df = pd.DataFrame(rows)
        # Decimal 转换
        for col in ['portfolio_ret', 'benchmark_ret', 'excess_ret', 'ic', 'rank_ic']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def load_position_details(self, round_id: str) -> Optional[pd.DataFrame]:
        """加载某个轮次的持仓明细"""
        rows = execute_query(
            "SELECT * FROM pt_positions WHERE round_id = %s ORDER BY pred_rank ASC",
            (round_id,)
        )
        if not rows:
            return None
        df = pd.DataFrame(rows)
        for col in ['pred_score', 'buy_price', 'sell_price', 'gross_ret', 'net_ret']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    # ========== 指标计算 ==========

    def compute_metrics(self, df: pd.DataFrame) -> dict:
        """
        计算全套绩效指标。

        Args:
            df: 已结算轮次 DataFrame（来自 load_settled_rounds）

        Returns:
            指标字典
        """
        ics = df['ic'].dropna().astype(float)
        rets = df['portfolio_ret'].dropna().astype(float)
        excs = df['excess_ret'].dropna().astype(float)

        # IC 系列
        ic_mean = ics.mean()
        ic_std = ics.std()
        icir = ic_mean / ic_std if ic_std > 0 else np.nan
        ic_pos_pct = (ics > 0).mean() * 100

        # RankIC 系列
        rank_ics = df['rank_ic'].dropna().astype(float)
        rank_ic_mean = rank_ics.mean() if len(rank_ics) > 0 else np.nan
        rank_ic_std = rank_ics.std() if len(rank_ics) > 1 else np.nan
        rank_icir = rank_ic_mean / rank_ic_std if rank_ic_std and rank_ic_std > 0 else np.nan

        # 收益系列
        # 复利累计
        cum_ret = (1 + rets / 100).prod() - 1
        cum_exc = excs.sum()

        # 最大单轮亏损
        max_loss = rets.min()

        # 年化（假设每周一轮，52轮/年）
        n = len(rets)
        annualized_ret = ((1 + cum_ret) ** (52 / n) - 1) * 100 if n > 0 else np.nan

        # 夏普比率（年化超额 / 超额标准差）
        if len(excs) > 1 and excs.std() > 0:
            sharpe = (excs.mean() / excs.std()) * np.sqrt(52)
        else:
            sharpe = np.nan

        # 胜率
        win_rate = (rets > 0).mean() * 100

        # 平均超额
        avg_excess = excs.mean() if len(excs) > 0 else np.nan

        # 超额胜率
        excess_win_rate = (excs > 0).mean() * 100 if len(excs) > 0 else np.nan

        return {
            'n_rounds': n,
            'ic_mean': round(float(ic_mean), 4),
            'ic_std': round(float(ic_std), 4),
            'icir': round(float(icir), 3),
            'ic_pos_pct': round(float(ic_pos_pct), 1),
            'rank_ic_mean': round(float(rank_ic_mean), 4) if not np.isnan(rank_ic_mean) else None,
            'rank_icir': round(float(rank_icir), 3) if not np.isnan(rank_icir) else None,
            'cum_ret_pct': round(float(cum_ret) * 100, 2),
            'cum_excess_pct': round(float(cum_exc), 2),
            'annualized_ret': round(float(annualized_ret), 2) if not np.isnan(annualized_ret) else None,
            'sharpe': round(float(sharpe), 2) if not np.isnan(sharpe) else None,
            'win_rate_pct': round(float(win_rate), 1),
            'avg_excess_pct': round(float(avg_excess), 2) if not np.isnan(avg_excess) else None,
            'excess_win_rate_pct': round(float(excess_win_rate), 1) if not np.isnan(excess_win_rate) else None,
            'max_loss_pct': round(float(max_loss), 2),
        }

    # ========== 结论生成 ==========

    def interpret(self, metrics: dict) -> str:
        """
        自动生成策略结论文字。
        """
        lines = []

        # IC 判断
        ic = metrics['ic_mean']
        if ic > 0.05:
            lines.append(f"[OK] IC={ic:.3f}，预测精度良好（>0.05）")
        elif ic > 0.03:
            lines.append(f"[--] IC={ic:.3f}，有基础预测能力（0.03~0.05）")
        elif ic > 0:
            lines.append(f"[!!] IC={ic:.3f}，预测能力较弱，建议优化因子")
        else:
            lines.append(f"[XX] IC={ic:.3f}<0，预测方向有问题，排查数据泄露")

        # ICIR 判断
        icir = metrics['icir']
        if icir is not None:
            if icir > 0.3:
                lines.append(f"[OK] ICIR={icir:.2f}，信号稳定性可接受")
            else:
                lines.append(f"[!!] ICIR={icir:.2f}，信号波动过大")

        # IC > 0 占比
        ic_pos = metrics['ic_pos_pct']
        if ic_pos > 55:
            lines.append(f"[OK] IC>0 占比 {ic_pos:.0f}%，方向正确率达标")
        else:
            lines.append(f"[!!] IC>0 占比 {ic_pos:.0f}%，方向准确率不足")

        # 累计超额
        exc = metrics['cum_excess_pct']
        if exc is not None:
            if exc > 0:
                lines.append(f"[OK] 累计超额收益 {exc:+.2f}%")
            else:
                lines.append(f"[XX] 累计超额收益 {exc:+.2f}%")

        # 综合指标
        sharpe = metrics.get('sharpe')
        max_loss = metrics['max_loss_pct']
        win_rate = metrics['win_rate_pct']

        lines.append(
            f"夏普 {sharpe:.2f}" if sharpe is not None else "夏普 N/A"
        )
        lines.append(
            f"最大单轮亏损 {max_loss:.2f}%，胜率 {win_rate:.0f}%"
        )

        # 总体判断
        if ic > 0.03 and icir > 0.3 and exc is not None and exc > 0:
            lines.append(">>> 策略表现良好，建议继续观察（需 >= 8 轮确认）")
        elif ic > 0:
            lines.append(">>> 策略有初步信号，需要更多轮次验证")
        else:
            lines.append(">>> 策略无效，建议优化因子或调整参数")

        return "\n".join(lines)

    # ========== 格式化输出 ==========

    def print_report(self, index_name: str = None, min_rounds: int = 1):
        """打印评估报告"""
        df = self.load_settled_rounds(index_name, min_rounds=min_rounds)
        if df is None:
            print("暂无已结算数据")
            return

        metrics = self.compute_metrics(df)
        label = index_name or "全部指数"

        print(f"\n{'='*60}")
        print(f"  Paper Trading 评估报告 - {label}（{len(df)} 轮）")
        print(f"{'='*60}")
        for k, v in metrics.items():
            print(f"  {k:<22} {v}")
        print(f"\n{'='*60}")
        print("  结论:")
        print(self.interpret(metrics))
        print(f"{'='*60}\n")

        # 打印每轮详情
        print("  每轮详情:")
        print(f"  {'信号日':<12} {'买入日':<12} {'卖出日':<12} "
              f"{'策略收益':>8} {'基准收益':>8} {'超额收益':>8} {'IC':>8}")
        print(f"  {'-'*76}")
        for _, row in df.iterrows():
            print(
                f"  {str(row['signal_date']):<12} "
                f"{str(row['buy_date']):<12} "
                f"{str(row['sell_date']):<12} "
                f"{float(row['portfolio_ret']):>7.2f}% "
                f"{float(row['benchmark_ret']):>7.2f}% "
                f"{float(row['excess_ret']):>7.2f}% "
                f"{float(row['ic']):>7.4f}"
            )
