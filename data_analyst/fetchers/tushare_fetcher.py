# -*- coding: utf-8 -*-
"""
获取指定股票近30天交易数据
使用 Tushare Pro API

运行：python data_analyst/fetchers/tushare_fetcher.py
环境：需要设置 TUSHARE_TOKEN 环境变量
"""
import os
from datetime import datetime, timedelta
import tushare as ts


def get_pro():
    """获取 Tushare Pro 实例"""
    token = os.environ.get("TUSHARE_TOKEN")
    if not token or not str(token).strip():
        raise RuntimeError("未设置环境变量 TUSHARE_TOKEN")
    ts.set_token(str(token).strip())
    return ts.pro_api()


def fetch_recent_data(stock_code: str, days: int = 30):
    """
    获取指定股票近N天的日线交易数据

    参数:
        stock_code: 股票代码，如 '600519.SH'
        days: 天数，默认30天
    """
    # 计算日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 10)  # 多取几天，排除非交易日

    start_str = start_date.strftime('%Y%m%d')
    end_str = end_date.strftime('%Y%m%d')

    print(f"获取股票数据: {stock_code}")
    print(f"日期范围: {start_str} - {end_str} (近{days}个交易日)")
    print("-" * 50)

    try:
        pro = get_pro()

        # 使用 pro_bar 获取前复权日线数据
        df = ts.pro_bar(
            ts_code=stock_code,
            start_date=start_str,
            end_date=end_str,
            adj='qfq',  # 前复权
            freq='D'
        )

        if df is None or df.empty:
            print("错误: 无法获取数据")
            return None

        # 按日期排序，取最近N条
        df = df.sort_values('trade_date', ascending=False).head(days)
        df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)

        print(f"成功获取 {len(df)} 条数据\n")
        print("数据预览:")
        print("-" * 50)

        # 格式化输出
        for _, row in df.iterrows():
            print(f"日期: {row['trade_date']}")
            print(f"  开盘: {row['open']:.2f}  最高: {row['high']:.2f}")
            print(f"  最低: {row['low']:.2f}  收盘: {row['close']:.2f}")
            print(f"  成交量: {row['vol']:,.0f}  成交额: {row['amount']:,.2f}万")
            print()

        return df

    except Exception as e:
        print(f"获取数据失败: {e}")
        return None


if __name__ == "__main__":
    # 测试：获取贵州茅台近30天数据
    stock = "600519.SH"
    fetch_recent_data(stock, days=30)
