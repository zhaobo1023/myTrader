#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填历史策略信号的5日出现次数统计
从指定日期开始，为每条历史记录添加 recent_occurrences 字段
"""
import os
import sys
import json
import logging
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pymysql

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# 直接数据库连接配置（绕过 config.db 的 host.docker.internal）
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Hao1023@zb',
    'database': 'trade',
    'charset': 'utf8mb4',
}


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def execute_query(sql, params=None, env='online'):
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
    finally:
        conn.close()


def execute_update(sql, params=None, env='online'):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            conn.commit()
            return cursor.rowcount
    finally:
        conn.close()


def get_stock_codes_from_signals(signals_json: str) -> list:
    """从 signals_json 中提取股票代码列表"""
    try:
        signals = json.loads(signals_json) if signals_json else []
        return [s.get('stock_code') for s in signals if s.get('stock_code')]
    except json.JSONDecodeError:
        return []


def add_occurrence_to_signal(signals_json: str, occurrence_counts: dict) -> str:
    """为每个信号添加 recent_occurrences 字段"""
    try:
        signals = json.loads(signals_json) if signals_json else []
        for sig in signals:
            stock_code = sig.get('stock_code', '')
            sig['recent_occurrences'] = occurrence_counts.get(stock_code, 0)
        return json.dumps(signals, ensure_ascii=False)
    except json.JSONDecodeError:
        return signals_json


def get_historical_occurrence_counts(target_run_id: int, target_run_date: str, stock_codes: list, days: int = 5, env: str = 'online') -> dict:
    """
    统计指定日期之前5日内，各股票的出现次数（不包含当前记录）

    Args:
        target_run_id: 当前记录的ID（用于排除）
        target_run_date: 当前记录的运行日期
        stock_codes: 股票代码列表
        days: 统计天数

    Returns:
        dict {stock_code: count}
    """
    if not stock_codes:
        return {}

    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT stock_code, COUNT(*) as count
        FROM trade_preset_strategy_run
        CROSS JOIN JSON_TABLE(
            signals_json,
            '$[*]' COLUMNS(
                stock_code VARCHAR(20) PATH '$.stock_code'
            )
        ) as sig
        WHERE id = trade_preset_strategy_run.id
          AND strategy_key = 'momentum_reversal'
          AND status = 'done'
          AND run_date < %s
          AND run_date >= DATE_SUB(%s, INTERVAL %s DAY)
          AND id != %s
          AND sig.stock_code IN ({placeholders})
        GROUP BY sig.stock_code
    """

    try:
        rows = execute_query(
            sql,
            (target_run_date, target_run_date, days, target_run_id) + tuple(stock_codes),
            env=env,
        )
        return {row['stock_code']: row['count'] for row in rows}
    except Exception as e:
        logger.warning(f'[BACKFILL] Failed to get occurrence counts: {e}')
        return {}


def backfill_occurrence_counts(start_date: str = '2026-04-13', env: str = 'online', dry_run: bool = False):
    """
    回填历史数据的5日出现次数

    Args:
        start_date: 开始日期
        env: 数据库环境
        dry_run: 是否为演练模式
    """
    logger.info(f'[BACKFILL] Starting backfill from {start_date} (dry_run={dry_run})')

    # 获取需要回填的记录
    rows = execute_query(
        """
        SELECT id, run_date, signals_json, signal_count
        FROM trade_preset_strategy_run
        WHERE strategy_key = 'momentum_reversal'
          AND status = 'done'
          AND run_date >= %s
          AND signals_json IS NOT NULL
          AND signals_json != ''
        ORDER BY run_date ASC
        """,
        (start_date,),
        env=env,
    )

    logger.info(f'[BACKFILL] Found {len(rows)} records to process')

    updated_count = 0
    for row in rows:
        run_id = row['id']
        run_date = str(row['run_date'])
        signals_json = row['signals_json']

        # 提取股票代码
        stock_codes = get_stock_codes_from_signals(signals_json)
        if not stock_codes:
            logger.warning(f'[BACKFILL] No stock codes found in run_id={run_id}')
            continue

        # 获取历史出现次数
        occurrence_counts = get_historical_occurrence_counts(run_id, run_date, stock_codes, days=5, env=env)

        # 添加 recent_occurrences 字段
        new_signals_json = add_occurrence_to_signal(signals_json, occurrence_counts)

        # 更新数据库
        if dry_run:
            logger.info(f'[DRY-RUN] run_id={run_id} date={run_date} stocks={len(stock_codes)}')
            # 显示部分统计
            sample = list(occurrence_counts.items())[:3]
            for code, count in sample:
                logger.info(f'  {code}: {count} occurrences')
        else:
            execute_update(
                "UPDATE trade_preset_strategy_run SET signals_json = %s WHERE id = %s",
                (new_signals_json, run_id),
                env=env,
            )
            updated_count += 1
            logger.info(f'[BACKFILL] Updated run_id={run_id} date={run_date} ({updated_count}/{len(rows)})')

    logger.info(f'[BACKFILL] Complete! Updated {updated_count} records')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Backfill occurrence counts for historical strategy runs')
    parser.add_argument('--start-date', default='2026-04-13', help='Start date (default: 2026-04-13)')
    parser.add_argument('--env', default='online', help='Database environment (default: online)')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    args = parser.parse_args()

    backfill_occurrence_counts(start_date=args.start_date, env=args.env, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
