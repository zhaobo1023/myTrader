# -*- coding: utf-8 -*-
"""
数据完整性检查服务

功能：
  1. 检查日 K 线数据是否更新到最新
  2. 检查股票数量是否正常
  3. 检查数据缺失
  4. 生成检查报告
"""
import sys
import os
from datetime import date, timedelta
from typing import Dict, List, Optional
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataMonitor:
    """数据完整性检查器"""

    def __init__(self):
        self.min_stock_count = 3000  # 最少股票数量
        self.min_records_per_stock = 30  # 每只股票最少记录数

        self.max_missing_days = 5  # 最大缺失天数

    def check_daily_data(self, expected_date: Optional[str] = None) -> Dict:
        """
        检查日 K 线数据完整性

        Args:
            expected_date: 期望的最新日期，格式 YYYY-MM-DD，默认今天
        Returns:
            检查结果字典
        """
        if expected_date is None:
            expected_date = date.today().strftime('%Y-%m-%d')

        issues = []
        warnings = []

        # 1. 检查股票总数
        stock_sql = "SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_daily"
        result = execute_query(stock_sql)
        stock_count = result[0]['cnt'] if result else 0

        if stock_count < self.min_stock_count:
            issues.append(f"股票数量过少: {stock_count} (预期 {self.min_stock_count}+)")

        # 2. 检查最新交易日期
        max_date_sql = "SELECT MAX(trade_date) as max_date FROM trade_stock_daily"
        result = execute_query(max_date_sql)
        max_date = result[0]['max_date'] if result else None

        if max_date:
            max_date_str = max_date.strftime('%Y-%m-%d') if hasattr(max_date, 'strftime') else str(max_date)
            if max_date_str < expected_date:
                issues.append(f"数据未更新: 最新日期 {max_date_str} (预期 {expected_date})")
        else:
            issues.append("数据库中没有数据")

        # 3. 检查总记录数
        total_sql = "SELECT COUNT(*) as cnt FROM trade_stock_daily"
        result = execute_query(total_sql)
        total_records = result[0]['cnt'] if result else 0

        # 4. 检查数据缺失的股票（最近30天数据不足10天的）
        check_start = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
        missing_sql = """
            SELECT stock_code, COUNT(*) as cnt
            FROM trade_stock_daily
            WHERE trade_date >= %s
            GROUP BY stock_code
            HAVING cnt < %s
        """
        missing_result = execute_query(missing_sql, [check_start, 10])
        missing_stocks = [r['stock_code'] for r in missing_result] if missing_result else []
        if len(missing_stocks) > 0:
            warnings.append(f"{len(missing_stocks)} 只股票数据不完整（近30天少于10条记录）")

        # 5. 检查完全没有数据的股票
        empty_sql = """
            SELECT stock_code FROM trade_stock_daily
            WHERE trade_date >= %s
            GROUP BY stock_code
            HAVING COUNT(*) = 0
        """
        empty_result = execute_query(empty_sql, [check_start])
        empty_stocks = [r['stock_code'] for r in empty_result] if empty_result else []

        # 6. 计算数据覆盖率
        coverage_sql = """
            SELECT
                COUNT(DISTINCT CASE WHEN trade_date = %s THEN 1 END) as covered_stocks,
                (SELECT COUNT(DISTINCT stock_code) FROM trade_stock_daily) as total_stocks
        """
        coverage_result = execute_query(coverage_sql, [expected_date])
        if coverage_result:
            covered = coverage_result[0].get('covered_stocks', 0)
            total = coverage_result[0].get('total_stocks', 0)
            coverage_rate = (covered / total * 100) if total > 0 else 0
        else:
            coverage_rate = 0

        if coverage_rate < 90:
            warnings.append(f"数据覆盖率过低: {coverage_rate:.1f}% (预期 90%+)")

        is_ok = len(issues) == 0 and len(warnings) == 0

        return {
            'is_ok': is_ok,
            'stock_count': stock_count,
            'max_date': max_date.strftime('%Y-%m-%d') if max_date else None,
            'total_records': total_records,
            'issues': issues,
            'warnings': warnings,
            'missing_stocks': missing_stocks[:50],  # 只返回前50个
            'empty_stocks': empty_stocks[:20],  # 只返回前20个
            'coverage_rate': coverage_rate,
        }

    def get_report(self) -> Dict:
        """
        生成检查报告

        Returns:
            报告字典
        """
        result = self.check_daily_data()

        report = {
            'check_time': date.now().strftime('%Y-%m-%d %H:%M:%S'),
            'is_ok': result['is_ok'],
            'summary': {
                'stock_count': result['stock_count'],
                'total_records': result['total_records'],
                'max_date': result['max_date'],
                'coverage_rate': result['coverage_rate'],
            },
            'issues': result['issues'],
            'warnings': result['warnings'],
        }

        return report

    def print_report(self) -> None:
        """打印检查报告"""
        result = self.check_daily_data()

        print("\n" + "=" * 60)
        print("数据完整性检查报告")
        print("=" * 60)
        print(f"检查时间: {date.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"检查结果: {'✅ 正常' if result['is_ok'] else '❌ 异常'}")
        print(f"\n数据概况:")
        print(f"  股票数量: {result['stock_count']}")
        print(f"  总记录数: {result['total_records']:,}")
        print(f"  最新日期: {result['max_date']}")
        print(f"  覆盖率: {result['coverage_rate']:.1f}%")

        if result['issues']:
            print(f"\n问题 ({len(result['issues'])}):")
            for issue in result['issues']:
                print(f"  ❌ {issue}")
        if result['warnings']:
            print(f"\n警告 ({len(result['warnings'])}):")
            for warning in result['warnings']:
                print(f"  ⚠️ {warning}")
        if result['missing_stocks']:
            print(f"\n数据缺失股票 (前50个):")
            print(f"  {', '.join(result['missing_stocks'][:50])}")
        if result['empty_stocks']:
            print(f"\n无数据股票 (前20个):")
            print(f"  {', '.join(result['empty_stocks'][:20])}")
        print("\n" + "=" * 60)


        return result


if __name__ == "__main__":
    monitor = DataMonitor()
    result = monitor.check_daily_data()
    monitor.print_report()
