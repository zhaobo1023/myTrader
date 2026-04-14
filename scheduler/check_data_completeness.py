# -*- coding: utf-8 -*-
"""
数据完备性检查 - 每日例行任务

检查各数据表的数据状态，记录到 trade_data_health 表。
"""
import logging
from datetime import datetime
from typing import Dict, List, Tuple

import pymysql

logger = logging.getLogger(__name__)


# 定义需要检查的表配置
TABLE_CHECKS = [
    # 核心行情数据
    ("trade_stock_daily", "daily", "日线行情", 5000, 1),  # 预期股票数, 最大滞后天数
    ("trade_stock_daily_basic", "daily", "估值数据", 5000, 3),

    # 技术指标
    ("trade_stock_rps", "indicator", "RPS相对强度", 5000, 5),
    ("trade_stock_basic_factor", "indicator", "基础因子", 5000, 5),
    ("trade_stock_financial", "financial", "财务数据", 5000, 7),

    # ETF/行业
    ("trade_etf_daily", "daily", "ETF日线", 500, 1),
    ("trade_log_bias_daily", "indicator", "对数乖离率", 30, 3),

    # 策略相关
    ("trade_preset_strategy_run", "strategy", "预设策略运行", None, None),
    ("trade_tech_report", "strategy", "技术面报告", None, None),

    # 情感/舆情
    ("trade_fear_index", "sentiment", "恐慌指数", None, 3),
    ("trade_news_sentiment", "sentiment", "新闻情感", None, 3),
]


def get_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host='localhost',
        user='root',
        password='Hao1023@zb',
        database='trade',
        charset='utf8mb4'
    )


def check_table(conn, table_name: str) -> Tuple[int, int, str]:
    """
    检查单个表的状态

    Returns:
        (记录数, 股票数, 最新日期)
    """
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    try:
        # 获取记录数
        cursor.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
        cnt = cursor.fetchone()['cnt']

        # 尝试获取最新日期
        max_date = None
        for date_col in ['trade_date', 'report_date', 'run_date', 'created_at', 'timestamp']:
            try:
                cursor.execute(f"SELECT MAX({date_col}) as max_date FROM {table_name}")
                result = cursor.fetchone()['max_date']
                if result:
                    max_date = str(result)
                    break
            except:
                continue

        # 尝试获取股票数
        stocks = None
        try:
            cursor.execute(f"SELECT COUNT(DISTINCT stock_code) as stocks FROM {table_name}")
            stocks = cursor.fetchone()['stocks']
        except:
            pass

        return cnt, stocks or 0, max_date or ''
    except Exception as e:
        logger.warning(f"[CHECK] Table {table_name} check failed: {e}")
        return 0, 0, ''


def calculate_status(cnt: int, max_date: str, expected_stocks: int, max_lag_days: int) -> str:
    """
    计算数据状态

    Returns:
        'ok', 'warning', 'critical', 'empty'
    """
    if cnt == 0:
        return 'empty'

    if max_date is None or max_date == '':
        return 'warning'

    # 检查数据滞后
    try:
        if max_date:
            from datetime import datetime
            check_date = datetime.strptime(max_date, '%Y-%m-%d').date()

            # 获取最新交易日
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(trade_date) as max_date FROM trade_stock_daily")
            latest_trade = cursor.fetchone()[0]
            conn.close()

            if latest_trade:
                latest = datetime.strptime(str(latest_trade), '%Y-%m-%d').date()
                lag_days = (latest - check_date).days

                if max_lag_days and lag_days > max_lag_days:
                    return 'critical'
                elif lag_days > 1:
                    return 'warning'
    except:
        pass

    # 检查股票数量
    if expected_stocks and cnt < expected_stocks * 0.8:  # 低于预期80%
        return 'warning'

    return 'ok'


