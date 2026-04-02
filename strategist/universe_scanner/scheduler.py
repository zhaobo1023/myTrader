# -*- coding: utf-8 -*-
"""
定时调度器

每日 18:00 自动执行全量自选股分层扫描
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import schedule
except ImportError:
    print("请安装 schedule: pip install schedule")
    sys.exit(1)

from strategist.universe_scanner.config import DEFAULT_CONFIG
from strategist.universe_scanner.run_scan import run_universe_scan

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def job():
    """定时任务：执行全量扫描"""
    logger.info("定时任务触发：开始全量自选股扫描")
    try:
        report_path = run_universe_scan()
        if report_path:
            logger.info(f"扫描完成: {report_path}")
        else:
            logger.warning("扫描未生成报告")
    except Exception as e:
        logger.error(f"扫描失败: {e}")


def run_scheduler():
    """启动定时调度器"""
    schedule_time = DEFAULT_CONFIG.schedule_time

    logger.info("=" * 60)
    logger.info("全量自选股扫描定时调度器启动")
    logger.info(f"计划执行时间: 每日 {schedule_time}")
    logger.info("=" * 60)

    schedule.every().day.at(schedule_time).do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='全量自选股扫描定时调度器')
    parser.add_argument('--run-now', action='store_true', help='立即执行一次扫描')
    parser.add_argument('--time', type=str, default=DEFAULT_CONFIG.schedule_time,
                        help='定时执行时间 (HH:MM)')

    args = parser.parse_args()

    if args.run_now:
        logger.info("立即执行扫描...")
        job()
    else:
        DEFAULT_CONFIG.schedule_time = args.time
        run_scheduler()


if __name__ == '__main__':
    main()
