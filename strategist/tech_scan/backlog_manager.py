# -*- coding: utf-8 -*-
"""
Backlog 管理器

记录数据缺失、计算失败等异常情况
"""
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BacklogManager:
    """Backlog 管理器"""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.backlog_file = self.output_dir / "backlog.md"
        self.items: List[Dict[str, Any]] = []
    
    def add_item(
        self,
        stock_code: str,
        stock_name: str,
        issue_type: str,
        description: str
    ):
        """
        添加 backlog 项
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            issue_type: 问题类型（如 'data_missing', 'calc_failed', 'rps_missing'）
            description: 问题描述
        """
        self.items.append({
            'stock_code': stock_code,
            'stock_name': stock_name,
            'issue_type': issue_type,
            'description': description,
            'timestamp': datetime.now()
        })
        logger.warning(f"Backlog: {stock_code} {stock_name} - {description}")
    
    def add_data_missing(self, stock_code: str, stock_name: str):
        """添加数据缺失记录"""
        self.add_item(
            stock_code=stock_code,
            stock_name=stock_name,
            issue_type='data_missing',
            description='无行情数据，请检查数据库或运行数据拉取任务'
        )
    
    def add_rps_missing(self, stock_code: str, stock_name: str):
        """添加 RPS 缺失记录"""
        self.add_item(
            stock_code=stock_code,
            stock_name=stock_name,
            issue_type='rps_missing',
            description='RPS数据缺失，需运行RPS计算任务'
        )
    
    def add_insufficient_history(self, stock_code: str, stock_name: str, required_days: int, actual_days: int):
        """添加历史数据不足记录"""
        self.add_item(
            stock_code=stock_code,
            stock_name=stock_name,
            issue_type='insufficient_history',
            description=f'历史数据不足: 需要{required_days}日, 实际{actual_days}日'
        )
    
    def add_calc_failed(self, stock_code: str, stock_name: str, error: str):
        """添加计算失败记录"""
        self.add_item(
            stock_code=stock_code,
            stock_name=stock_name,
            issue_type='calc_failed',
            description=f'指标计算失败: {error}'
        )
    
    def save(self, scan_date: datetime = None):
        """
        保存 backlog 到文件
        
        追加模式，保留历史记录
        """
        if not self.items:
            logger.info("无 backlog 项需要记录")
            return
        
        if scan_date is None:
            scan_date = datetime.now()
        
        # 读取现有内容
        existing_content = ""
        if self.backlog_file.exists():
            existing_content = self.backlog_file.read_text(encoding='utf-8')
        
        # 构建新内容
        lines = []
        
        # 如果是新文件，添加标题
        if not existing_content:
            lines.append("# 技术扫描 Backlog")
            lines.append("")
            lines.append("> 记录数据缺失、计算失败等需要处理的问题")
            lines.append("")
        
        # 添加日期标题
        date_str = scan_date.strftime('%Y-%m-%d')
        lines.append(f"## {date_str}")
        lines.append("")
        
        # 添加 backlog 项
        for item in self.items:
            checkbox = "[ ]"
            lines.append(f"- {checkbox} **{item['stock_code']} {item['stock_name']}**: {item['description']}")
        
        lines.append("")
        
        # 写入文件
        new_content = "\n".join(lines)
        if existing_content:
            # 追加到现有内容
            full_content = existing_content.rstrip() + "\n\n" + new_content
        else:
            full_content = new_content
        
        self.backlog_file.write_text(full_content, encoding='utf-8')
        logger.info(f"Backlog 已保存: {self.backlog_file} ({len(self.items)} 项)")
    
    def clear(self):
        """清空当前 backlog 项"""
        self.items = []
    
    def has_items(self) -> bool:
        """是否有 backlog 项"""
        return len(self.items) > 0
