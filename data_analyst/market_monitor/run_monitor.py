# -*- coding: utf-8 -*-
"""
SVD 市场状态监控 - 主入口

支持:
  1. CLI 手动运行: python -m data_analyst.market_monitor.run_monitor --latest
  2. 编程调用: SVDMonitor().run(start_date, end_date)
  3. 定时调度: run_daily_monitor()
"""
import sys
import os
import argparse
import logging
from datetime import date, datetime, timedelta
from time import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from .config import SVDMonitorConfig
from .schemas import SVDRecord, MarketRegime
from .data_builder import DataBuilder
from .svd_engine import compute_svd, compute_variance_ratios
from .regime_classifier import RegimeClassifier
from .storage import SVDStorage
from .visualizer import plot_regime_chart
from .reporter import generate_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SVDMonitor:
    """SVD 市场状态监控器"""

    def __init__(self, config: SVDMonitorConfig = None):
        self.config = config or SVDMonitorConfig()
        self.data_builder = DataBuilder(self.config)
        self.classifier = RegimeClassifier(self.config)
        self.storage = SVDStorage

    def run(self, start_date: str, end_date: str = None,
            save_db: bool = True, generate_chart: bool = True,
            generate_report: bool = True) -> dict:
        """
        运行 SVD 市场监控

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD), 默认为今天
            save_db: 是否保存到数据库
            generate_chart: 是否生成图表
            generate_report: 是否生成报告

        Returns:
            dict: {records, regimes, chart_path, report_path}
        """
        if end_date is None:
            end_date = date.today().strftime('%Y-%m-%d')

        logger.info(f"=" * 60)
        logger.info(f"SVD 市场监控: {start_date} ~ {end_date}")
        logger.info(f"窗口配置: {self.config.windows}")
        logger.info(f"行业中性化: {self.config.industry_neutral}")
        logger.info(f"=" * 60)

        t0 = time()

        # 1. 初始化数据库
        if save_db:
            self.storage.init_table()

        # 2. 加载收益率数据
        logger.info("[1/5] 加载收益率数据...")
        returns_df = self.data_builder.load_returns(start_date, end_date)

        if returns_df.empty or len(returns_df) < max(self.config.windows.keys()):
            logger.error("数据不足，退出")
            return {'records': [], 'regimes': [], 'chart_path': None, 'report_path': None}

        # 3. 滚动窗口 SVD
        logger.info("[2/5] 滚动窗口 SVD 计算...")
        all_records = []
        T = len(returns_df)

        for window_size, step in self.config.windows.items():
            window_records = []
            for start_idx in range(0, T - window_size, step):
                mid_idx = start_idx + window_size // 2
                mid_date = returns_df.index[mid_idx]
                calc_date = mid_date.date() if hasattr(mid_date, 'date') else mid_date

                matrix, stock_count, _ = self.data_builder.build_window_matrix(
                    returns_df, start_idx, window_size
                )

                if matrix is None:
                    continue

                # SVD
                _, sigma, _ = compute_svd(matrix, self.config.n_components)
                ratios = compute_variance_ratios(sigma)

                record = SVDRecord(
                    calc_date=calc_date,
                    window_size=window_size,
                    top1_var_ratio=ratios['top1_var_ratio'],
                    top3_var_ratio=ratios['top3_var_ratio'],
                    top5_var_ratio=ratios['top5_var_ratio'],
                    reconstruction_error=ratios['reconstruction_error'],
                    stock_count=stock_count,
                    market_state="",  # 后续填充
                    is_mutation=0,
                )
                window_records.append(record)

            all_records.extend(window_records)
            logger.info(f"  窗口 {window_size}日: {len(window_records)} 个计算点")

        if not all_records:
            logger.error("无有效 SVD 结果")
            return {'records': [], 'regimes': [], 'chart_path': None, 'report_path': None}

        # 4. 市场状态分类
        logger.info("[3/5] 市场状态分类...")
        results_df = pd.DataFrame([r.model_dump() for r in all_records])
        unique_dates = sorted(results_df['calc_date'].unique())
        regimes = []

        for calc_date in unique_dates:
            regime = self.classifier.classify(results_df, calc_date)
            regimes.append(regime)

            # 回填 market_state 和 is_mutation 到 records
            for r in all_records:
                if r.calc_date == calc_date:
                    r.market_state = regime.market_state
                    r.is_mutation = 1 if regime.is_mutation else 0

        latest_regime = regimes[-1] if regimes else None
        if latest_regime:
            logger.info(f"  最新状态: {latest_regime.market_state} "
                        f"(score={latest_regime.final_score:.1%}, "
                        f"mutation={latest_regime.is_mutation})")

        # 5. 保存 + 可视化 + 报告
        chart_path = None
        report_path = None

        if save_db:
            logger.info("[4/5] 保存到数据库...")
            self.storage.save_batch(all_records)
            logger.info(f"  保存 {len(all_records)} 条记录")

        if generate_chart:
            logger.info("[5/5] 生成图表...")
            chart_path = plot_regime_chart(
                results_df, regimes,
                output_dir=self.config.output_dir
            )

        if generate_report and latest_regime:
            report_path = generate_report(
                latest_regime, results_df, chart_path,
                output_dir=self.config.output_dir
            )

        elapsed = time() - t0
        logger.info(f"=" * 60)
        logger.info(f"完成! 耗时 {elapsed:.1f}s")
        logger.info(f"图表: {chart_path}")
        logger.info(f"报告: {report_path}")
        logger.info(f"=" * 60)

        return {
            'records': all_records,
            'regimes': regimes,
            'chart_path': chart_path,
            'report_path': report_path,
        }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='SVD 市场状态监控')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--latest', action='store_true', help='仅计算最新一天')
    parser.add_argument('--backfill-days', type=int, default=365,
                        help='回填天数 (默认 365)')
    parser.add_argument('--no-db', action='store_true', help='不保存数据库')
    parser.add_argument('--no-chart', action='store_true', help='不生成图表')
    parser.add_argument('--industry-neutral', action='store_true',
                        help='开启行业中性化')

    args = parser.parse_args()

    config = SVDMonitorConfig()
    if args.industry_neutral:
        config.industry_neutral = True

    monitor = SVDMonitor(config)

    if args.latest:
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=args.backfill_days)).strftime('%Y-%m-%d')
    elif args.start:
        start_date = args.start
        end_date = args.end or date.today().strftime('%Y-%m-%d')
    else:
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=args.backfill_days)).strftime('%Y-%m-%d')

    monitor.run(
        start_date=start_date,
        end_date=end_date,
        save_db=not args.no_db,
        generate_chart=not args.no_chart,
    )


def run_daily_monitor():
    """供 scheduler_service 调用的每日监控入口"""
    config = SVDMonitorConfig()
    monitor = SVDMonitor(config)

    end_date = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=400)).strftime('%Y-%m-%d')

    result = monitor.run(start_date=start_date, end_date=end_date)

    if result['regimes']:
        latest = result['regimes'][-1]
        if latest.is_mutation:
            logger.warning(f"突变警报! 市场状态: {latest.market_state}, "
                           f"综合得分: {latest.final_score:.1%}")
            try:
                from data_analyst.services.alert_service import AlertService
                alert = AlertService()
                alert.send_text(
                    f"SVD 突变警报\n"
                    f"市场状态: {latest.market_state}\n"
                    f"综合得分: {latest.final_score:.1%}\n"
                    f"请关注市场风险!"
                )
            except Exception as e:
                logger.warning(f"发送报警失败: {e}")


if __name__ == '__main__':
    main()