def save_check_result(conn, check_time: str, results: List[Dict]):
    """保存检查结果到数据库"""
    cursor = conn.cursor()

    # 先创建表（如果不存在）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_data_health (
            id INT AUTO_INCREMENT PRIMARY KEY,
            check_time DATETIME NOT NULL,
            table_name VARCHAR(100) NOT NULL,
            table_category VARCHAR(50),
            record_count BIGINT DEFAULT 0,
            stock_count INT DEFAULT 0,
            latest_date DATE,
            status VARCHAR(20),
            lag_days INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_check_time (check_time),
            INDEX idx_table_name (table_name),
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # 获取最新交易日用于计算滞后天数
    cursor.execute("SELECT MAX(trade_date) as max_date FROM trade_stock_daily")
    latest_trade = cursor.fetchone()[0]

    # 插入或更新检查结果
    for r in results:
        lag_days = None
        if r['max_date'] and latest_trade:
            try:
                from datetime import datetime
                check_date = datetime.strptime(str(r['max_date']), '%Y-%m-%d').date()
                latest = datetime.strptime(str(latest_trade), '%Y-%m-%d').date()
                lag_days = (latest - check_date).days
            except:
                pass

        cursor.execute("""
            INSERT INTO trade_data_health
                (check_time, table_name, table_category, record_count, stock_count, latest_date, status, lag_days)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            check_time, r['table'], r['category'], r['count'],
            r['stocks'], r['max_date'] or None, r['status'], lag_days
        ))

    conn.commit()
    logger.info(f"[CHECK] Saved {len(results)} table health records")


def run_check(env: str = 'online') -> Dict:
    """
    执行数据完备性检查

    Returns:
        检查结果摘要
    """
    logger.info("[CHECK] Starting data completeness check...")

    conn = get_connection()
    check_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    results = []
    summary = {'ok': 0, 'warning': 0, 'critical': 0, 'empty': 0, 'error': 0}

    for table_name, category, desc, expected_stocks, max_lag in TABLE_CHECKS:
        try:
            cnt, stocks, max_date = check_table(conn, table_name)
            status = calculate_status(cnt, max_date, expected_stocks, max_lag)

            results.append({
                'table': table_name,
                'category': category,
                'desc': desc,
                'count': cnt,
                'stocks': stocks,
                'max_date': max_date,
                'status': status,
            })

            summary[status] = summary.get(status, 0) + 1

        except Exception as e:
            logger.error(f"[CHECK] Failed to check {table_name}: {e}")
            summary['error'] = summary.get('error', 0) + 1

    # 保存结果
    save_check_result(conn, check_time, results)

    conn.close()

    # 打印摘要
    logger.info(f"[CHECK] Summary: OK={summary['ok']}, Warning={summary['warning']}, Critical={summary['critical']}, Empty={summary['empty']}, Error={summary['error']}")

    return {
        'check_time': check_time,
        'summary': summary,
        'details': results,
    }


def get_latest_health() -> List[Dict]:
    """获取最新的健康检查结果"""
    conn = get_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("""
        SELECT * FROM trade_data_health
        WHERE check_time = (SELECT MAX(check_time) FROM trade_data_health)
        ORDER BY table_category, table_name
    """)

    results = cursor.fetchall()
    conn.close()

    return results


def get_health_summary() -> Dict:
    """获取健康状态摘要"""
    conn = get_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("""
        SELECT status, COUNT(*) as cnt
        FROM trade_data_health
        WHERE check_time = (SELECT MAX(check_time) FROM trade_data_health)
        GROUP BY status
    """)

    summary = {row['status']: row['cnt'] for row in cursor.fetchall()}
    conn.close()

    return summary


# CLI 入口
if __name__ == '__main__':
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    result = run_check()

    # 打印结果表格
    print("\n" + "=" * 80)
    print("数据完备性检查报告")
    print("=" * 80)
    print(f"检查时间: {result['check_time']}")
    print()

    for r in result['details']:
        status_icon = {
            'ok': '✅',
            'warning': '⚠️',
            'critical': '🔴',
            'empty': '❌',
        }.get(r['status'], '❓')

        print(f"{status_icon} {r['table']:35} {r['max_date']:12} {r['count']:>10,} 条  status={r['status']}")

    print()
    print(f"摘要: OK={result['summary']['ok']}, Warning={result['summary']['warning']}, Critical={result['summary']['critical']}, Empty={result['summary']['empty']}")
    print("=" * 80)
