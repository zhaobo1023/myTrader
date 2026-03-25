# -*- coding: utf-8 -*-
"""
ETF因子回测模块

对 oil_mom_20 因子进行单标的回测验证：
- 能源化工ETF (159930.SZ)
- 光伏ETF (159766.SZ)

运行:
    python research/etf_factor_backtest.py
"""
import sys
import os
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.db import execute_query

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_PLOT = True
except ImportError:
    HAS_PLOT = False
    print("警告: matplotlib 未安装")


# ============================================================
# 配置
# ============================================================

# 回测参数
INITIAL_CASH = 100000  # 初始资金 10万
COMMISSION_RATE = 0.0002  # 手续费率 0.02%
SLIPPAGE_RATE = 0.0001  # 滑点率 0.01%

# 因子阈值（根据滚动IC分析结果设定）
# 因子分布: 27% < -0.05, 41% 在 [-0.05, 0.05], 32% > 0.05
# 光伏ETF与oil_mom_20负相关： 因子跌 -> 光伏涨
FACTOR_THRESHOLD_LONG = -0.10   # 像多阈值（因子值低于-0.10时做多）
FACTOR_THRESHOLD_SHORT = 0.10    # 做空阈值（因子值高于0.10时做空）

# 目标ETF
TARGET_ETFS = {
    '159930.SZ': {
        'name': '能源化工ETF',
        'direction': 'negative',  # 负相关，因子跌→做多
    },
    '159766.SZ': {
        'name': '光伏ETF',
        'direction': 'negative',  # 负相关，因子跌→做多
    },
}


# ============================================================
# 数据加载
# ============================================================

def load_factor_data(factor_code: str,
                     start_date: str = None,
                     end_date: str = None) -> pd.Series:
    """从数据库加载因子数据"""
    sql = """
        SELECT date, value
        FROM macro_factors
        WHERE indicator = %s
    """
    params = [factor_code]

    if start_date:
        sql += " AND date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND date <= %s"
        params.append(end_date)

    sql += " ORDER BY date ASC"

    rows = execute_query(sql, params)

    if not rows:
        return pd.Series()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    return df.set_index('date')['value']


def load_etf_data(etf_code: str,
                  start_date: str = None,
                  end_date: str = None) -> pd.DataFrame:
    """从数据库加载ETF日线数据"""
    sql = """
        SELECT trade_date, open_price, high_price, low_price, close_price, volume
        FROM trade_etf_daily
        WHERE fund_code = %s
    """
    params = [etf_code]

    if start_date:
        sql += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND trade_date <= %s"
        params.append(end_date)

    sql += " ORDER BY trade_date ASC"

    rows = execute_query(sql, params)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df.set_index('trade_date')


# ============================================================
# 回测引擎
# ============================================================

