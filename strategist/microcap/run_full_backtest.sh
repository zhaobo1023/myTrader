#!/bin/bash
# -*- coding: utf-8 -*-
"""
微盘股策略 - 全量回测脚本

时间估算：
- 数据加载：10-30秒（一次性加载3年数据）
- 因子计算：每个交易日约0.1秒，600个交易日 = 60秒
- 回测执行：每个交易日约0.05秒，600个交易日 = 30秒
- 总计：约2-3分钟

策略参数：
- 因子：PEG
- 选股数：15只
- 持有天数：1天（T+1买入，次日卖出）
- 市值百分位：20%（选取市值后20%的微盘股）
"""

set -e

echo "========================================================================"
echo "微盘股PEG策略 - 全量回测"
echo "========================================================================"

# 时间范围：3年完整回测
START_DATE="2023-01-01"
END_DATE="2026-03-31"

# 策略参数
FACTOR="peg"           # PEG因子
TOP_N=15               # 每期选15只
HOLD_DAYS=1            # 持有1天
MARKET_CAP_PCT=0.20    # 市值后20%

# 交易成本
BUY_COST=0.0003        # 买入 0.03%
SELL_COST=0.0013       # 卖出 0.13% (含印花税)
SLIPPAGE=0.001         # 滑点 0.1%

echo ""
echo "回测配置："
echo "  时间范围: $START_DATE ~ $END_DATE"
echo "  因子类型: $FACTOR"
echo "  选股数量: $TOP_N"
echo "  持有天数: $HOLD_DAYS"
echo "  市值百分位: $MARKET_CAP_PCT (后20%微盘股)"
echo "  买入成本: $BUY_COST"
echo "  卖出成本: $SELL_COST"
echo "  滑点: $SLIPPAGE"
echo ""
echo "预计耗时: 2-3分钟"
echo "========================================================================"

START_TIME=$(date +%s)

# 执行回测
python -m strategist.microcap.run_backtest \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --factor "$FACTOR" \
    --top-n $TOP_N \
    --hold-days $HOLD_DAYS \
    --market-cap-percentile $MARKET_CAP_PCT \
    --buy-cost-rate $BUY_COST \
    --sell-cost-rate $SELL_COST \
    --slippage-rate $SLIPPAGE \
    --exclude-st

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================================================"
echo "回测完成！"
echo "总耗时: $ELAPSED 秒 ($(($ELAPSED / 60)) 分 $(($ELAPSED % 60)) 秒)"
echo ""
echo "结果文件位置:"
echo "  - output/microcap/backtest_*.csv              (交易记录)"
echo "  - output/microcap/backtest_daily_values_*.csv (每日净值)"
echo "  - output/microcap/backtest_summary.json        (统计摘要)"
echo "  - output/microcap/backtest_monthly_*.csv       (月度收益)"
echo "  - output/microcap/nav_vs_benchmark_*.csv       (基准对比)"
echo "========================================================================"
