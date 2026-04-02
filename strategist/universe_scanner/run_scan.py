# -*- coding: utf-8 -*-
"""
全量自选股分层扫描主入口

优化策略（两阶段查询）:
  阶段1: 单次 SQL 取最新一天数据 + RPS → 海选过滤（秒级）
  阶段2: 只对候选股取 60 天数据 → 计算技术指标 → 评分
"""
import sys
import os
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query
from strategist.universe_scanner.config import UniverseScanConfig, DEFAULT_CONFIG
from strategist.universe_scanner.universe_parser import parse_universe_csv, StockInfo
from strategist.universe_scanner.scoring_engine import ScoringEngine
from strategist.universe_scanner.report_generator import UniverseReportGenerator
from strategist.tech_scan.indicator_calculator import IndicatorCalculator

logger = logging.getLogger('universe_scan')


def setup_logging(config: UniverseScanConfig, scan_date: datetime) -> logging.Logger:
    """配置日志"""
    config.ensure_dirs()
    log_file = Path(config.log_dir) / f"universe_{scan_date.strftime('%Y%m%d')}.log"
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


def fetch_latest_snapshot(stock_codes: list, env: str) -> pd.DataFrame:
    """
    阶段1: 单次 SQL 取最新一天的行情 + RPS

    Returns:
        DataFrame with columns: stock_code, close, volume, amount, turnover_rate,
                                  rps_120, rps_250, rps_slope, stock_name, industry
    """
    if not stock_codes:
        return pd.DataFrame()

    placeholders = ','.join(['%s'] * len(stock_codes))
    latest_date_sub = "(SELECT MAX(trade_date) FROM trade_stock_daily)"

    # 主查询: 最新一天行情
    sql = f"""
        SELECT d.stock_code, d.trade_date,
               d.close_price as close, d.volume, d.amount, d.turnover_rate
        FROM trade_stock_daily d
        WHERE d.stock_code IN ({placeholders})
          AND d.trade_date = {latest_date_sub}
        ORDER BY d.stock_code
    """
    rows = execute_query(sql, tuple(stock_codes), env=env)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    for col in ['close', 'volume', 'amount', 'turnover_rate']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    logger.info(f"阶段1: 获取最新一天数据 {len(df)} 只")

    # 合并 RPS (最新一天)
    rps_sql = f"""
        SELECT stock_code, rps_120, rps_250, rps_slope
        FROM trade_stock_rps
        WHERE stock_code IN ({placeholders})
          AND trade_date = {latest_date_sub}
    """
    try:
        rps_rows = execute_query(rps_sql, tuple(stock_codes), env=env)
        if rps_rows:
            rps_df = pd.DataFrame(rps_rows)
            for col in ['rps_120', 'rps_250', 'rps_slope']:
                if col in rps_df.columns:
                    rps_df[col] = pd.to_numeric(rps_df[col], errors='coerce')
            df = df.merge(rps_df, on='stock_code', how='left')
            logger.info(f"阶段1: 合并 RPS 数据 {len(rps_rows)} 条")
    except Exception as e:
        logger.warning(f"RPS 查询失败: {e}")

    return df


def fetch_history_data(stock_codes: list, env: str, lookback_days: int = 80) -> pd.DataFrame:
    """
    阶段2: 只取候选股的 60 天历史数据（用于计算技术指标）

    lookback_days 使用自然日，80 天约 60 个交易日
    """
    if not stock_codes:
        return pd.DataFrame()

    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    placeholders = ','.join(['%s'] * len(stock_codes))

    sql = f"""
        SELECT stock_code, trade_date,
               open_price as `open`, high_price as high,
               low_price as low, close_price as close,
               volume, amount, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code IN ({placeholders})
          AND trade_date >= %s
        ORDER BY stock_code, trade_date
    """
    params = tuple(stock_codes) + (start_date,)
    rows = execute_query(sql, params, env=env)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover_rate']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    logger.info(f"阶段2: 获取 {len(stock_codes)} 只历史数据 {len(df)} 条")
    return df


def fetch_industry_map(stock_codes: list, env: str) -> dict:
    """获取行业映射"""
    if not stock_codes:
        return {}
    placeholders = ','.join(['%s'] * len(stock_codes))
    for table, code_col, name_col in [
        ('trade_stock_industry', 'stock_code', 'stock_name'),
        ('stock_basic', 'stock_code', 'name'),
    ]:
        try:
            sql = f"""
                SELECT {code_col}, {name_col} as stock_name,
                       industry, sector
                FROM {table}
                WHERE {code_col} IN ({placeholders})
            """
            rows = execute_query(sql, tuple(stock_codes), env=env)
            if rows:
                return {
                    r[code_col]: {
                        'name': r.get('stock_name', ''),
                        'industry': r.get('industry', '') or r.get('sector', ''),
                    }
                    for r in rows
                }
        except Exception:
            continue
    return {}


