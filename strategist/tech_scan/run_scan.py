# -*- coding: utf-8 -*-
"""
技术面扫描主入口

每日盘后自动扫描持仓股票的技术面状态
"""
import sys
import os
import pandas as pd
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from .config import ScanConfig, DEFAULT_CONFIG
from .portfolio_parser import PortfolioParser
from .data_fetcher import DataFetcher
from .indicator_calculator import IndicatorCalculator
from .signal_detector import SignalDetector, SignalLevel, SignalTag
from .report_generator import ReportGenerator
from .backlog_manager import BacklogManager
from .chart_generator import ChartGenerator


# 上证指数代码
INDEX_CODE = '000001.SH'
INDEX_NAME = '上证指数'


def setup_logging(config: ScanConfig, scan_date: datetime) -> logging.Logger:
    """配置日志（使用独立 logger 避免影响全局）"""
    config.ensure_dirs()

    log_file = Path(config.log_dir) / f"scan_{scan_date.strftime('%Y%m%d')}.log"

    logger = logging.getLogger('tech_scan')
    logger.setLevel(logging.INFO)

    logger.handlers.clear()

    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def _find_prev_report(output_dir: str, scan_date: datetime) -> str:
    """查找前一天的报告文件"""
    output_path = Path(output_dir)
    for i in range(1, 6):
        prev_date = scan_date - timedelta(days=i)
        filename = f"TechScan_{prev_date.strftime('%Y%m%d')}.md"
        filepath = output_path / filename
        if filepath.exists():
            return str(filepath)
    return None


def _fetch_index_status(fetcher: DataFetcher, calculator: IndicatorCalculator) -> dict:
    """
    获取上证指数的技术状态

    Returns:
        {'name': str, 'code': str, 'trend': str, 'pct': float}
    """
    try:
        df = fetcher.fetch_daily_data([INDEX_CODE], lookback_days=300)
        if df.empty:
            return {}

        df = calculator.calculate_all(df)

        latest_date = df['trade_date'].max()
        latest = df[df['trade_date'] == latest_date].iloc[0]

        detector = SignalDetector()
        trend = detector.get_trend_status(latest)

        pct = latest.get('pct_change')
        if pct is not None and not pd.isna(pct):
            pct = float(pct)
        else:
            pct = None

        return {
            'name': INDEX_NAME,
            'code': INDEX_CODE,
            'trend': trend,
            'pct': pct
        }
    except Exception as e:
        logging.getLogger('tech_scan').warning(f"获取指数状态失败: {e}")
        return {}


def _save_daily_summary(output_dir: str, scan_date: datetime, analysis_results: list):
    """
    保存每日摘要 CSV

    记录每只标的的颜色标签，用于连续性分析。
    """
    summary_path = Path(output_dir) / "Daily_Summary.csv"

    rows = []
    for r in analysis_results:
        # 判断颜色
        if r['is_danger']:
            color = 'DANGER'
        elif r['has_divergence']:
            color = 'DIVERGENCE'
        elif any(s.level == SignalLevel.RED for s in r['signals']):
            color = 'RED'
        elif any(s.level == SignalLevel.YELLOW for s in r['signals']):
            color = 'YELLOW'
        elif any(s.level == SignalLevel.GREEN for s in r['signals']):
            color = 'GREEN'
        else:
            color = 'NORMAL'

        rows.append({
            'date': scan_date.strftime('%Y-%m-%d'),
            'code': r['code'],
            'name': r['name'],
            'level': r['level'],
            'color': color,
            'close': round(r['close'], 2) if r['close'] and not pd.isna(r['close']) else '',
            'pnl_pct': round(r['pnl_pct'], 2) if r['pnl_pct'] is not None else '',
            'rps': round(r['rps'], 0) if r['rps'] is not None and not pd.isna(r['rps']) else '',
            'trend': r['trend'],
        })

    df_summary = pd.DataFrame(rows)

    # 追加模式
    if summary_path.exists():
        existing = pd.read_csv(summary_path)
        # 去重：同一日期的同一代码只保留最新
        existing = existing[existing['date'] != scan_date.strftime('%Y-%m-%d')]
        df_summary = pd.concat([existing, df_summary], ignore_index=True)

    df_summary.to_csv(summary_path, index=False)
    logging.getLogger('tech_scan').info(f"Daily Summary 已保存: {summary_path}")