class ETFFactorBacktest:
    """ETF因子回测引擎"""

    def __init__(self,
                 etf_code: str,
                 etf_name: str,
                 factor_code: str = 'oil_mom_20',
                 initial_cash: float = INITIAL_CASH,
                 commission_rate: float = COMMISSION_RATE,
                 slippage_rate: float = SLIPPAGE_RATE,
                 factor_direction: str = 'negative'):
        """
        Args:
            etf_code: ETF代码
            etf_name: ETF名称
            factor_code: 因子代码
            initial_cash: 初始资金
            commission_rate: 手续费率
            slippage_rate: 滑点率
            factor_direction: 因子方向 ('positive' 或 'negative')
        """
        self.etf_code = etf_code
        self.etf_name = etf_name
        self.factor_code = factor_code
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.factor_direction = factor_direction

        # 回测状态
        self.cash = initial_cash
        self.position = 0  # 持仓份额
        self.position_value = 0  # 持仓市值
        self.trades = []  # 交易记录
        self.daily_values = []  # 每日净值

    def run(self, start_date: str = None, end_date: str = None) -> Dict:
        """
        执行回测

        Returns:
            回测结果字典
        """
        print(f"\n开始回测: {self.etf_name} ({self.etf_code})")
        print(f"  因子: {self.factor_code}")
        print(f"  方向: {self.factor_direction}")
        print(f"  初始资金: {self.initial_cash:,.0f}")
        print(f"  手续费率: {self.commission_rate*100:.2f}%")
        print(f"  滑点率: {self.slippage_rate*100:.2f}%")

        # 加载数据
        factor = load_factor_data(self.factor_code, start_date, end_date)
        etf = load_etf_data(self.etf_code, start_date, end_date)

        if factor.empty or etf.empty:
            print("  [错误] 数据不足")
            return {}

        print(f"  因子数据: {len(factor)} 条")
        print(f"  ETF数据: {len(etf)} 条")

        # 对齐日期
        aligned = pd.DataFrame({
            'factor': factor,
            'open': etf['open_price'],
            'high': etf['high_price'],
            'low': etf['low_price'],
            'close': etf['close_price'],
        }).dropna()

        print(f"  共同交易日: {len(aligned)}")

        if len(aligned) < 100:
            print("  [错误] 数据不足100天")
            return {}

        # 重置状态
        self.cash = self.initial_cash
        self.position = 0
        self.position_value = 0
        self.trades = []
        self.daily_values = []

        # 逐日回测
        # 正确逻辑: 第T天因子值 -> 第T+1天开盘执行交易
        dates = aligned.index.tolist()

        for i in range(len(dates) - 1):  # 最后一天不执行交易（没有下一天数据）
            date = dates[i]
            next_date = dates[i + 1]

            row = aligned.loc[date]
            next_row = aligned.loc[next_date]

            factor_val = row['factor']
            close_price = row['close']
            next_open_price = next_row['open']

            # 计算当前市值
            self.position_value = self.position * close_price
            total_value = self.cash + self.position_value

            # 记录每日净值
            self.daily_values.append({
                'date': date,
                'cash': self.cash,
                'position': self.position,
                'position_value': self.position_value,
                'total_value': total_value,
                'factor': factor_val,
                'close': close_price,
            })

            # 生成交易信号（基于今天的因子值）
            signal = self._generate_signal(factor_val)

            # 执行交易（在下一天开盘价执行）
            if signal != 0:
                self._execute_trade(signal, next_open_price, next_date)

        # 计算回测指标
        results = self._calculate_metrics()

        return results

    def _generate_signal(self, factor_val: float) -> int:
        """
        生成交易信号

        Args:
            factor_val: 因子值

        Returns:
            1: 买入, -1: 卖出, 0: 持有
        """
        # 根据因子方向调整阈值
        # 光伏ETF与oil_mom_20负相关: 因子跌 -> 光伏涨
        # 所以: 因子值低(看多原油) -> 做多光伏
        if self.factor_direction == 'negative':
            # 负相关: 因子值 < FACTOR_THRESHOLD_LONG (-0.10) 时做多
            if factor_val < FACTOR_THRESHOLD_LONG and self.position == 0:
                return 1  # 买入
            # 因子值 > FACTOR_THRESHOLD_SHORT (0.10) 时平仓
            elif factor_val > FACTOR_THRESHOLD_SHORT and self.position > 0:
                return -1  # 卖出
        else:
            # 正相关: 因子值 > FACTOR_THRESHOLD_LONG (-0.10) 时做多
            if factor_val > FACTOR_THRESHOLD_LONG and self.position == 0:
                return 1  # 买入
            # 因子值 < FACTOR_THRESHOLD_SHORT (0.10) 时平仓
            elif factor_val < FACTOR_THRESHOLD_SHORT and self.position > 0:
                return -1  # 卖出
        return 0

    def _execute_trade(self, signal: int, price: float, date):
        """执行交易"""
        if signal == 1 and self.position == 0:
            # 买入（全仓）
            # 考虑滑点后的实际价格
            actual_price = price * (1 + self.slippage_rate)
            # 用实际价格计算可买入份额，并预留手续费
            shares = self.cash / (actual_price * (1 + self.commission_rate))
            cost = shares * actual_price * (1 + self.commission_rate)

            if cost <= self.cash:
                self.position = shares
                self.cash -= cost
                self.trades.append({
                    'date': date,
                    'action': 'BUY',
                    'price': actual_price,
                    'shares': shares,
                    'cost': cost,
                })

        elif signal == -1 and self.position > 0:
            # 卖出
            actual_price = price * (1 - self.slippage_rate)
            revenue = self.position * actual_price * (1 - self.commission_rate)

            self.cash += revenue
            self.trades.append({
                'date': date,
                'action': 'SELL',
                'price': actual_price,
                'shares': self.position,
                'revenue': revenue,
            })
            self.position = 0

    def _calculate_metrics(self) -> Dict:
        """计算回测指标"""
        if not self.daily_values:
            return {}

        df = pd.DataFrame(self.daily_values)
        df = df.set_index('date')

        # 计算收益率
        df['return'] = df['total_value'].pct_change()
        df['cum_return'] = (1 + df['return']).cumprod() - 1

        # 基准收益率（买入持有）
        first_close = df['close'].iloc[0]
        df['benchmark_value'] = self.initial_cash * df['close'] / first_close
        df['benchmark_return'] = df['benchmark_value'].pct_change()
        df['benchmark_cum_return'] = (1 + df['benchmark_return']).cumprod() - 1

        # 统计指标
        total_return = df['total_value'].iloc[-1] / self.initial_cash - 1
        benchmark_return = df['benchmark_value'].iloc[-1] / self.initial_cash - 1

        # 年化收益率
        days = len(df)
        annual_return = (1 + total_return) ** (252 / days) - 1
        benchmark_annual = (1 + benchmark_return) ** (252 / days) - 1

        # 最大回撤
        df['peak'] = df['total_value'].cummax()
        df['drawdown'] = (df['total_value'] - df['peak']) / df['peak']
        max_drawdown = df['drawdown'].min()

        # 夏普比率
        excess_return = df['return'].mean() * 252 - benchmark_annual
        volatility = df['return'].std() * np.sqrt(252)
        sharpe = excess_return / volatility if volatility > 0 else 0

        # 胜率
        winning_trades = len([t for t in self.trades if t['action'] == 'SELL' and t.get('revenue', 0) > t.get('cost', 0)])
        total_trades = len([t for t in self.trades if t['action'] == 'SELL'])

        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # 交易次数
        trade_count = len(self.trades)

        results = {
            'etf_code': self.etf_code,
            'etf_name': self.etf_name,
            'factor_code': self.factor_code,
            'start_date': df.index[0],
            'end_date': df.index[-1],
            'trading_days': days,
            'initial_cash': self.initial_cash,
            'final_value': df['total_value'].iloc[-1],
            'total_return': total_return,
            'annual_return': annual_return,
            'benchmark_return': benchmark_return,
            'benchmark_annual': benchmark_annual,
            'excess_return': total_return - benchmark_return,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'win_rate': win_rate,
            'trade_count': trade_count,
            'daily_values': df,
            'trades': self.trades,
        }

        return results


