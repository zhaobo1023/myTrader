# -*- coding: utf-8 -*-
"""
每日执行流程 (Daily Run)

整合所有模块的每日执行逻辑:
1. 拉取宏观数据 → 存表
2. 计算宏观因子 -> 追加因子库
3. 运行滚动IC监控 -> 更新factor_status
4. 如有因子状态变化 -> 触发飞书推送

运行:
    python daily_run.py
    python daily_run.py --date 2024-01-15
    python daily_run.py --full
"""
import sys
import os
import argparse
from datetime import date, timedelta
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.db import execute_query, get_connection
from config.settings import settings


class DailyRunner:
    """每日执行流程管理器"""

    def __init__(self, target_date: str = None, full_run: bool = False):
        """
        初始化

        Args:
            target_date: 目标日期 (YYYY-MM-DD)，默认昨天
            full_run: 是否全量重算
        """
        if target_date:
            self.target_date = target_date
        else:
            self.target_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

        self.full_run = full_run
        self.results = {
            'macro_fetch': {'status': 'pending', 'message': ''},
            'factor_calc': {'status': 'pending', 'message': ''},
            'factor_monitor': {'status': 'pending', 'message': ''},
            'alerts': []
        }

    def log(self, step: str, message: str):
        """打印日志"""
        print(f"[{step}] {message}")

    def step1_fetch_macro_data(self) -> Tuple[bool, str]:
        """
        步骤1: 拉取宏观数据

        Returns:
            (是否成功, 消息)
        """
        self.log("步骤1", f"拉取宏观数据 (日期: {self.target_date})...")

        try:
            from data_analyst.fetchers.macro_fetcher import fetch_all_indicators

            results = fetch_all_indicators()

            success_count = sum(1 for r in results.values() if r['success'])
            total_count = len(results)
            total_records = sum(r['count'] for r in results.values())

            message = f"成功: {success_count}/{total_count}, 总记录: {total_records}"
            self.log("步骤1", f"完成 - {message}")
            return True, message

        except Exception as e:
            error_msg = f"失败: {str(e)}"
            self.log("步骤1", error_msg)
            return False, error_msg

    def step2_calculate_factors(self) -> Tuple[bool, str]:
        """
        步骤2: 计算宏观因子

        Returns:
            (是否成功, 消息)
        """
        self.log("步骤2", "计算宏观因子...")

        try:
            from data_analyst.factors.macro_factor_calculator import calculate_all_factors, save_all_factors

            if self.full_run:
                # 全量重算: 从最早日期开始
                start_date = '2020-01-01'
            else:
                # 增量更新
                start_date = None

            all_factors = calculate_all_factors(start_date)

            if not all_factors:
                return False, "无因子数据"

            total_saved = save_all_factors(all_factors)
            message = f"保存 {total_saved} 条因子记录"
            self.log("步骤2", f"完成 - {message}")
            return True, message
        except Exception as e:
            error_msg = f"失败: {str(e)}"
            self.log("步骤2", error_msg)
            return False, error_msg

    def step3_run_factor_monitor(self) -> Tuple[bool, str, List]:
        """
        步骤3: 运行因子监控

        Returns:
            (是否成功, 消息, 状态变化列表)
        """
        self.log("步骤3", "运行因子监控...")

        try:
            from research.factor_monitor import run_monitor
            result = run_monitor(output_dir='output')
            status_changes = []

            # 检查 factor_alerts 表中的状态变化
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT factor_code, old_status, new_status
                    FROM factor_alerts
                    WHERE alert_date = %s
                    ORDER BY id DESC
                """, [self.target_date])
                rows = cursor.fetchall()
                for row in rows:
                    status_changes.append({
                        'factor_code': row['factor_code'],
                        'old_status': row['old_status'],
                        'new_status': row['new_status']
                    })
                cursor.close()
                conn.close()
            except:
                pass

            message = f"监控完成 - 有效: {result.get('valid_count', 0)}, 衰减: {result.get('decaying_count', 0)}, 失效: {result.get('invalid_count', 0)}"
            self.log("步骤3", f"完成 - {message}")
            return True, message, status_changes
        except Exception as e:
            error_msg = f"失败: {str(e)}"
            self.log("步骤3", error_msg)
            return False, error_msg, []

    def step4_send_alerts(self, status_changes: List) -> Tuple[bool, str]:
        """
        步骤4: 发送报警通知

        Args:
            status_changes: 状态变化列表

        Returns:
            (是否成功, 消息)
        """
        if not status_changes:
            self.log("步骤4", "无状态变化，跳过报警")
            return True, "无状态变化"

        self.log("步骤4", f"发送报警通知 ({len(status_changes)} 个变化)...")

        try:
            import requests
            webhook_url = getattr(settings, 'FEISHU_WEBHOOK_URL', '')
            if not webhook_url:
                self.log("步骤4", "未配置飞书 Webhook URL")
                return True, "已跳过（未配置)"

            for change in status_changes:
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {"tag": "plain_text", "content": "因子状态变化报警"},
                            "template": "red"
                        },
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": f"**因子**: {change['factor_code']}\n**状态变化**: {change['old_status']} -> {change['new_status']}\n**时间**: {self.target_date}"
                            }
                        ]
                    }
                }
                try:
                    resp = requests.post(webhook_url, json=payload, timeout=10)
                    resp.raise_for_status()
                    self.log("步骤4", "飞书报警发送成功")
                except Exception as e:
                    self.log("步骤4", f"飞书报警发送失败: {e}")
                    return False, str(e)

            self.log("步骤4", f"完成 - 已发送 {len(status_changes)} 个报警")
            return True, f"已发送 {len(status_changes)} 个报警"
        except Exception as e:
            self.log("步骤4", f"发送报警失败: {e}")
            return False, str(e)

    def run(self) -> Dict:
        """
        执行完整流程

        Returns:
            执行结果摘要
        """
        print("=" * 60)
        print("每日执行流程")
        print(f"目标日期: {self.target_date}")
        print(f"全量重算: {'是' if self.full_run else '否'}")
        print("=" * 60)

        success_count = 0
        fail_count = 0

        # 步骤1: 拉取宏观数据
        success, message = self.step1_fetch_macro_data()
        self.results['macro_fetch'] = {'status': 'success' if success else 'failed', 'message': message}
        if success:
            success_count += 1
        else:
            fail_count += 1

        # 步骤2: 计算因子
        success, message = self.step2_calculate_factors()
        self.results['factor_calc'] = {'status': 'success' if success else 'failed', 'message': message}
        if success:
            success_count += 1
        else:
            fail_count += 1

        # 步骤3: 运行监控
        success, message, status_changes = self.step3_run_factor_monitor()
        self.results['factor_monitor'] = {'status': 'success' if success else 'failed', 'message': message}
        self.results['alerts'] = status_changes
        if success:
            success_count += 1
        else:
            fail_count += 1

        # 步骤4: 发送报警
        if status_changes:
            success, message = self.step4_send_alerts(status_changes)
            if not success:
                fail_count += 1

        # 打印摘要
        print("\n" + "=" * 60)
        print("执行摘要")
        print("=" * 60)
        print(f"成功步骤: {success_count}")
        print(f"失败步骤: {fail_count}")
        print(f"因子状态变化: {len(status_changes)}")

        if self.results['alerts']:
            print("\n状态变化详情:")
            for alert in self.results['alerts']:
                print(f"  - {alert}")

        print("=" * 60)

        return self.results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='每日执行流程')
    parser.add_argument('--date', type=str, help='目标日期 (YYYY-MM-DD)，默认昨天')
    parser.add_argument('--full', action='store_true', help='触发全量重算')
    args = parser.parse_args()

    runner = DailyRunner(target_date=args.date, full_run=args.full)
    runner.run()
