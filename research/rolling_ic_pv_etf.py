# -*- coding: utf-8 -*-
"""
光伏ETF滚动IC分析

分析 oil_mom_20 因子对光伏ETF (159766.SZ) 的滚动IC
检查近期信号是否还活着

运行:
    python research/rolling_ic_pv_etf.py
"""
import sys
import os
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query

# 配置
FACTOR_CODE = 'oil_mom_20'
ETF_CODE = '159766.SZ'
ETF_NAME = '光伏ETF'
ROLLING_WINDOW = 60
SPLIT_DATE = '2022-02-24'


def load_factor_data():
    sql = """
        SELECT date, value
        FROM macro_factors
        WHERE indicator = %s
        ORDER BY date ASC
    """
    rows = execute_query(sql, [FACTOR_CODE])
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    return df.set_index('date')['value']


def load_etf_data():
    sql = """
        SELECT trade_date, close_price
        FROM trade_etf_daily
        WHERE fund_code = %s
        ORDER BY trade_date ASC
    """
    rows = execute_query(sql, [ETF_CODE])
    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
    return df.set_index('trade_date')['close_price']


def main():
    print("=" * 70)
    print(f"oil_mom_20 对 {ETF_NAME} 滚动IC分析")
    print("=" * 70)

    # 加载数据
    print("\n[1] 加载数据...")
    factor = load_factor_data()
    etf_price = load_etf_data()

    print(f"  因子数据: {len(factor)} 条, {factor.index.min().date()} ~ {factor.index.max().date()}")
    print(f"  ETF数据: {len(etf_price)} 条, {etf_price.index.min().date()} ~ {etf_price.index.max().date()}")

    # 对齐日期
    aligned = pd.DataFrame({
        'factor': factor,
        'price': etf_price
    }).dropna()

    print(f"  共同时间范围: {len(aligned)} 个交易日")

    # 计算T+5未来收益
    aligned['forward_ret'] = aligned['price'].shift(-5) / aligned['price'] - 1
    aligned = aligned.dropna()

    # 计算滚动IC
    print("\n[2] 计算滚动IC (60日窗口)...")
    rolling_ic = aligned['factor'].rolling(window=ROLLING_WINDOW).corr(aligned['forward_ret'])
    rolling_ic = rolling_ic.dropna()

    print(f"  有效IC记录: {len(rolling_ic)} 条")

    # 全样本统计
    ic_mean = rolling_ic.mean()
    ic_std = rolling_ic.std()
    icir = ic_mean / ic_std

    print("\n" + "=" * 70)
    print("全样本统计 (T+5)")
    print("=" * 70)
    print(f"  IC均值: {ic_mean:.4f}")
    print(f"  IC标准差: {ic_std:.4f}")
    print(f"  ICIR: {icir:.4f}")
    print(f"  样本数: {len(rolling_ic)}")

    # 分段统计
    split_dt = pd.to_datetime(SPLIT_DATE)
    before = rolling_ic[rolling_ic.index < split_dt]
    after = rolling_ic[rolling_ic.index >= split_dt]

    print("\n" + "-" * 70)
    print(f"分段统计 (分割点: {SPLIT_DATE} 俄乌冲突)")
    print("-" * 70)

    print(f"\n冲突前 (2020 ~ {SPLIT_DATE}):")
    if len(before) > 0:
        print(f"  IC均值: {before.mean():.4f}")
        print(f"  ICIR: {before.mean()/before.std():.4f}")
        print(f"  样本数: {len(before)}")

    print(f"\n冲突后 ({SPLIT_DATE} ~ 2026):")
    if len(after) > 0:
        print(f"  IC均值: {after.mean():.4f}")
        print(f"  ICIR: {after.mean()/after.std():.4f}")
        print(f"  样本数: {len(after)}")

    # 近100天统计
    recent_100 = rolling_ic.tail(100)
    print("\n" + "=" * 70)
    print("近期信号状态 (近100个交易日)")
    print("=" * 70)
    print(f"  IC均值: {recent_100.mean():.4f}")
    print(f"  ICIR: {recent_100.mean()/recent_100.std():.4f}")
    print(f"  负IC占比: {(recent_100 < 0).mean()*100:.1f}%")

    # 最近10天滚动IC
    recent_10 = rolling_ic.tail(10)
    print("\n最近10天滚动IC:")
    for date, ic in recent_10.items():
        status = 'OK' if ic < 0 else 'WEAK'  # 负IC是有效的
        print(f"  {date.strftime('%Y-%m-%d')}: IC={ic:+.4f} {status}")

    # 判断信号状态
    print("\n" + "=" * 70)
    print("信号状态判断")
    print("=" * 70)

    recent_icir = recent_100.mean() / recent_100.std()
    expected_sign = np.sign(ic_mean)  # 全样本IC方向
    actual_sign = np.sign(recent_100.mean())  # 近期IC方向

    if abs(recent_icir) > 0.3 and actual_sign == expected_sign:
        status = 'ALIVE'
        reason = f'近100天ICIR={recent_icir:.2f}, 方向一致'
    elif abs(recent_icir) > 0.15:
        status = 'WEAKENING'
        reason = f'近100天ICIR={recent_icir:.2f}, 方向一致但减弱'
    else:
        status = 'DEAD'
        reason = f'近100天ICIR={recent_icir:.2f}, 可能失效'

    print(f"  状态: {status}")
    print(f"  原因: {reason}")

    # 结论
    print("\n" + "=" * 70)
    print("分析结论")
    print("=" * 70)

    if status == 'ALIVE':
        print(f"\n结论: {ETF_NAME} 信号存活")
        print(f"  - oil_mom_20 对光伏ETF有持续的负向预测能力")
        print(f"  - 近期ICIR={recent_icir:.2f} > 0.3，信号稳定")
        print(f"  - 建议: 可以进入回测阶段")
    elif status == 'WEAKENING':
        print(f"\n结论: {ETF_NAME} 信号减弱")
        print(f"  - 近期ICIR={recent_icir:.2f}，信号有所衰减")
        print(f"  - 建议: 继续观察，暂缓回测")
    else:
        print(f"\n结论: {ETF_NAME} 信号可能失效")
        print(f"  - 近期ICIR={recent_icir:.2f}，信号衰减明显")
        print(f"  - 建议: 不建议使用该因子")

    print("\n" + "=" * 70)
    print("分析完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