# ============================================================
# 结果展示
# ============================================================

def print_backtest_results(results: Dict):
    """打印回测结果"""
    print("\n" + "=" * 70)
    print(f"回测结果: {results['etf_name']} ({results['etf_code']})")
    print("=" * 70)

    print(f"\n回测区间: {results['start_date'].date()} ~ {results['end_date'].date()}")
    print(f"交易天数: {results['trading_days']}")

    print(f"\n收益指标:")
    print(f"  最终净值: {results['final_value']:,.2f}")
    print(f"  总收益率: {results['total_return']*100:.2f}%")
    print(f"  年化收益率: {results['annual_return']*100:.2f}%")
    print(f"  基准收益率: {results['benchmark_return']*100:.2f}%")
    print(f"  基准年化: {results['benchmark_annual']*100:.2f}%")
    print(f"  超额收益: {results['excess_return']*100:.2f}%")

    print(f"\n风险指标:")
    print(f"  最大回撤: {results['max_drawdown']*100:.2f}%")
    print(f"  夏普比率: {results['sharpe_ratio']:.2f}")

    print(f"\n交易统计:")
    print(f"  交易次数: {results['trade_count']}")
    print(f"  胜率: {results['win_rate']*100:.1f}%")

    # 评价
    print(f"\n策略评价:")
    if results['excess_return'] > 0.05 and results['max_drawdown'] > -0.2:
        print("  ✓ 优秀策略: 显著超额收益 + 可控回撤")
    elif results['excess_return'] > 0 and results['max_drawdown'] > -0.3:
        print("  ✓ 有效策略: 正超额收益 + 可接受回撤")
    elif results['excess_return'] > 0:
        print("  ⚠ 一般策略: 正超额收益但回撤较大")
    else:
        print("  ✗ 无效策略: 未跑赢基准")


