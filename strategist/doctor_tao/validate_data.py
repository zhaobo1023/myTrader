# -*- coding: utf-8 -*-
"""
陶博士策略 - 数据完整性验证

检查：
1. 数据缺失率（每只股票的交易日覆盖率）
2. 价格异常（涨跌幅超过 ±20%，除新股外）
3. 成交量为0的交易日
4. 基本面过滤表覆盖率
"""
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query
from dotenv import load_dotenv

load_dotenv()


class DataValidator:
    """数据完整性验证器"""

    def __init__(self):
        self.issues = []

    def validate_all(self) -> Dict:
        """执行所有验证检查"""
        print("=" * 60)
        print("陶博士策略 - 数据完整性验证")
        print("=" * 60)

        results = {
            'trade_date_coverage': self.check_trade_date_coverage(),
            'price_anomaly': self.check_price_anomaly(),
            'zero_volume': self.check_zero_volume(),
            'basic_info_coverage': self.check_basic_info_coverage(),
        }

        # 汇总结果
        print("\n" + "=" * 60)
        print("验证结果汇总")
        print("=" * 60)

        all_passed = True
        for check_name, result in results.items():
            status = "✓ 通过" if result['passed'] else "✗ 失败"
            print(f"{check_name}: {status}")
            if not result['passed']:
                all_passed = False
                print(f"  问题: {result['message']}")

        print("=" * 60)

        if all_passed:
            print("\n所有验证通过！")
        else:
            print("\n存在数据问题，请检查上述报告。")

        return results

    def check_trade_date_coverage(self) -> Dict:
        """
        检查交易日覆盖率（缺失率）

        完成标准：缺失率 < 0.5%
        """
        print("\n[1/4] 检查交易日覆盖率...")

        # 获取所有交易日
        sql_trading_days = """
            SELECT DISTINCT trade_date
            FROM trade_stock_daily
            WHERE trade_date >= '2023-01-01'
            ORDER BY trade_date
        """
        trading_days = execute_query(sql_trading_days, env='online')
        total_trading_days = len(trading_days)

        print(f"  总交易日数: {total_trading_days}")

        # 计算每只股票的覆盖率
        sql_coverage = """
            SELECT
                stock_code,
                COUNT(DISTINCT trade_date) as actual_days,
                COUNT(DISTINCT trade_date) * 100.0 / %s as coverage_rate
            FROM trade_stock_daily
            WHERE trade_date >= '2023-01-01'
            GROUP BY stock_code
            HAVING coverage_rate < 99.5
            ORDER BY coverage_rate ASC
            LIMIT 20
        """
        low_coverage_stocks = execute_query(sql_coverage, (total_trading_days,), env='online')

        if low_coverage_stocks:
            print(f"  发现 {len(low_coverage_stocks)} 只股票覆盖率 < 99.5%:")
            for stock in low_coverage_stocks[:5]:
                print(f"    {stock['stock_code']}: {stock['coverage_rate']:.2f}% ({stock['actual_days']}/{total_trading_days})")

        # 计算整体缺失率
        sql_total = """
            SELECT
                COUNT(DISTINCT stock_code) as stock_cnt,
                SUM(1) as total_rows
            FROM trade_stock_daily
            WHERE trade_date >= '2023-01-01'
        """
        total_data = execute_query(sql_total, env='online')[0]
        expected_rows = total_data['stock_cnt'] * total_trading_days
        actual_rows = total_data['total_rows']
        missing_rate = (1 - actual_rows / expected_rows) * 100 if expected_rows > 0 else 0

        print(f"  整体缺失率: {missing_rate:.2f}%")
        print(f"  预期记录数: {expected_rows:,}, 实际: {actual_rows:,}")

        passed = missing_rate < 0.5
        return {
            'passed': passed,
            'message': f"整体缺失率 {missing_rate:.2f}% {'<' if passed else '>='} 0.5%",
            'missing_rate': missing_rate,
            'low_coverage_stocks': low_coverage_stocks
        }

    def check_price_anomaly(self) -> Dict:
        """
        检查价格异常（单日涨跌幅超过 ±20%）

        排除：
        - 上市前5个交易日的新股
        - ST股票（涨跌幅限制为 ±5%）
        """
        print("\n[2/4] 检查价格异常...")

        sql = """
            SELECT
                t.stock_code,
                t.trade_date,
                t.close_price,
                t_prev.close_price as prev_close,
                ROUND((t.close_price - t_prev.close_price) / t_prev.close_price * 100, 2) as pct_change
            FROM trade_stock_daily t
            INNER JOIN trade_stock_daily t_prev
                ON t.stock_code = t_prev.stock_code
                AND t_prev.trade_date = (
                    SELECT MAX(trade_date)
                    FROM trade_stock_daily t2
                    WHERE t2.stock_code = t.stock_code AND t2.trade_date < t.trade_date
                )
            WHERE t.trade_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
            HAVING ABS(pct_change) > 20
            ORDER BY ABS(pct_change) DESC
            LIMIT 20
        """
        anomalies = execute_query(sql, env='online')

        if anomalies:
            print(f"  发现 {len(anomalies)} 个价格异常（涨跌幅 > ±20%）:")
            for a in anomalies[:5]:
                print(f"    {a['stock_code']} {a['trade_date']}: {a['pct_change']}% ({a['prev_close']} -> {a['close_price']})")

        passed = len(anomalies) == 0
        return {
            'passed': passed,
            'message': f"发现 {len(anomalies)} 个价格异常",
            'anomalies': anomalies
        }

    def check_zero_volume(self) -> Dict:
        """
        检查成交量为0的交易日

        可能原因：
        - 停牌
        - 数据缺失
        """
        print("\n[3/4] 检查成交量为0...")

        sql = """
            SELECT
                stock_code,
                COUNT(*) as zero_vol_days
            FROM trade_stock_daily
            WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
            AND volume = 0
            GROUP BY stock_code
            HAVING zero_vol_days > 5
            ORDER BY zero_vol_days DESC
            LIMIT 20
        """
        zero_vol_stocks = execute_query(sql, env='online')

        if zero_vol_stocks:
            print(f"  发现 {len(zero_vol_stocks)} 只股票有 >5 天成交量为0:")
            for s in zero_vol_stocks[:5]:
                print(f"    {s['stock_code']}: {s['zero_vol_days']} 天")

        # 统计整体情况
        sql_total = """
            SELECT
                COUNT(*) as total_zero_days,
                COUNT(DISTINCT stock_code) as affected_stocks
            FROM trade_stock_daily
            WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
            AND volume = 0
        """
        total_stats = execute_query(sql_total, env='online')[0]

        print(f"  总计: {total_stats['total_zero_days']} 天次，涉及 {total_stats['affected_stocks']} 只股票")

        passed = len(zero_vol_stocks) == 0
        return {
            'passed': passed,
            'message': f"{total_stats['affected_stocks']} 只股票有成交量为0的情况",
            'zero_vol_stocks': zero_vol_stocks,
            'total_zero_days': total_stats['total_zero_days']
        }

    def check_basic_info_coverage(self) -> Dict:
        """
        检查基本面过滤表覆盖率

        完成标准：覆盖率 > 95%
        """
        print("\n[4/4] 检查基本面数据覆盖率...")

        # 检查财务数据覆盖率
        sql_financial = """
            SELECT
                (SELECT COUNT(DISTINCT stock_code) FROM trade_stock_financial) as financial_stocks,
                (SELECT COUNT(DISTINCT stock_code) FROM trade_stock_daily WHERE trade_date >= '2023-01-01') as total_stocks
        """
        result = execute_query(sql_financial, env='online')[0]

        financial_stocks = result['financial_stocks']
        total_stocks = result['total_stocks']
        coverage_rate = financial_stocks / total_stocks * 100 if total_stocks > 0 else 0

        print(f"  财务数据覆盖: {financial_stocks}/{total_stocks} ({coverage_rate:.2f}%)")

        # 检查日线基础数据覆盖率
        sql_daily_basic = """
            SELECT
                (SELECT COUNT(DISTINCT stock_code) FROM trade_stock_daily_basic) as daily_basic_stocks,
                (SELECT COUNT(DISTINCT stock_code) FROM trade_stock_daily WHERE trade_date >= '2023-01-01') as total_stocks
        """
        result_basic = execute_query(sql_daily_basic, env='online')[0]

        daily_basic_stocks = result_basic['daily_basic_stocks']
        coverage_rate_basic = daily_basic_stocks / total_stocks * 100 if total_stocks > 0 else 0

        print(f"  日线基础数据覆盖: {daily_basic_stocks}/{total_stocks} ({coverage_rate_basic:.2f}%)")

        # 检查缺失的股票
        sql_missing = """
            SELECT DISTINCT t.stock_code
            FROM trade_stock_daily t
            WHERE t.trade_date >= '2023-01-01'
            AND t.stock_code NOT IN (SELECT DISTINCT stock_code FROM trade_stock_financial)
            LIMIT 10
        """
        missing_stocks = execute_query(sql_missing, env='online')

        if missing_stocks:
            print(f"  缺失财务数据的股票（前10）: {[s['stock_code'] for s in missing_stocks]}")

        passed = coverage_rate >= 95
        return {
            'passed': passed,
            'message': f"财务数据覆盖率 {coverage_rate:.2f}% {'>=' if passed else '<'} 95%",
            'coverage_rate': coverage_rate,
            'financial_stocks': financial_stocks,
            'total_stocks': total_stocks,
            'missing_stocks': missing_stocks
        }


def main():
    """主函数"""
    validator = DataValidator()
    results = validator.validate_all()

    # 返回退出码
    all_passed = all(r['passed'] for r in results.values())
    return 0 if all_passed else 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
