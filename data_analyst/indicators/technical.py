# -*- coding: utf-8 -*-
"""
技术指标计算服务

使用pandas和talib计算技术指标
支持：MA、MACD、RSI、KDJ、布林带、ATR、量比等
"""
import pandas as pd
import numpy as np
from typing import Optional, List
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query, execute_many

# 尝试导入talib，如果没有安装则使用pandas-ta
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False
    print("警告: TA-Lib未安装，将使用pandas实现（功能受限）")


class TechnicalIndicatorCalculator:
    """技术指标计算器"""

    def __init__(self):
        pass

    def calculate_ma(self, data: pd.DataFrame, periods: List[int] = [5, 10, 20, 60, 120, 250]) -> pd.DataFrame:
        """
        计算移动平均线

        Args:
            data: 包含close_price列的DataFrame
            periods: 周期列表

        Returns:
            添加了MA列的DataFrame
        """
        df = data.copy()
        for period in periods:
            df[f'ma{period}'] = df['close_price'].rolling(window=period, min_periods=period).mean()
        return df

    def calculate_macd(self, data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """
        计算MACD指标

        Args:
            data: 包含close_price列的DataFrame
            fast: 快线周期
            slow: 慢线周期
            signal: 信号线周期

        Returns:
            添加了MACD列的DataFrame
        """
        df = data.copy()

        if HAS_TALIB:
            # 使用TA-Lib
            df['macd_dif'], df['macd_dea'], df['macd_histogram'] = talib.MACD(
                df['close_price'],
                fastperiod=fast,
                slowperiod=slow,
                signalperiod=signal
            )
        else:
            # 使用pandas实现
            ema_fast = df['close_price'].ewm(span=fast, adjust=False).mean()
            ema_slow = df['close_price'].ewm(span=slow, adjust=False).mean()
            df['macd_dif'] = ema_fast - ema_slow
            df['macd_dea'] = df['macd_dif'].ewm(span=signal, adjust=False).mean()
            df['macd_histogram'] = 2 * (df['macd_dif'] - df['macd_dea'])

        return df

    def calculate_rsi(self, data: pd.DataFrame, periods: List[int] = [6, 12, 24]) -> pd.DataFrame:
        """
        计算RSI指标

        Args:
            data: 包含close_price列的DataFrame
            periods: 周期列表

        Returns:
            添加了RSI列的DataFrame
        """
        df = data.copy()

        for period in periods:
            if HAS_TALIB:
                df[f'rsi_{period}'] = talib.RSI(df['close_price'], timeperiod=period)
            else:
                # 使用pandas实现
                delta = df['close_price'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                df[f'rsi_{period}'] = 100 - (100 / (1 + rs))

        return df

    def calculate_kdj(self, data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
        """
        计算KDJ指标

        Args:
            data: 包含high_price, low_price, close_price列的DataFrame
            n: RSV周期
            m1: K值平滑周期
            m2: D值平滑周期

        Returns:
            添加了KDJ列的DataFrame
        """
        df = data.copy()

        if HAS_TALIB:
            # 使用TA-Lib的STOCH（Stochastic Oscillator）
            df['kdj_k'], df['kdj_d'] = talib.STOCH(
                df['high_price'],
                df['low_price'],
                df['close_price'],
                fastk_period=n,
                slowk_period=m1,
                slowk_matype=0,
                slowd_period=m2,
                slowd_matype=0
            )
            df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
        else:
            # 使用pandas实现
            low_min = df['low_price'].rolling(window=n, min_periods=1).min()
            high_max = df['high_price'].rolling(window=n, min_periods=1).max()
            rsv = (df['close_price'] - low_min) / (high_max - low_min) * 100

            df['kdj_k'] = rsv.ewm(com=m1 - 1, adjust=False).mean()
            df['kdj_d'] = df['kdj_k'].ewm(com=m2 - 1, adjust=False).mean()
            df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']

        return df

    def calculate_bollinger_bands(self, data: pd.DataFrame, period: int = 20, std_dev: float = 2) -> pd.DataFrame:
        """
        计算布林带

        Args:
            data: 包含close_price列的DataFrame
            period: 周期
            std_dev: 标准差倍数

        Returns:
            添加了布林带列的DataFrame
        """
        df = data.copy()

        if HAS_TALIB:
            df['bollinger_upper'], df['bollinger_middle'], df['bollinger_lower'] = talib.BBANDS(
                df['close_price'],
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev,
                matype=0
            )
        else:
            # 使用pandas实现
            df['bollinger_middle'] = df['close_price'].rolling(window=period).mean()
            std = df['close_price'].rolling(window=period).std()
            df['bollinger_upper'] = df['bollinger_middle'] + std_dev * std
            df['bollinger_lower'] = df['bollinger_middle'] - std_dev * std

        return df

    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        计算ATR（平均真实波幅）

        Args:
            data: 包含high_price, low_price, close_price列的DataFrame
            period: 周期

        Returns:
            添加了ATR列的DataFrame
        """
        df = data.copy()

        if HAS_TALIB:
            df['atr'] = talib.ATR(
                df['high_price'],
                df['low_price'],
                df['close_price'],
                timeperiod=period
            )
        else:
            # 使用pandas实现
            high = df['high_price']
            low = df['low_price']
            close = df['close_price']

            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = tr.rolling(window=period).mean()

        return df

    def calculate_volume_ratio(self, data: pd.DataFrame, period: int = 5) -> pd.DataFrame:
        """
        计算量比

        Args:
            data: 包含volume列的DataFrame
            period: 周期

        Returns:
            添加了volume_ratio列的DataFrame
        """
        df = data.copy()

        # 计算移动平均成交量
        avg_volume = df['volume'].rolling(window=period).mean()

        # 量比 = 当前成交量 / 平均成交量
        df['volume_ratio'] = df['volume'] / avg_volume

        return df

    def calculate_all_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有技术指标

        Args:
            data: 包含OHLCV数据的DataFrame

        Returns:
            添加了所有技术指标的DataFrame
        """
        df = data.copy()

        # 计算MA
        df = self.calculate_ma(df, periods=[5, 10, 20, 60, 120, 250])

        # 计算MACD
        df = self.calculate_macd(df)

        # 计算RSI
        df = self.calculate_rsi(df, periods=[6, 12, 24])

        # 计算KDJ
        df = self.calculate_kdj(df)

        # 计算布林带
        df = self.calculate_bollinger_bands(df)

        # 计算ATR
        df = self.calculate_atr(df)

        # 计算量比
        df = self.calculate_volume_ratio(df)

        return df

    def save_indicators_to_db(self, stock_code: str, data: pd.DataFrame):
        """
        将技术指标保存到数据库

        Args:
            stock_code: 股票代码
            data: 包含技术指标的DataFrame
        """
        # 准备数据
        records = []
        for idx, row in data.iterrows():
            if pd.isna(row.get('ma5')):
                continue  # 跳过没有足够数据的行

            record = (
                stock_code,
                row['trade_date'],
                row.get('ma5'),
                row.get('ma10'),
                row.get('ma20'),
                row.get('ma60'),
                row.get('ma120'),
                row.get('ma250'),
                row.get('macd_dif'),
                row.get('macd_dea'),
                row.get('macd_histogram'),
                row.get('rsi_6'),
                row.get('rsi_12'),
                row.get('rsi_24'),
                row.get('kdj_k'),
                row.get('kdj_d'),
                row.get('kdj_j'),
                row.get('bollinger_upper'),
                row.get('bollinger_middle'),
                row.get('bollinger_lower'),
                row.get('atr'),
                row.get('volume_ratio'),
                row.get('turnover_rate'),
            )
            records.append(record)

        if not records:
            print(f"  {stock_code}: 没有足够的数据计算指标")
            return

        # 批量插入/更新
        sql = """
        INSERT INTO trade_technical_indicator
        (stock_code, trade_date, ma5, ma10, ma20, ma60, ma120, ma250,
         macd_dif, macd_dea, macd_histogram, rsi_6, rsi_12, rsi_24,
         kdj_k, kdj_d, kdj_j, bollinger_upper, bollinger_middle, bollinger_lower,
         atr, volume_ratio, turnover_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        ma5=VALUES(ma5), ma10=VALUES(ma10), ma20=VALUES(ma20),
        ma60=VALUES(ma60), ma120=VALUES(ma120), ma250=VALUES(ma250),
        macd_dif=VALUES(macd_dif), macd_dea=VALUES(macd_dea), macd_histogram=VALUES(macd_histogram),
        rsi_6=VALUES(rsi_6), rsi_12=VALUES(rsi_12), rsi_24=VALUES(rsi_24),
        kdj_k=VALUES(kdj_k), kdj_d=VALUES(kdj_d), kdj_j=VALUES(kdj_j),
        bollinger_upper=VALUES(bollinger_upper), bollinger_middle=VALUES(bollinger_middle),
        bollinger_lower=VALUES(bollinger_lower), atr=VALUES(atr),
        volume_ratio=VALUES(volume_ratio), turnover_rate=VALUES(turnover_rate)
        """

        try:
            affected = execute_many(sql, records)
            print(f"  {stock_code}: 成功保存 {len(records)} 条指标数据")
        except Exception as e:
            print(f"  {stock_code}: 保存失败 - {e}")

    def calculate_for_stock(self, stock_code: str, start_date: Optional[str] = None):
        """
        为指定股票计算技术指标

        Args:
            stock_code: 股票代码
            start_date: 开始日期（可选, 默认回溯500自然日,
                        足够MA250等长周期指标的滚动窗口）
        """
        # 默认回溯500自然日(约250交易日), 覆盖MA250等长周期指标
        if start_date is None:
            from datetime import date, timedelta
            start_date = (date.today() - timedelta(days=500)).strftime('%Y-%m-%d')

        # 从数据库读取K线数据
        sql = """
        SELECT trade_date, open_price, high_price, low_price, close_price, volume, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
          AND trade_date >= %s
        """
        params = [stock_code, start_date]

        sql += " ORDER BY trade_date ASC"

        rows = execute_query(sql, params)

        if not rows:
            print(f"  {stock_code}: 没有找到K线数据")
            return

        # 转换为DataFrame
        df = pd.DataFrame(rows)

        # MySQL Decimal -> float (Decimal cannot do arithmetic with float/numpy)
        for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'turnover_rate']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 计算所有指标
        df_with_indicators = self.calculate_all_indicators(df)

        # 保存到数据库
        self.save_indicators_to_db(stock_code, df_with_indicators)

    def calculate_for_all_stocks(self, start_date: Optional[str] = None):
        """
        为所有股票计算技术指标

        Args:
            start_date: 开始日期（可选）
        """
        # 获取所有股票代码
        sql = "SELECT DISTINCT stock_code FROM trade_stock_daily ORDER BY stock_code"
        rows = execute_query(sql)
        stock_codes = [row['stock_code'] for row in rows]

        print(f"\n开始计算 {len(stock_codes)} 只股票的技术指标...\n")

        for i, stock_code in enumerate(stock_codes, 1):
            print(f"[{i}/{len(stock_codes)}] 处理 {stock_code}...")
            self.calculate_for_stock(stock_code, start_date)

        print(f"\n技术指标计算完成！")