def run_universe_scan(config=None, scan_date=None) -> str:
    """执行全量自选股分层扫描（两阶段优化版）"""
    if config is None:
        config = DEFAULT_CONFIG
    if scan_date is None:
        scan_date = datetime.now()

    log = setup_logging(config, scan_date)
    log.info("=" * 60)
    log.info(f"开始全量自选股扫描 - {scan_date.strftime('%Y-%m-%d')}")
    log.info("=" * 60)

    # ==================================================================
    # 1. 解析总池子
    # ==================================================================
    log.info(f"解析总池子: {config.universe_csv}")
    try:
        a_shares, hk_other = parse_universe_csv(config.universe_csv)
    except Exception as e:
        log.error(f"解析总池子失败: {e}")
        raise

    if not a_shares:
        log.error("未解析到任何 A股/ETF")
        return None

    stock_codes = [s.code_fmt for s in a_shares]
    code_to_info = {s.code_fmt: s for s in a_shares}
    log.info(f"A股+ETF 共 {len(stock_codes)} 只")

    # ==================================================================
    # 2. 获取行业信息
    # ==================================================================
    log.info("获取行业信息")
    industry_map = fetch_industry_map(stock_codes, env=config.db_env)
    log.info(f"获取到 {len(industry_map)} 只行业信息")

    for code_fmt, info in code_to_info.items():
        if code_fmt in industry_map:
            db_ind = industry_map[code_fmt].get('industry', '')
            if db_ind and (not info.industry or info.industry == '--'):
                info.industry = db_ind
            db_name = industry_map[code_fmt].get('name', '')
            if db_name and not info.name:
                info.name = db_name

    # ==================================================================
    # 阶段1: 快照数据 + 海选过滤
    # ==================================================================
    t0 = datetime.now()
    log.info("阶段1: 获取最新一天快照 + RPS...")
    snapshot_df = fetch_latest_snapshot(stock_codes, config.db_env)

    if snapshot_df.empty:
        log.error("获取快照数据失败")
        return None

    latest_date = snapshot_df['trade_date'].max()
    log.info(f"最新交易日: {latest_date.strftime('%Y-%m-%d')}, {len(snapshot_df)} 只")

    # 海选预过滤: 剔除明显不合格的（用 amount 当天值做粗筛）
    # 60日均额无法在快照中计算，暂时放宽此条件
    # 但 RPS 和 MA250 需要历史数据，留到阶段2

    # 暂时用 RPS 做粗筛（如果有 RPS 数据）
    candidate_codes = snapshot_df['stock_code'].tolist()

    if 'rps_120' in snapshot_df.columns or 'rps_250' in snapshot_df.columns:
        rps120 = snapshot_df.get('rps_120')
        rps250 = snapshot_df.get('rps_250')
        has_rps_mask = pd.Series(True, index=snapshot_df.index)
        if rps120 is not None:
            has_rps_mask = has_rps_mask | (rps120 > config.rps_min)
        if rps250 is not None:
            has_rps_mask = has_rps_mask | (rps250 > config.rps_min)
        # 保留: 有 RPS 数据且满足条件，或无 RPS 数据的
        no_rps = rps120.isna() & rps250.isna()
        pass_mask = has_rps_mask | no_rps
        filtered_df = snapshot_df[~pass_mask]
        candidate_codes = snapshot_df[pass_mask]['stock_code'].tolist()
        log.info(f"阶段1 RPS 预筛: {len(snapshot_df)} -> {len(candidate_codes)} "
                 f"(剔除 {len(filtered_df)} 只 RPS 过低)")

    # ==================================================================
    # 阶段2: 候选股历史数据 + 技术指标
    # ==================================================================
    t1 = datetime.now()
    log.info(f"阶段2: 获取 {len(candidate_codes)} 只候选股历史数据...")

    # 分批拉取候选股历史（每批 200 只）
    BATCH_SIZE = 200
    all_hist = []
    total_batches = (len(candidate_codes) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(candidate_codes), BATCH_SIZE):
        batch = candidate_codes[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        log.info(f"  历史批次 {batch_num}/{total_batches}: {len(batch)} 只")
        try:
            batch_df = fetch_history_data(batch, config.db_env, lookback_days=80)
            if not batch_df.empty:
                all_hist.append(batch_df)
        except Exception as e:
            log.error(f"  批次 {batch_num} 失败: {e}")

    if all_hist:
        hist_df = pd.concat(all_hist, ignore_index=True)
    else:
        hist_df = pd.DataFrame()

    # ==================================================================
    # 计算技术指标
    # ==================================================================
    if not hist_df.empty:
        log.info(f"计算技术指标 ({len(hist_df)} 条记录)...")
        calculator = IndicatorCalculator(
            ma_windows=[5, 20, 60, 250],
            rsi_period=14,
        )
        hist_df = calculator.calculate_all(hist_df)

        # 计算日均成交额 (60日)
        if 'amount' in hist_df.columns:
            hist_df['avg_amount_60d'] = float('nan')
            for code, group in hist_df.groupby('stock_code'):
                if 'amount' in group.columns:
                    amt = group['amount'].astype(float)
                    hist_df.loc[group.index, 'avg_amount_60d'] = amt.rolling(window=60, min_periods=20).mean().values
    else:
        log.warning("无历史数据，跳过技术指标计算")

    # ==================================================================
    # 取最新一天 + 合并所有数据
    # ==================================================================
    if not hist_df.empty:
        latest_hist = hist_df[hist_df['trade_date'] == hist_df['trade_date'].max()].copy()
    else:
        latest_hist = pd.DataFrame()

    # 合并行业和名称
    for df_target in [latest_hist, snapshot_df]:
        df_target['industry'] = df_target['stock_code'].map(
            lambda c: code_to_info.get(c, StockInfo('', '', '', '', '')).industry
        )
        df_target['stock_name'] = df_target['stock_code'].map(
            lambda c: code_to_info.get(c, StockInfo('', '', '', '', '')).name
        )

    # 如果有历史指标数据，合并到快照
    if not latest_hist.empty:
        # 从历史数据取最新一天的指标列
        indicator_cols = ['ma5', 'ma20', 'ma60', 'ma250', 'macd_dif', 'macd_dea',
                          'macd_hist', 'rsi', 'volume_ratio', 'vol_ma5', 'vol_ma20',
                          'prev_macd_dif', 'prev_macd_dea', 'prev_ma5', 'prev_ma20',
                          'avg_amount_60d', 'pct_change', 'atr_14', 'high_20', 'low_20',
                          'ma20_bias', 'ma60_bias']
        existing_cols = [c for c in indicator_cols if c in latest_hist.columns]
        if existing_cols:
            merge_df = latest_hist[['stock_code'] + existing_cols].copy()
            # 合并到 snapshot（用历史指标覆盖）
            drop_cols = [c for c in existing_cols if c in snapshot_df.columns]
            snapshot_df = snapshot_df.drop(columns=drop_cols, errors='ignore')
            snapshot_df = snapshot_df.merge(merge_df, on='stock_code', how='left')

        analysis_df = snapshot_df
    else:
        analysis_df = snapshot_df

    t2 = datetime.now()
    log.info(f"数据处理完成: 阶段1 {(t1-t0).total_seconds():.1f}s + "
             f"阶段2 {(t2-t1).total_seconds():.1f}s = "
             f"总计 {(t2-t0).total_seconds():.1f}s")

    # ==================================================================
    # 三层分层过滤 + 评分
    # ==================================================================
    log.info(f"执行分层过滤 + 评分 ({len(analysis_df)} 只)")
    engine = ScoringEngine(config)

    # RPS 可用性
    has_rps = 'rps_120' in analysis_df.columns or 'rps_250' in analysis_df.columns
    if not has_rps:
        log.warning("RPS 数据缺失，将跳过 RPS 过滤门槛")
        original_rps_min = config.rps_min
        config.rps_min = 0

    results = engine.run(analysis_df)

    if not has_rps:
        config.rps_min = original_rps_min

    # ==================================================================
    # 生成报告
    # ==================================================================
    log.info("生成报告")
    report_gen = UniverseReportGenerator(config)
    report_path = report_gen.generate(results, hk_other, scan_date)
    log.info(f"报告: {report_path}")

    report_gen.save_daily_csv(results, scan_date)

    # ==================================================================
    # 汇总
    # ==================================================================
    hp = results['high_priority']
    wl = results['watchlist']
    uv = results['universe']
    fo = results['filtered_out']

    log.info("=" * 60)
    log.info(f"扫描完成! 耗时 {(t2-t0).total_seconds():.1f}s")
    log.info(f"  海选池: {len(uv)} | 关注池: {len(wl)} | 核心池: {len(hp)} | 剔除: {len(fo)}")
    if hp:
        top5 = [(s.code, s.name, s.total_score) for s in hp[:5]]
        log.info(f"  Top 5: {top5}")
    log.info(f"  报告: {report_path}")
    log.info("=" * 60)

    return report_path


def main():
    parser = argparse.ArgumentParser(description='全量自选股分层扫描')
    parser.add_argument('--date', type=str, help='扫描日期 (YYYY-MM-DD)')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'])
    parser.add_argument('--csv', type=str, help='总池子 CSV 文件路径')
    parser.add_argument('--output', type=str, help='输出目录')

    args = parser.parse_args()
    config = UniverseScanConfig()
    if args.env:
        config.db_env = args.env
    if args.csv:
        config.universe_csv = args.csv
    if args.output:
        config.output_dir = args.output

    scan_date = None
    if args.date:
        scan_date = datetime.strptime(args.date, '%Y-%m-%d')

    try:
        report_path = run_universe_scan(config, scan_date)
        if report_path:
            print(f"\n扫描完成! 报告: {report_path}")
        else:
            print("\n扫描失败")
            sys.exit(1)
    except Exception as e:
        print(f"\n扫描出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