def run_daily_scan(
    config: ScanConfig = None,
    scan_date: datetime = None
) -> str:
    """
    执行每日技术面扫描

    Args:
        config: 扫描配置
        scan_date: 扫描日期（默认今天）

    Returns:
        报告文件路径
    """
    if config is None:
        config = DEFAULT_CONFIG

    if scan_date is None:
        scan_date = datetime.now()

    logger = setup_logging(config, scan_date)
    logger.info("=" * 60)
    logger.info(f"开始技术面扫描 - {scan_date.strftime('%Y-%m-%d')}")
    logger.info("=" * 60)

    backlog = BacklogManager(config.output_dir)

    # 1. 解析持仓文件
    logger.info(f"解析持仓文件: {config.portfolio_file}")
    try:
        parser = PortfolioParser(config.portfolio_file)
        positions = parser.parse()
        logger.info(f"解析到 {len(positions)} 只 A股/ETF")

        for level in ['L1', 'L2', 'L3']:
            level_pos = [p for p in positions if p.level == level]
            if level_pos:
                codes = [p.code for p in level_pos]
                logger.info(f"  {level}: {len(level_pos)} 只 - {codes}")
    except Exception as e:
        logger.error(f"持仓文件解析失败: {e}")
        raise

    if not positions:
        logger.warning("未解析到任何持仓，退出")
        return None

    stock_codes = [p.code for p in positions]

    # 2. 获取行情数据
    logger.info(f"获取行情数据 (env={config.db_env})")
    fetcher = DataFetcher(env=config.db_env)

    availability = fetcher.check_data_availability(stock_codes)
    if availability['missing']:
        for code in availability['missing']:
            pos = next((p for p in positions if p.code == code), None)
            name = pos.name if pos else ''
            backlog.add_data_missing(code, name)
        logger.warning(f"以下股票无数据: {availability['missing']}")

    if not availability['available']:
        logger.error("所有股票均无数据，退出")
        backlog.save(scan_date)
        return None

    logger.info(f"最新交易日: {availability['latest_date']}")

    df = fetcher.fetch_daily_data(availability['available'], config.lookback_days)
    if df.empty:
        logger.error("获取日线数据失败")
        return None

    logger.info(f"获取到 {len(df)} 条日线数据")

    # 3. 获取 RPS 数据
    logger.info("获取 RPS 数据")
    rps_df = fetcher.fetch_rps_data(availability['available'])
    if rps_df.empty:
        logger.warning("未获取到 RPS 数据，将使用持仓内相对排名")
        for code in availability['available']:
            pos = next((p for p in positions if p.code == code), None)
            name = pos.name if pos else ''
            backlog.add_rps_missing(code, name)

    # 4. 计算技术指标
    logger.info("计算技术指标")
    calculator = IndicatorCalculator(
        ma_windows=config.ma_windows,
        rsi_period=config.rsi_period,
        macd_fast=config.macd_fast,
        macd_slow=config.macd_slow,
        macd_signal=config.macd_signal
    )

    df = calculator.calculate_all(df)

    if not rps_df.empty:
        rps_cols = ['stock_code', 'trade_date']
        for col in ['rps_120', 'rps_250', 'rps_slope']:
            if col in rps_df.columns:
                rps_cols.append(col)
        df = df.merge(
            rps_df[rps_cols],
            on=['stock_code', 'trade_date'],
            how='left'
        )
    else:
        df = calculator.calc_rps(df, window=250)

    # 5. 获取指数状态
    logger.info("获取指数锚点数据")
    index_status = _fetch_index_status(fetcher, calculator)
    if index_status:
        logger.info(f"指数 {index_status['name']}: 趋势={index_status['trend']}, "
                     f"涨跌={index_status.get('pct', '-'):+.2f}%")

    # 6. 获取最新一天的数据
    latest_date = df['trade_date'].max()
    latest_df = df[df['trade_date'] == latest_date].copy()
    logger.info(f"分析日期: {latest_date.strftime('%Y-%m-%d')}, {len(latest_df)} 只股票")

    for code in availability['available']:
        stock_df = df[df['stock_code'] == code]
        if len(stock_df) < 250:
            pos = next((p for p in positions if p.code == code), None)
            name = pos.name if pos else ''
            backlog.add_insufficient_history(code, name, 250, len(stock_df))

    # 7. 查找前一天报告
    prev_report_path = _find_prev_report(config.output_dir, scan_date)
    if prev_report_path:
        logger.info(f"找到前一天报告: {prev_report_path}")

    # 8. 生成报告
    logger.info("生成扫描报告")
    report_gen = ReportGenerator(config.output_dir)
    report_path, analysis_results = report_gen.generate(
        latest_df, positions, scan_date,
        prev_report_path=prev_report_path,
        index_status=index_status,
        full_df=df  # 传递完整历史数据用于图表生成
    )

    # 9. 保存 Daily Summary
    logger.info("保存 Daily Summary")
    _save_daily_summary(config.output_dir, scan_date, analysis_results)

    # 10. 保存 backlog
    if backlog.has_items():
        backlog.save(scan_date)

    logger.info("=" * 60)
    logger.info(f"扫描完成！报告: {report_path}")
    logger.info("=" * 60)

    return report_path


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='持仓技术面扫描')
    parser.add_argument('--date', type=str, help='扫描日期 (YYYY-MM-DD)，默认今天')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'], help='数据库环境')
    parser.add_argument('--portfolio', type=str, help='持仓文件路径')
    parser.add_argument('--output', type=str, help='输出目录')
    parser.add_argument('--stock', type=str, help='single stock scan, e.g. 688386')

    args = parser.parse_args()

    # Single stock mode: delegate to SingleStockScanner
    if args.stock:
        from .single_scanner import SingleStockScanner
        scanner = SingleStockScanner(env=args.env)
        report = scanner.scan(args.stock)
        print(report)
        return

    config = ScanConfig()
    if args.env:
        config.db_env = args.env
    if args.portfolio:
        config.portfolio_file = args.portfolio
    if args.output:
        config.output_dir = args.output

    scan_date = None
    if args.date:
        scan_date = datetime.strptime(args.date, '%Y-%m-%d')

    try:
        report_path = run_daily_scan(config, scan_date)
        if report_path:
            print(f"\n✅ 扫描完成！报告: {report_path}")
        else:
            print("\n❌ 扫描失败，请查看日志")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 扫描出错: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
