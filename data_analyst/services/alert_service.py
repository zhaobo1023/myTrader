# -*- coding: utf-8 -*-
"""
报警服务

支持：
  1. 飞书 Webhook 推送
  2. 控制台打印（测试用）
"""
import os
import json
import requests
from typing import Optional, Dict, List
from datetime import datetime
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from dotenv import load_dotenv

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AlertService:
    """报警服务"""

    def __init__(self):
        self.webhook_url = os.getenv('FEISHU_WEBHOOK_URL')
        self.enabled = bool(self.webhook_url)

        if not self.enabled:
            logger.warning("飞书 Webhook 未配置，报警功能将输出到控制台")

    def send_text(self, text: str) -> bool:
        """发送文本消息"""
        if not self.enabled:
            logger.info(f"[控制台] {text}")
            return True

        payload = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            result = response.json()

            if result.get('StatusCode') == 0:
                logger.info("飞书消息发送成功")
                return True
            else:
                logger.error(f"飞书消息发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False

    def send_card(self, title: str, content: List[Dict],
                   color: str = "blue") -> bool:
        """发送卡片消息"""
        if not self.enabled:
            logger.info(f"[控制台] {title}")
            return True

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": color
                },
                "elements": content
            }
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            result = response.json()

            if result.get('StatusCode') == 0:
                logger.info("飞书卡片发送成功")
                return True
            else:
                logger.error(f"飞书卡片发送失败: {result}")
                return False
        except Exception as e:
            logger.error(f"飞书卡片发送异常: {e}")
            return False

    def send_data_alert(self, title: str, data: Dict, str,
                       issues: List[str] = None,
                       warnings: List[str] = None) -> bool:
        """发送数据报警"""
        # 构建内容
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**检查时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        ]

        # 添加数据概览
        if data:
            overview = "**数据概览**\n"
            for key, value in data.items():
                overview += f"- {key}: {value}\n"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": overview
                }
            })

        # 添加问题
        if issues:
            issues_text = "**问题**\n"
            for issue in issues:
                issues_text += f"- ❌ {issue}\n"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": issues_text
                }
            })

        # 添加警告
        if warnings:
            warnings_text = "**警告**\n"
            for warning in warnings:
                warnings_text += f"- ⚠️ {warning}\n"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": warnings_text
                }
            })

        # 添加备注
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "myTrader 数据监控系统"
                }
            ]
        })

        # 根据状态选择颜色
        color = "red" if issues else ("yellow" if warnings else "green")

        return self.send_card(f"[数据监控] {title}", elements, color=color)

    def send_success_alert(self, title: str, message: str) -> bool:
        """发送成功消息"""
        content = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        ]

        {
            "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{title}**\n{message}"
                }
            },

            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "myTrader 数据监控系统"
                    }
                ]
            }
        ]

        return self.send_card(title, content, color="green")


    def send_factor_calc_trigger(self, is_ok: bool, issues: List[str]) -> None:
        """发送因子计算触发通知"""
        if is_ok:
            return self.send_success_alert(
                "数据检查通过，                f"数据完整性检查通过，即将开始因子计算..."
            )
        else:
            return self.send_data_alert(
                "数据检查异常",
                {},
                issues=issues
            )


if __name__ == "__main__":
    # 测试
    service = AlertService()
    # 发送测试消息
    service.send_text("这是一条测试消息，来自 myTrader 数据监控系统")
    # 发送数据报警测试
    service.send_data_alert(
        "测试数据报警",
        {"测试": "数据"},
        issues=["测试问题1", "测试问题2"]
    )
    # 发送成功消息测试
    service.send_success_alert(
        "测试成功",
        "这是一条测试成功消息"
    )
