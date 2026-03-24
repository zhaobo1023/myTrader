# -*- coding: utf-8 -*-
"""
持仓配置管理模块

用于管理持仓配置，支持JSON格式读写
包含完整的CSV字段

使用方法:
    from config.holdings_manager import HoldingsManager

    manager = HoldingsManager()
    holdings = manager.get_holdings()
    print(manager.summary())
"""

import csv
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
        self._holdings_full = None

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
            data = self.load_holdings()
            self._holdings = data.get('holdings', [])
        return self._holdings

    def get_holdings_full(self) -> List[Dict]:
        """获取完整持仓数据（包含所有CSV字段）"""
        if self._holdings_full is None:
            full_path = self.config_path.replace('holdings.json', 'holdings_full.json')
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._holdings_full = data.get('holdings', [])
            else:
                self._holdings_full = []
        return self._holdings_full

    def get_stock_codes(self, format: str = 'default') -> List[str]:
        """
        获取股票代码列表

        Args:
            format: 代码格式
                - 'default': 原始格式 (300750.SZ)
                - 'simple': 简化格式 (300750)

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
        return {h['code']: h.get('weight', 0) for h in holdings}

    def get_update_date(self) -> str:
        """获取持仓更新日期"""
        if self._holdings is None:
            data = self.load_holdings()
            return data.get('update_date', '')
        return self._holdings.get('update_date', '') if isinstance(self._holdings, dict) else ''

    def update_holdings(self, holdings: List[Dict], portfolio_name: str = None):
        """
        更新持仓配置

        Args:
            holdings: 持仓列表
            portfolio_name: 组合名称
        """
        data = self.load_holdings()
        if portfolio_name is None:
            portfolio_name = data.get('portfolio_name', '持仓组合')

        # 计算总权重
        total_weight = sum(h.get('weight', 0) for h in holdings)
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

        self._holdings = holdings
        print(f"✅ 持仓配置已更新: {self.config_path}")

    def update_holdings_from_csv(self, csv_path: str):
        """从CSV文件更新持仓"""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV文件不存在: {csv_path}")

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            headers = next(reader)

            holdings = []
            for row in reader:
                if len(row) < 3:
                    continue

                data = {}
                for i, val in enumerate(row):
                    if i < len(headers):
                        col_name = headers[i].strip()
                        data[col_name] = val.strip() if val else ''

                if not data.get('代码'):
                    continue

                code_raw = self._parse_code(data.get('代码', ''))
                code = code_raw + self._get_market_suffix(code_raw)
                name = data.get('名称', '').strip()

                holding = {
                    'code': code,
                    'name': name,
                    'price': self._parse_value(data.get('最新')),
                    'change_pct': self._parse_value(data.get('涨幅%')),
                    'change': self._parse_value(data.get('涨跌')),
                    'high': self._parse_value(data.get('最高')),
                    'low': self._parse_value(data.get('最低')),
                    'open': self._parse_value(data.get('开盘')),
                    'prev_close': self._parse_value(data.get('昨收')),
                    'volume': self._parse_value(data.get('总量')),
                    'amount': self._parse_value(data.get('金额')),
                    'turnover_rate': self._parse_value(data.get('换手%')),
                    'pe_ratio': self._parse_value(data.get('市盈率')),
                    'pb_ratio': self._parse_value(data.get('市净率')),
                    'industry': data.get('所属行业', '').strip(),
                    'total_market_cap': self._parse_value(data.get('总市值')),
                    'float_market_cap': self._parse_value(data.get('流通市值')),
                    'total_shares': self._parse_value(data.get('总股本')),
                    'float_shares': self._parse_value(data.get('流通股本')),
                    'change_3d': self._parse_value(data.get('3日涨幅%')),
                    'change_6d': self._parse_value(data.get('6日涨幅%')),
                    'change_mtd': self._parse_value(data.get('本月涨幅%')),
                    'change_ytd': self._parse_value(data.get('今年涨幅%')),
                    'change_1m': self._parse_value(data.get('近一月涨幅%')),
                    'change_1y': self._parse_value(data.get('近一年涨幅%')),
                    'amplitude': self._parse_value(data.get('振幅%')),
                    'volume_ratio': self._parse_value(data.get('量比')),
                    'vwap': self._parse_value(data.get('均价')),
                    'weight': 0  # 稍后计算等权
                }
                holdings.append(holding)

            # 计算等权
            if holdings:
                equal_weight = round(1.0 / len(holdings), 4)
                for h in holdings:
                    h['weight'] = equal_weight

            # 保存到JSON
            self.update_holdings(holdings)

            # 保存完整版本
            full_path = self.config_path.replace('holdings.json', 'holdings_full.json')
            full_config = {
                "portfolio_name": "主力持仓组合",
                "update_date": date.today().strftime('%Y-%m-%d'),
                "holdings_count": len(holdings),
                "holdings": holdings,
                "notes": "完整持仓数据，来源于hold.csv"
            }
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, ensure_ascii=False, indent=2)
            print(f"✅ 完整持仓数据已保存: {full_path}")

            return holdings

    def _parse_code(self, code_str: str) -> str:
        """解析股票代码"""
        code = code_str.strip()
        if code.startswith('='):
            code = code[1:].strip().strip('"').strip()
        return code

    def _get_market_suffix(self, code: str) -> str:
        """根据代码获取市场后缀"""
        if code.startswith('6'):
            return '.SH'
        elif code.startswith('0') or code.startswith('3') or code.startswith('1'):
            return '.SZ'
        else:
            return '.SZ'

    def _parse_value(self, val: str) -> float:
        """解析数值，处理单位"""
        if not val or not val.strip():
            return 0.0

        val = val.strip()
        if '%' in val:
            val = val.replace('%', '')

        multipliers = {'万': 10000, '亿': 100000000}
        multiplier = 1
        for unit, mult in multipliers.items():
            if unit in val:
                multiplier = mult
                val = val.replace(unit, '')
                break

        try:
            return float(val) * multiplier
        except:
            return 0.0

    def summary(self) -> str:
        """生成持仓摘要（基础版）"""
        holdings = self.get_holdings()
        data = self.load_holdings()
        update_date = data.get('update_date', '')

        lines = [
            f"{'='*50}",
            f"持仓组合摘要 ({update_date})",
            f"{'='*50}",
            f"{'代码':<12} {'名称':<10} {'权重':>8}",
            f"{'-'*50}"
        ]

        for h in sorted(holdings, key=lambda x: -x.get('weight', 0)):
            weight = h.get('weight', 0)
            lines.append(f"{h['code']:<12} {h['name']:<10} {weight*100:>7.2f}%")

        total = sum(h.get('weight', 0) for h in holdings)
        lines.append(f"{'-'*50}")
        lines.append(f"{'合计':<12} {'':<10} {total*100:>7.2f}%")
        lines.append(f"{'='*50}")

        return '\n'.join(lines)

    def summary_full(self) -> str:
        """生成持仓摘要（完整版）"""
        holdings = self.get_holdings_full()
        if not holdings:
            return self.summary()

        lines = [
            f"{'='*120}",
            f"持仓组合摘要 (完整版)",
            f"{'='*120}",
            f"{'代码':<12} {'名称':<10} {'最新价':>10} {'涨幅%':>8} {'换手%':>8} {'市盈率':>8} {'市净率':>8} {'行业':<12} {'总市值(亿)':>12}",
            f"{'-'*120}"
        ]

        for h in sorted(holdings, key=lambda x: -x.get('weight', 0)):
            market_cap = h.get('total_market_cap', 0)
            if isinstance(market_cap, (int, float)):
                market_cap = market_cap / 100000000  # 转换为亿
            else:
                market_cap = 0
            code = h.get('code', '')
            name = h.get('name', '')
            industry = h.get('industry', '')
            lines.append(
                f"{code:<12} {name:<10} "
                f"{h.get('price', 0):>10.2f} "
                f"{h.get('change_pct', 0):>7.2f}% "
                f"{h.get('turnover_rate', 0):>7.2f}% "
                f"{h.get('pe_ratio', 0):>8.2f} "
                f"{h.get('pb_ratio', 0):>8.2f} "
                f"{industry:<12} "
                f"{market_cap:>12.2f}"
            )

        lines.append(f"{'-'*120}")
        lines.append(f"共 {len(holdings)} 只股票")
        lines.append(f"{'='*120}")

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
    manager = HoldingsManager()
    print(manager.summary())
