# -*- coding: utf-8 -*-
"""
SVD 市场状态监控 - 主入口

支持:
  1. CLI 手动运行: python -m data_analyst.market_monitor.run_monitor --latest
  2. 多股票池: --universe 全A / --universe SW_L1 / --universe SW_L1:银行
  3. 编程调用: SVDMonitor().run(start_date, end_date)
  4. 定时调度: run_daily_monitor()
"""
import sys
import os
import types
import argparse
import logging
import importlib
from datetime import date, datetime, timedelta
from time import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

# 支持直接运行: python data_analyst/market_monitor/run_monitor.py
# 通过注册 dummy data_analyst 包绕过 data_analyst/__init__.py 的 xtquant 导入
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _register_dummy_parent_package():
    """注册空的 data_analyst 包到 sys.modules，防止 __init__.py 中的 xtquant 导入"""
    if 'data_analyst' not in sys.modules:
        dummy = types.ModuleType('data_analyst')
        dummy.__path__ = [os.path.join(_PROJECT_ROOT, 'data_analyst')]
        dummy.__package__ = 'data_analyst'
        sys.modules['data_analyst'] = dummy
    if 'data_analyst.market_monitor' not in sys.modules:
        dummy_sub = types.ModuleType('data_analyst.market_monitor')
        dummy_sub.__path__ = [_THIS_DIR]
        dummy_sub.__package__ = 'data_analyst.market_monitor'
        sys.modules['data_analyst.market_monitor'] = dummy_sub


