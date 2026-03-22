# -*- coding: utf-8 -*-
"""
定时任务调度服务

功能:
  1. 使用 APScheduler 实现定时任务
  2. 支持每日定时任务和间隔任务
  3. 集成数据检查和因子计算触发
"""
import sys
import os
import logging
from datetime import datetime
from typing import Callable, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SchedulerService:
    """定时任务调度服务"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self._alert_service = None
        self._on_factor_callback = None

    def _job_listener(self, event):
        """任务执行监听器"""
        if event.exception:
            logger.error(f"任务执行失败: {event.job_id}, 错误: {event.exception}")
            if self._alert_service:
                self._alert_service.send_text(
                    f"❌ 定时任务执行失败\n"
                    f"任务: {event.job_id}\n"
                    f"错误: {event.exception}"
                )
        else:
            logger.info(f"任务执行成功: {event.job_id}")

            # 任务执行成功后的回调
            if self._on_factor_callback:
                self._on_factor_callback(True, event.job_id)

            if self._alert_service:
                self._alert_service.send_success_alert(
                    f"✅ 任务执行成功",
                    f"任务: {event.job_id}"
                )

    def add_job(self, func: Callable, trigger, job_id: Optional[str] = None, **kwargs):
        """添加定时任务"""
        self.scheduler.add_job(func, trigger=trigger, id=job_id, **kwargs)
        logger.info(f"添加定时任务: {job_id or func.__name__}")

    def add_daily_job(self, func: Callable, hour: int = 18, minute: int = 0,
                         job_id: Optional[str] = None, **kwargs):
        """添加每日定时任务"""
        trigger = CronTrigger(hour=hour, minute=minute)
        self.add_job(func, trigger, job_id=job_id, **kwargs)

    def add_interval_job(self, func: Callable, seconds: Optional[int] = None,
                         minutes: Optional[int] = None, hours: Optional[int] = None,
                         job_id: Optional[str] = None, **kwargs):
        """添加间隔任务"""
        from apscheduler.triggers.interval import IntervalTrigger
        trigger = IntervalTrigger(seconds=seconds, minutes=minutes, hours=hours)
        self.add_job(func, trigger, job_id=job_id, **kwargs)
    def set_alert_service(self, alert_service):
        """设置报警服务"""
        self._alert_service = alert_service

    def set_factor_callback(self, callback: Callable):
        """设置因子计算完成回调"""
        self._on_factor_callback = callback

    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("定时任务调度器已启动")

    def shutdown(self, wait: bool = True):
        """关闭调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("定时任务调度器已关闭")
    def get_jobs(self):
        """获取所有任务"""
        return self.scheduler.get_jobs()
    def remove_job(self, job_id: str):
        """移除任务"""
        self.scheduler.remove_job(job_id)
        logger.info(f"移除任务: {job_id}")
    def pause_job(self, job_id: str):
        """暂停任务"""
        self.scheduler.pause_job(job_id)
        logger.info(f"暂停任务: {job_id}")
    def resume_job(self, job_id: str):
        """恢复任务"""
        self.scheduler.resume_job(job_id)
        logger.info(f"恢复任务: {job_id}")


# ============================================================
# 数据检查任务
# ============================================================

def check_data_and_trigger_factor():
    """检查数据完整性并在通过时触发因子计算"""
    from data_analyst.services.data_monitor import DataMonitor
    from data_analyst.services.alert_service import AlertService

    logger.info("=" * 60)
    logger.info("开始数据完整性检查...")
    logger.info("=" * 60)

    monitor = DataMonitor()
    result = monitor.check_daily_data()

    # 打印报告
    monitor.print_report()

    alert_service = AlertService()

    scheduler = SchedulerService()
    scheduler.set_alert_service(alert_service)

    # 设置因子计算回调
    def on_factor_complete(success: bool, job_id: str):
        if success:
            logger.info("因子计算完成，触发后续流程...")
            # TODO: 这里可以添加后续流程，如选股、回测等
        else:
            logger.error("因子计算失败")
            alert_service.send_data_alert(
                "因子计算失败",
                {},
                ["因子计算过程中发生错误，请检查日志"]
            )

    scheduler.set_factor_callback(on_factor_complete)

    if result['is_ok']:
        # 数据检查通过，触发因子计算
        logger.info("数据检查通过，开始因子计算...")
        alert_service.send_success_alert(
            "数据检查通过",
            "数据完整性检查通过，已触发因子计算任务"
        )

        # 触发因子计算
        trigger_factor_calculation()
    else:
        # 数据检查失败，发送报警
        logger.error("数据检查失败，发送报警...")
        alert_service.send_data_alert(
            "数据检查异常",
            result,
            result.get('issues', [])
        )


def trigger_factor_calculation():
    """触发因子计算"""
    logger.info("开始因子计算...")

    try:
        # TODO: 实现因子计算逻辑
        # 这里可以调用因子计算模块
        # from data_analyst.factors.factor_calculator import FactorCalculator
        # calculator = FactorCalculator()
        # calculator.calculate_all_factors()

        logger.info("因子计算完成")
        return True
    except Exception as e:
        logger.error(f"因子计算失败: {e}")
        return False


# ============================================================
# 初始化调度器
# ============================================================

def init_scheduler():
    """初始化定时任务"""
    # 创建服务实例
    alert_service = AlertService()
    scheduler = SchedulerService()
    scheduler.set_alert_service(alert_service)

    # 添加每日 18:00 数据检查任务
    scheduler.add_daily_job(
        func=check_data_and_trigger_factor,
        hour=18,
        minute=0,
        job_id='daily_data_check'
    )

    logger.info("定时任务初始化完成")
    return scheduler


# ============================================================
# 主函数
# ============================================================

def main():
    """测试定时任务调度器"""
    # 初始化调度器
    scheduler = init_scheduler()

    # 启动调度器
    scheduler.start()

    # 显示所有任务
    jobs = scheduler.get_jobs()
    print(f"\n当前共有 {len(jobs)} 个定时任务:")
    for job in jobs:
        print(f"  - {job.id}: 下次执行时间 {job.next_run_time}")

    # 保持运行
    try:
        print("\n调度器运行中，按 Ctrl+C 停止...")
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在关闭调度器...")
        scheduler.shutdown()
        print("调度器已关闭")


if __name__ == "__main__":
    main()