def plot_backtest_results(results: Dict, save_path: str):
    """绘制回测结果图"""
    if not HAS_PLOT:
        return

    df = results['daily_values']

    fig, axes = plt.subplots(3, 1, figsize=(14, 12))

    # 子图1: 净值曲线
    ax1 = axes[0]
    ax1.plot(df.index, df['total_value'], label='策略净值', linewidth=1.5)
    ax1.plot(df.index, df['benchmark_value'], label='基准净值', linewidth=1.5, alpha=0.7)
    ax1.set_title(f"{results['etf_name']} - 策略净值 vs 基准", fontsize=12, fontweight='bold')
    ax1.set_ylabel('净值 (元)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 子图2: 因子值
    ax2 = axes[1]
    ax2.bar(df.index, df['factor'], width=1, alpha=0.7)
    ax2.axhline(y=FACTOR_THRESHOLD_LONG, color='green', linestyle='--', label=f'做多阈值 ({FACTOR_THRESHOLD_LONG})')
    ax2.axhline(y=FACTOR_THRESHOLD_SHORT, color='red', linestyle='--', label=f'做空阈值 ({FACTOR_THRESHOLD_SHORT})')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_title(f"因子值 ({results['factor_code']})", fontsize=12, fontweight='bold')
    ax2.set_ylabel('因子值')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 子图3: 回撤
    ax3 = axes[2]
    ax3.fill_between(df.index, df['drawdown'], 0, alpha=0.5, color='red')
    ax3.set_title('策略回撤', fontsize=12, fontweight='bold')
    ax3.set_ylabel('回撤')
    ax3.set_xlabel('日期')
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\n图表已保存: {save_path}")
    plt.close()


# ============================================================
# 主函数
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='ETF因子回测')
    parser.add_argument('--etf', type=str, help='ETF代码 (如 159766.SZ)')
    parser.add_argument('--start', type=str, help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, default='output', help='输出目录')
    args = parser.parse_args()

    print("=" * 70)
    print("ETF因子回测 - oil_mom_20")
    print("=" * 70)

    # 确定回测标的
    if args.etf:
        etf_code = args.etf
        etf_info = TARGET_ETFS.get(etf_code, {'name': etf_code, 'direction': 'negative'})
    else:
        # 默认使用光伏ETF（ICIR最高）
        etf_code = '159766.SZ'
        etf_info = TARGET_ETFS[etf_code]

    print(f"\n回测标的: {etf_info['name']} ({etf_code})")

    # 创建回测引擎
    backtest = ETFFactorBacktest(
        etf_code=etf_code,
        etf_name=etf_info['name'],
        factor_code='oil_mom_20',
        factor_direction=etf_info['direction'],
    )

    # 执行回测
    results = backtest.run(
        start_date=args.start,
        end_date=args.end,
    )

    if not results:
        print("\n回测失败")
        return

    # 打印结果
    print_backtest_results(results)

    # 绘图
    if HAS_PLOT:
        os.makedirs(args.output, exist_ok=True)
        plot_path = os.path.join(args.output, f'backtest_{etf_code.replace(".", "")}_oil_mom_20.png')
        plot_backtest_results(results, plot_path)

    print("\n" + "=" * 70)
    print("回测完成!")
    print("=" * 70)


if __name__ == "__main__":
    main()
