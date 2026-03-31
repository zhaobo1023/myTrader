# -*- coding: utf-8 -*-
"""
陶博士策略 - 信号筛选器

实现两阶段漏斗筛选：
1. 基本面过滤（ST、上市时间、成交额、净利润）
2. 动量筛选（RPS >= 90、MA20 > MA60、动量斜率 > 0）
3. 反转候选（RPS >= 80、价格分位 < 30）
4. 大盘条件判断
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.doctor_tao.data_fetcher import DoctorTaoDataFetcher
from strategist.doctor_tao.indicators import IndicatorCalculator
from config.db import execute_query


@dataclass
class ScreenerParams:
    """
    筛选参数配置
    
    参数说明参考文档 doctor_tao_strategy.md 第三节
    """
    # 基本面过滤参数（第3.1节）
    min_list_days: int = 250  # 上市满1年（250交易日）
    min_avg_amount: float = 5000  # 近60日均成交额 ≥ 5000万
    min_net_profit: float = 0  # 近2年至少1年净利润为正
    min_price: float = 3.0  # 收盘价 ≥ 3元

    # 动量筛选参数（第3.2节）
    rps_threshold: float = 95  # RPS ≥ 95
    rps_continuous_weeks: int = 4  # 连续4周RPS≥90
    rps_continuous_min: float = 90  # 连续期间最低RPS
    return_60d_rank_threshold: float = 70  # 近60日涨幅排名前30%（即排名≥70）
    volume_ratio_threshold: float = 1.2  # 近4周均量 > 52周均量×1.2

    # 反转候选参数（第3.3节）
    reversal_price_percentile_threshold: float = 35  # 750日历史分位 < 35%
    reversal_return_60d_threshold: float = 0.15  # 近60日涨幅 > 15%
    reversal_rps_slope_threshold: float = 1.0  # RPS动量斜率 Z > 1.0
    reversal_volume_ratio_threshold: float = 1.5  # 近4周均量 > 52周均量×1.5
    reversal_rps_max: float = 90  # 当前RPS < 90（尚未过热）

    # 大盘条件参数（第3.4节）
    # 沪指站上MA50 → 开启信号
    # 沪指在MA50与MA120之间 → 降低仓位，只关注RPS≥97
    # 沪指跌破MA120 → 暂停所有信号
    index_code: str = '000001.SH'  # 上证指数


class SignalScreener:
    """信号筛选器"""

    def __init__(self, params: Optional[ScreenerParams] = None):
        self.params = params or ScreenerParams()
        self.fetcher = DoctorTaoDataFetcher(use_cache=True)

    def apply_prefilter(self, stock_list: List[str], filter_table: pd.DataFrame, latest_prices: Optional[pd.DataFrame] = None) -> List[str]:
        """
        基本面底线过滤（文档第3.1节）
        
        过滤条件：
        1. 非ST / 退市风险
        2. 上市满1年（250交易日）
        3. 近60日均成交额 ≥ 5000万
        4. 近2年至少1年净利润为正
        5. 收盘价 ≥ 3元
        """
        print(f"\n[1/4] 基本面过滤...")
        print(f"  输入股票数: {len(stock_list)}")

        # 筛选条件
        today = datetime.now().date()

        # 1. 非ST股票
        filtered = filter_table[filter_table['is_st'] == False].copy()
        print(f"  非ST股票: {len(filtered)} 只")

        # 2. 上市满1年（250交易日 ≈ 365自然日）
        min_list_natural_days = int(self.params.min_list_days * 365 / 250)
        filtered = filtered[
            (pd.to_datetime(filtered['list_date']).dt.date < today - timedelta(days=min_list_natural_days))
        ]
        print(f"  上市满{self.params.min_list_days}交易日（约{min_list_natural_days}自然日）: {len(filtered)} 只")

        # 3. 成交额过滤（近60日均成交额 ≥ 5000万）
        if 'avg_amount_60d' in filtered.columns:
            filtered = filtered[filtered['avg_amount_60d'] >= self.params.min_avg_amount]
            print(f"  成交额≥{self.params.min_avg_amount}万: {len(filtered)} 只")

        # 4. 净利润过滤（近2年至少1年净利润为正）
        if 'latest_net_profit' in filtered.columns:
            # 简化处理：最新净利润为正
            filtered = filtered[filtered['latest_net_profit'] > self.params.min_net_profit]
            print(f"  净利润>0: {len(filtered)} 只")

        # 只保留在输入列表中的股票
        filtered = filtered[filtered['stock_code'].isin(stock_list)]

        result = filtered['stock_code'].tolist()
        print(f"  过滤后股票数: {len(result)} 只")
        print(f"  过滤率: {(1 - len(result)/len(stock_list))*100:.1f}%")

        return result
    
    def apply_price_filter(self, indicators_df: pd.DataFrame) -> pd.DataFrame:
        """
        价格过滤：收盘价 ≥ 3元（排除仙股）
        """
        if self.params.min_price > 0:
            before_count = len(indicators_df)
            indicators_df = indicators_df[indicators_df['close'] >= self.params.min_price]
            print(f"  价格≥{self.params.min_price}元: {len(indicators_df)} 只（过滤 {before_count - len(indicators_df)} 只）")
        return indicators_df

    def screen_momentum(self, indicators_df: pd.DataFrame) -> pd.DataFrame:
        """
        第一层：动量筛选
        
        捕捉当前 RPS 已经强势、月线趋势向上、可以跟进参与主升浪的股票
        
        条件（文档第3.2节）：
        1. RPS ≥ 95（且连续4周≥90，需要历史数据支持）
        2. 股价站上月线（close > MA20）
        3. 股价站上年线（close > MA250）
        4. 近60日涨幅排名前30%
        5. 成交量放大（近4周均量 > 52周均量×1.2）
        """
        print(f"\n[2/4] 动量筛选...")

        filtered = indicators_df.copy()
        initial_count = len(filtered)

        # 1. RPS ≥ 95
        filtered = filtered[filtered['rps'] >= self.params.rps_threshold]
        print(f"  RPS >= {self.params.rps_threshold}: {len(filtered)} 只")

        # 2. 股价站上月线（close > MA20）
        filtered = filtered[filtered['close'] > filtered['ma20']]
        print(f"  股价 > MA20（月线）: {len(filtered)} 只")

        # 3. 股价站上年线（close > MA250）
        if 'ma250' in filtered.columns:
            filtered = filtered[filtered['close'] > filtered['ma250']]
            print(f"  股价 > MA250（年线）: {len(filtered)} 只")

        # 4. 近60日涨幅排名前30%（排名分位 >= 70）
        if 'return_60d_rank' in filtered.columns:
            filtered = filtered[filtered['return_60d_rank'] >= self.params.return_60d_rank_threshold]
            print(f"  60日涨幅排名前30%: {len(filtered)} 只")

        # 5. 成交量放大（近4周均量 > 52周均量×1.2）
        if 'volume_ratio' in filtered.columns:
            filtered = filtered[filtered['volume_ratio'] >= self.params.volume_ratio_threshold]
            print(f"  成交量放大（比值≥{self.params.volume_ratio_threshold}）: {len(filtered)} 只")

        # 添加信号类型
        filtered['signal_type'] = 'momentum'

        print(f"  最终动量信号: {len(filtered)} 只（筛选率: {len(filtered)/initial_count*100:.2f}%）")

        return filtered

    def screen_reversal(self, indicators_df: pd.DataFrame) -> pd.DataFrame:
        """
        第二层：反转候选筛选
        
        捕捉处于底部积累、尚未启动但未来可能启动的股票
        
        条件（文档第3.3节）：
        1. 价格历史低位：750日历史分位 < 35%
        2. 近期开始启动：近60日涨幅 > 15%
        3. RPS快速提升：RPS动量斜率 Z > 1.0
        4. 成交量异动：近4周均量 > 52周均量×1.5
        5. RPS尚未到顶：当前RPS < 90（尚未过热）
        """
        print(f"\n[3/4] 反转候选筛选...")

        filtered = indicators_df.copy()
        initial_count = len(filtered)

        # 1. 价格历史低位：750日历史分位 < 35%
        filtered = filtered[filtered['price_percentile'] < self.params.reversal_price_percentile_threshold]
        print(f"  价格分位 < {self.params.reversal_price_percentile_threshold}%: {len(filtered)} 只")

        # 2. RPS尚未到顶：当前RPS < 90（尚未过热）
        filtered = filtered[filtered['rps'] < self.params.reversal_rps_max]
        print(f"  RPS < {self.params.reversal_rps_max}（未过热）: {len(filtered)} 只")

        # 3. RPS快速提升：RPS动量斜率 Z > 1.0
        if 'rps_slope' in filtered.columns:
            filtered = filtered[filtered['rps_slope'] > self.params.reversal_rps_slope_threshold]
            print(f"  RPS斜率Z > {self.params.reversal_rps_slope_threshold}: {len(filtered)} 只")

        # 4. 近期开始启动：近60日涨幅 > 15%
        if 'return_60d_rank' in filtered.columns:
            # 使用60日涨幅排名作为代理，排名>50%表示涨幅为正且较好
            # 更精确的做法需要原始涨幅数据
            pass  # 暂时跳过，因为当前指标只有排名没有原始涨幅

        # 5. 成交量异动：近4周均量 > 52周均量×1.5
        if 'volume_ratio' in filtered.columns:
            filtered = filtered[filtered['volume_ratio'] >= self.params.reversal_volume_ratio_threshold]
            print(f"  成交量异动（比值≥{self.params.reversal_volume_ratio_threshold}）: {len(filtered)} 只")

        # 添加信号类型
        filtered['signal_type'] = 'reversal'

        print(f"  最终反转候选: {len(filtered)} 只（筛选率: {len(filtered)/initial_count*100:.2f}%）")

        return filtered

    def _fetch_stock_names(self, codes: List[str]) -> Dict[str, str]:
        """通过 akshare 查询股票名称"""
        if not codes:
            return {}
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            # code 列是纯数字（如 000593），需要拼后缀
            code_name_map = dict(zip(df['code'], df['name']))
            result = {}
            for code in codes:
                pure_code = code.split('.')[0]
                result[code] = code_name_map.get(pure_code, '')
            found = sum(1 for v in result.values() if v)
            print(f"  查询股票名称: {found}/{len(codes)} 只匹配")
            return result
        except Exception as e:
            print(f"  查询股票名称失败: {e}")
            return {}

    def check_market_condition(self) -> Dict[str, any]:
        """
        大盘条件判断（文档第3.4节）
        
        返回：
        - status: 'bullish' / 'neutral' / 'bearish'
        - bullish: 沪指站上MA50 → 开启信号输出
        - neutral: 沪指在MA50与MA120之间 → 降低仓位，只关注RPS≥97
        - bearish: 沪指跌破MA120 → 暂停所有信号
        """
        print(f"\n[4/4] 大盘条件判断...")

        result = {
            'status': 'bullish',
            'close': None,
            'ma50': None,
            'ma120': None,
            'message': ''
        }

        try:
            # 获取上证指数数据
            index_df = self.fetcher.fetch_daily_price(
                self.params.index_code, 
                start_date='2023-01-01'
            )

            if len(index_df) == 0:
                print("  无法获取大盘数据，默认通过")
                result['message'] = '无法获取大盘数据'
                return result

            # 计算 MA50/MA120
            index_df['ma50'] = index_df['close'].rolling(window=50).mean()
            index_df['ma120'] = index_df['close'].rolling(window=120).mean()

            # 最新值
            latest = index_df.iloc[-1]
            close = float(latest['close'])
            ma50 = float(latest['ma50']) if pd.notna(latest['ma50']) else None
            ma120 = float(latest['ma120']) if pd.notna(latest['ma120']) else None

            result['close'] = close
            result['ma50'] = ma50
            result['ma120'] = ma120

            print(f"  上证指数: {close:.2f}")
            print(f"  MA50: {ma50:.2f if ma50 else 'N/A'}, MA120: {ma120:.2f if ma120 else 'N/A'}")

            if ma50 is None or ma120 is None:
                result['message'] = 'MA数据不足'
                return result

            # 判断大盘状态
            if close > ma50:
                result['status'] = 'bullish'
                result['message'] = '沪指站上MA50 → 开启信号输出'
                print(f"  ✓ 状态: BULLISH（沪指 > MA50）")
            elif close > ma120:
                result['status'] = 'neutral'
                result['message'] = '沪指在MA50与MA120之间 → 只关注RPS≥97'
                print(f"  ⚠ 状态: NEUTRAL（MA120 < 沪指 < MA50）")
            else:
                result['status'] = 'bearish'
                result['message'] = '沪指跌破MA120 → 暂停所有信号'
                print(f"  ✗ 状态: BEARISH（沪指 < MA120）")

            return result

        except Exception as e:
            print(f"  大盘条件判断失败: {e}，默认通过")
            result['message'] = f'判断失败: {e}'
            return result

    def run_screener(self, date: Optional[str] = None, output_csv: bool = True) -> pd.DataFrame:
        """
        运行筛选器

        Args:
            date: 指定日期，格式 'YYYY-MM-DD'，默认最新日期
            output_csv: 是否输出CSV文件

        Returns:
            筛选结果DataFrame
        """
        print("=" * 60)
        print("陶博士策略 - 信号筛选器")
        print("=" * 60)

        # 1. 获取所有股票列表
        print("\n[1/5] 获取股票列表...")
        all_stocks = self.fetcher.fetch_all_stocks()
        print(f"  总股票数: {len(all_stocks)}")

        # 2. 获取基本面过滤表
        print("\n[2/5] 获取基本面过滤表...")
        filter_table = self.fetcher.fetch_filter_table()

        # 3. 基本面过滤
        filtered_stocks = self.apply_prefilter(all_stocks, filter_table)

        # 4. 批量获取价格数据（使用全量股票）
        print(f"\n[3/5] 批量获取价格数据...")
        test_stocks = filtered_stocks  # 使用全量股票
        print(f"  全量股票数: {len(test_stocks)}")

        price_dict = self.fetcher.fetch_daily_price_batch(
            test_stocks,
            start_date=(datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')
        )

        # 转换为 DataFrame
        price_list = []
        for code, df in price_dict.items():
            if len(df) > 0:
                df['stock_code'] = code
                price_list.append(df)

        if not price_list:
            print("无有效价格数据")
            return pd.DataFrame()

        price_df = pd.concat(price_list, ignore_index=True)
        print(f"  获取到 {len(price_df)} 条价格数据")

        # 5. 计算所有指标
        indicators_df = IndicatorCalculator.calc_all_indicators(price_df)

        # 只保留最新日期的数据
        if date:
            latest_df = indicators_df[indicators_df['trade_date'] == date]
        else:
            latest_date = indicators_df['trade_date'].max()
            latest_df = indicators_df[indicators_df['trade_date'] == latest_date]

        print(f"\n最新日期: {latest_df['trade_date'].iloc[0]}")
        print(f"有效股票数: {len(latest_df)}")

        # 5.5 价格过滤（收盘价 ≥ 3元）
        latest_df = self.apply_price_filter(latest_df)

        # 6. 动量筛选
        momentum_df = self.screen_momentum(latest_df)

        # 7. 反转候选筛选
        reversal_df = self.screen_reversal(latest_df)

        # 8. 大盘条件判断
        market_condition = self.check_market_condition()
        market_status = market_condition['status']

        # 9. 根据大盘状态过滤信号
        result_list = []

        if market_status == 'bearish':
            # 沪指跌破MA120 → 暂停所有信号
            print("\n⚠️ 大盘处于熊市状态，暂停所有信号输出")
            momentum_df = pd.DataFrame()
            reversal_df = pd.DataFrame()
        elif market_status == 'neutral':
            # 沪指在MA50与MA120之间 → 只关注RPS≥97的动量股
            if len(momentum_df) > 0:
                momentum_df = momentum_df[momentum_df['rps'] >= 97]
                print(f"\n⚠️ 大盘中性，只保留RPS≥97的动量信号: {len(momentum_df)} 只")

        if len(momentum_df) > 0:
            result_list.append(momentum_df)

        if len(reversal_df) > 0:
            result_list.append(reversal_df)

        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result['market_status'] = market_status
            result['market_message'] = market_condition['message']
        else:
            result = pd.DataFrame()

        # 9.5 查询股票名称
        if len(result) > 0:
            name_map = self._fetch_stock_names(result['stock_code'].tolist())
            result['stock_name'] = result['stock_code'].map(name_map)
            # 把 stock_name 放在 stock_code 后面
            cols = list(result.columns)
            cols.remove('stock_name')
            idx = cols.index('stock_code') + 1
            cols.insert(idx, 'stock_name')
            result = result[cols]

        # 10. 输出 CSV
        if output_csv and len(result) > 0:
            output_dir = os.path.join(os.path.dirname(__file__), 'output')
            os.makedirs(output_dir, exist_ok=True)

            output_file = os.path.join(
                output_dir,
                f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            result.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"\n结果已保存到: {output_file}")

        # 11. 打印统计信息
        print("\n" + "=" * 60)
        print("筛选结果统计:")
        print("=" * 60)
        print(f"动量信号: {len(momentum_df)} 只")
        print(f"反转候选: {len(reversal_df)} 只")
        print(f"大盘状态: {market_status.upper()} - {market_condition['message']}")
        print("=" * 60)

        return result


if __name__ == '__main__':
    # 测试筛选器
    screener = SignalScreener()
    result = screener.run_screener()

    if len(result) > 0:
        print("\n前10只股票:")
        cols = ['stock_code', 'stock_name', 'trade_date', 'signal_type', 'rps', 'close', 'ma20', 'ma250', 'volume_ratio']
        available_cols = [c for c in cols if c in result.columns]
        print(result[available_cols].head(10))
