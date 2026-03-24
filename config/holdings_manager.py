# -*- coding: utf-8 -*-
"""
持仓配置管理模块

用于管理持仓配置，支持JSON格式读写

使用方法:
    from config.holdings_manager import HoldingsManager

    manager = HoldingsManager()
    holdings = manager.get_holdings()

    # 更新持仓
    manager.update_holdings(new_holdings)
"""
import json
import os
from datetime import date
from typing import List, Dict, Optional


class HoldingsManager:
    """持仓配置管理器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'holdings.json'
            )
        self.config_path = config_path
        self._holdings = None

    def load_holdings(self) -> Dict:
        """加载持仓配置"""
        if not os.path.exists(self.config_path):
            return {
                "portfolio_name": "默认持仓组合",
                "update_date": date.today().strftime('%Y-%m-%d'),
                "holdings": [],
                "cash_weight": 1.0,
                "total_weight": 1.0
            }

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_holdings(self) -> List[Dict]:
        """获取持仓列表"""
        if self._holdings is None:
            self._holdings = self.load_holdings()
        return self._holdings.get('holdings', [])

    def get_stock_codes(self, format: str = 'default') -> List[str]:
        """
        获取股票代码列表

        Args:
            format: 代码格式
                - 'default': 原始格式 (300750.SZ)
                - 'simple': 简化格式 (300750)
                - 'wind': Wind格式 (300750.SZ)
                - 'qmt': QMT格式 (300750.SZ)

        Returns:
            股票代码列表
        """
        holdings = self.get_holdings()
        codes = [h['code'] for h in holdings]

        if format == 'simple':
            return [c.split('.')[0] for c in codes]

        return codes

    def get_weights(self) -> Dict[str, float]:
        """获取股票权重映射"""
        holdings = self.get_holdings()
        return {h['code']: h['weight'] for h in holdings}

    def get_update_date(self) -> str:
        """获取持仓更新日期"""
        if self._holdings is None:
            self._holdings = self.load_holdings()
        return self._holdings.get('update_date', '')

    def update_holdings(self, holdings: List[Dict], portfolio_name: str = None):
        """
        更新持仓配置

        Args:
            holdings: 持仓列表 [{'code': '300750.SZ', 'name': '宁德时代', 'weight': 0.1}, ...]
            portfolio_name: 组合名称
        """
        if portfolio_name is None:
            portfolio_name = self._holdings.get('portfolio_name', '持仓组合') if self._holdings else '持仓组合'

        # 计算总权重
        total_weight = sum(h['weight'] for h in holdings)
        cash_weight = max(0, 1.0 - total_weight)

        config = {
            "portfolio_name": portfolio_name,
            "update_date": date.today().strftime('%Y-%m-%d'),
            "holdings": holdings,
            "cash_weight": round(cash_weight, 4),
            "total_weight": 1.0
        }

        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

        self._holdings = config
        print(f"✅ 持仓配置已更新: {self.config_path}")

    def add_holding(self, code: str, name: str, weight: float):
        """添加单个持仓"""
        holdings = self.get_holdings()

        # 检查是否已存在
        for h in holdings:
            if h['code'] == code:
                h['weight'] = weight
                h['name'] = name
                self.update_holdings(holdings)
                return

        # 添加新持仓
        holdings.append({
            'code': code,
            'name': name,
            'weight': weight
        })
        self.update_holdings(holdings)

    def remove_holding(self, code: str):
        """移除持仓"""
        holdings = self.get_holdings()
        holdings = [h for h in holdings if h['code'] != code]
        self.update_holdings(holdings)

    def summary(self) -> str:
        """生成持仓摘要"""
        holdings = self.get_holdings()
        update_date = self.get_update_date()

        lines = [
            f"{'='*50}",
            f"持仓组合摘要 ({update_date})",
            f"{'='*50}",
            f"{'代码':<12} {'名称':<10} {'权重':>8}",
            f"{'-'*50}"
        ]

        for h in sorted(holdings, key=lambda x: -x['weight']):
            lines.append(f"{h['code']:<12} {h['name']:<10} {h['weight']*100:>7.2f}%")

        total = sum(h['weight'] for h in holdings)
        lines.append(f"{'-'*50}")
        lines.append(f"{'合计':<12} {'':<10} {total*100:>7.2f}%")
        lines.append(f"{'='*50}")

        return '\n'.join(lines)


# 便捷函数
def get_holdings() -> List[Dict]:
    """获取持仓列表"""
    return HoldingsManager().get_holdings()


def get_stock_codes(format: str = 'default') -> List[str]:
    """获取股票代码列表"""
    return HoldingsManager().get_stock_codes(format)


def get_weights() -> Dict[str, float]:
    """获取股票权重映射"""
    return HoldingsManager().get_weights()


if __name__ == "__main__":
    # 测试
    manager = HoldingsManager()
    print(manager.summary())