def _load_sibling(name):
    """加载同目录模块，绕过 data_analyst/__init__.py"""
    import importlib.util
    full_name = f"data_analyst.market_monitor.{name}"
    filepath = os.path.join(_THIS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(full_name, filepath)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "data_analyst.market_monitor"  # 使相对导入生效
    # 将模块注册到 sys.modules 以支持相对导入
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# 注册 dummy 包并加载同包模块
_register_dummy_parent_package()


# 加载同包模块
_config_mod = _load_sibling("config")
_schemas_mod = _load_sibling("schemas")
_svd_engine_mod = _load_sibling("svd_engine")
_regime_classifier_mod = _load_sibling("regime_classifier")
_storage_mod = _load_sibling("storage")
_visualizer_mod = _load_sibling("visualizer")
_reporter_mod = _load_sibling("reporter")
_data_builder_mod = _load_sibling("data_builder")

SVDMonitorConfig = _config_mod.SVDMonitorConfig
SVDRecord = _schemas_mod.SVDRecord
MarketRegime = _schemas_mod.MarketRegime
DataBuilder = _data_builder_mod.DataBuilder
compute_svd = _svd_engine_mod.compute_svd
compute_variance_ratios = _svd_engine_mod.compute_variance_ratios
RegimeClassifier = _regime_classifier_mod.RegimeClassifier
SVDStorage = _storage_mod.SVDStorage
plot_regime_chart = _visualizer_mod.plot_regime_chart
plot_industry_heatmap = _visualizer_mod.plot_industry_heatmap
generate_report = _reporter_mod.generate_report
generate_industry_report = _reporter_mod.generate_industry_report

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
            do_generate_report: bool = True,
            universe_type: str = "全A", universe_id: str = "",
            stock_codes: list = None) -> dict:
        """
        运行 SVD 市场监控

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD), 默认为今天
            save_db: 是否保存到数据库
            generate_chart: 是否生成图表
            do_generate_report: 是否生成报告
            universe_type: 股票池类型 ("全A" / "SW_L1")
            universe_id: 股票池 ID (行业名，全A时为空)
            stock_codes: 可选，直接指定股票列表

        Returns:
            dict: {records, regimes, chart_path, report_path}
        """
        if end_date is None:
            end_date = date.today().strftime('%Y-%m-%d')

        universe_label = f"{universe_type}:{universe_id}" if universe_id else universe_type
        logger.info(f"=" * 60)
        logger.info(f"SVD 市场监控: {start_date} ~ {end_date}")
        logger.info(f"股票池: {universe_label}")
        logger.info(f"窗口配置: {self.config.windows}")
        logger.info(f"行业中性化: {self.config.industry_neutral}")
        logger.info(f"=" * 60)

        t0 = time()

        # 1. 初始化数据库 (失败不阻断)
        if save_db:
            try:
                self.storage.init_table()
            except Exception as e:
                logger.warning(f"DB 初始化失败，将跳过保存: {e}")
                save_db = False

        # 2. 加载收益率数据
        logger.info("[1/5] 加载收益率数据...")
        returns_df = self.data_builder.load_returns(start_date, end_date, stock_codes)

        if returns_df.empty or len(returns_df) < max(self.config.windows.keys()):
            logger.error("数据不足，退出")
            return {'records': [], 'regimes': [], 'chart_path': None, 'report_path': None}

        # 3. 滚动窗口 SVD
        logger.info("[2/5] 滚动窗口 SVD 计算...")
        all_records = []
        T = len(returns_df)

        for window_size, step in self.config.windows.items():
            window_records = []
            # Collect start indices: regular rolling + anchor to latest
            starts = list(range(0, T - window_size + 1, step))
            latest_start = T - window_size
            if latest_start > 0 and (not starts or starts[-1] != latest_start):
                starts.append(latest_start)

            for start_idx in starts:
                end_idx = start_idx + window_size - 1
                end_date_ts = returns_df.index[end_idx]
                calc_date = end_date_ts.date() if hasattr(end_date_ts, 'date') else end_date_ts

                matrix, stock_count, _ = self.data_builder.build_window_matrix(
                    returns_df, start_idx, window_size, stock_codes
                )

                if matrix is None:
                    continue

                # SVD
                _, sigma, _ = compute_svd(matrix, self.config.n_components)
                ratios = compute_variance_ratios(sigma)

                record = SVDRecord(
                    calc_date=calc_date,
                    window_size=window_size,
                    universe_type=universe_type,
                    universe_id=universe_id,
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

        # 5. 保存 + 可视化 + 报告 (DB 失败不阻断后续步骤)
        chart_path = None
        report_path = None

        if save_db:
            logger.info("[4/5] 保存到数据库...")
            try:
                self.storage.save_batch(all_records)
                logger.info(f"  保存 {len(all_records)} 条记录")
            except Exception as e:
                logger.error(f"  DB 保存失败 (图表/报告仍将生成): {e}")

        if generate_chart:
            logger.info("[5/5] 生成图表...")
            chart_path = plot_regime_chart(
                results_df, regimes,
                output_dir=self.config.output_dir
            )

        if do_generate_report and latest_regime:
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

    def run_sw_l1_industries(self, start_date: str, end_date: str = None,
                             save_db: bool = True,
                             min_industry_stocks: int = 10) -> dict:
        """
        对所有申万一级行业分别运行 SVD 监控

        数据加载策略: 一次加载全 A 数据，在内存中按行业切片，避免重复查询。

        Args:
            start_date: 开始日期
            end_date: 结束日期
            save_db: 是否保存到数据库
            min_industry_stocks: 行业最少股票数 (低于此数跳过)

        Returns:
            dict: {industry_name: run_result, ...}
        """
        if end_date is None:
            end_date = date.today().strftime('%Y-%m-%d')

        t0 = time()
        logger.info(f"=" * 60)
        logger.info(f"SVD 行业监控: {start_date} ~ {end_date}")
        logger.info(f"=" * 60)

        # 1. 加载全 A 数据 (一次性)
        logger.info("[1/3] 加载全 A 收益率数据...")
        returns_df = self.data_builder.load_returns(start_date, end_date)
        if returns_df.empty:
            logger.error("数据加载失败")
            return {}

        # 2. 加载行业映射
        logger.info("[2/3] 加载行业映射...")
        industry_stocks = self.data_builder.load_industry_stocks()

        # 过滤小行业
        valid_industries = {
            ind: stocks for ind, stocks in industry_stocks.items()
            if len(stocks) >= min_industry_stocks
        }
        logger.info(f"有效行业: {len(valid_industries)}/{len(industry_stocks)} "
                     f"(过滤 < {min_industry_stocks} 只)")

        # 3. 逐行业运行 SVD
        logger.info(f"[3/3] 逐行业 SVD 计算 ({len(valid_industries)} 个行业)...")
        results = {}
        success_count = 0
        skip_count = 0

        for i, (industry_name, stocks) in enumerate(sorted(valid_industries.items()), 1):
            # 检查行业股票是否在 returns_df 中
            available_stocks = [s for s in stocks if s in returns_df.columns]
            if len(available_stocks) < min_industry_stocks:
                skip_count += 1
                continue

            logger.info(f"  [{i}/{len(valid_industries)}] {industry_name} "
                        f"({len(available_stocks)} 只股票)...")

            # 行业 SVD: 在内存中切片
            industry_returns = returns_df[available_stocks]
            T = len(industry_returns)

            industry_records = []
            for window_size, step in self.config.windows.items():
                starts = list(range(0, T - window_size + 1, step))
                latest_start = T - window_size
                if latest_start > 0 and (not starts or starts[-1] != latest_start):
                    starts.append(latest_start)

                for start_idx in starts:
                    end_idx = start_idx + window_size - 1
                    end_date_ts = industry_returns.index[end_idx]
                    calc_date = end_date_ts.date() if hasattr(end_date_ts, 'date') else end_date_ts

                    matrix, stock_count, _ = self.data_builder.build_window_matrix(
                        industry_returns, start_idx, window_size, available_stocks
                    )

                    if matrix is None:
                        continue

                    _, sigma, _ = compute_svd(matrix, self.config.n_components)
                    ratios = compute_variance_ratios(sigma)

                    record = SVDRecord(
                        calc_date=calc_date,
                        window_size=window_size,
                        universe_type="SW_L1",
                        universe_id=industry_name,
                        top1_var_ratio=ratios['top1_var_ratio'],
                        top3_var_ratio=ratios['top3_var_ratio'],
                        top5_var_ratio=ratios['top5_var_ratio'],
                        reconstruction_error=ratios['reconstruction_error'],
                        stock_count=stock_count,
                        market_state="",
                        is_mutation=0,
                    )
                    industry_records.append(record)

            if not industry_records:
                skip_count += 1
                continue

            # 市场状态分类 (每个行业独立 classifier + 分位数阈值)
            ind_df = pd.DataFrame([r.model_dump() for r in industry_records])
            unique_dates = sorted(ind_df['calc_date'].unique())
            # 行业独立 classifier: 避免行业间突变状态互相污染
            ind_classifier = RegimeClassifier(self.config)
            regimes = []
            for calc_date in unique_dates:
                regime = ind_classifier.classify(
                    ind_df, calc_date, use_percentile=True
                )
                regimes.append(regime)
                for r in industry_records:
                    if r.calc_date == calc_date:
                        r.market_state = regime.market_state
                        r.is_mutation = 1 if regime.is_mutation else 0

            results[industry_name] = {
                'records': industry_records,
                'regimes': regimes,
            }
            success_count += 1

            # DB 保存 (每个行业单独保存，失败不阻断)
            if save_db:
                try:
                    self.storage.save_batch(industry_records)
                except Exception as e:
                    logger.warning(f"    DB 保存失败: {e}")

        elapsed = time() - t0
        logger.info(f"=" * 60)
        logger.info(f"行业 SVD 完成! 成功 {success_count}, 跳过 {skip_count}, 耗时 {elapsed:.1f}s")
        logger.info(f"=" * 60)

        # 4. 生成行业热力图
        if results:
            try:
                heatmap_path = plot_industry_heatmap(
                    results, output_dir=self.config.output_dir
                )
                logger.info(f"行业热力图: {heatmap_path}")
            except Exception as e:
                logger.warning(f"行业热力图生成失败: {e}")

        # 5. 生成行业总览报告
        if results:
            try:
                report_path = generate_industry_report(
                    results, output_dir=self.config.output_dir
                )
                logger.info(f"行业报告: {report_path}")
            except Exception as e:
                logger.warning(f"行业报告生成失败: {e}")

        return results


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
    parser.add_argument('--min-stocks', type=int, default=None,
                        help='最小有效股票数 (覆盖默认值)')
    parser.add_argument('--universe', type=str, default='全A',
                        help='股票池: 全A / SW_L1 (全部行业) / SW_L1:银行 (单个行业)')
    parser.add_argument('--min-industry-stocks', type=int, default=10,
                        help='行业 SVD 最少股票数 (默认 10)')

    args = parser.parse_args()

    config = SVDMonitorConfig()
    if args.industry_neutral:
        config.industry_neutral = True
    if args.min_stocks is not None:
        config.min_stock_count = args.min_stocks

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

    save_db = not args.no_db

    # 解析 --universe 参数
    if args.universe == 'SW_L1':
        # 所有申万一级行业
        monitor.run_sw_l1_industries(
            start_date=start_date,
            end_date=end_date,
            save_db=save_db,
            min_industry_stocks=args.min_industry_stocks,
        )
    elif args.universe.startswith('SW_L1:'):
        # 单个行业
        industry_name = args.universe.split(':', 1)[1]
        logger.info(f"单行业模式: {industry_name}")
        # 先加载行业映射获取股票列表
        industry_stocks = monitor.data_builder.load_industry_stocks()
        stocks = industry_stocks.get(industry_name, [])
        if not stocks:
            logger.error(f"未找到行业: {industry_name}")
            return
        monitor.run(
            start_date=start_date,
            end_date=end_date,
            save_db=save_db,
            generate_chart=not args.no_chart,
            universe_type="SW_L1",
            universe_id=industry_name,
            stock_codes=stocks,
        )
    else:
        # 全 A (默认)
        monitor.run(
            start_date=start_date,
            end_date=end_date,
            save_db=save_db,
            generate_chart=not args.no_chart,
            universe_type="全A",
            universe_id="",
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
