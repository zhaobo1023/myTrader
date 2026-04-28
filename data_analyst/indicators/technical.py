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
        # 准备数据 -- NaN 必须转为 None，否则 pymysql 报错
        def _safe(v):
            if v is None:
                return None
            if isinstance(v, float) and (v != v):
                return None
            if hasattr(v, 'item'):
                v = v.item()
                if isinstance(v, float) and (v != v):
                    return None
            return v

        records = []
        for idx, row in data.iterrows():
            if pd.isna(row.get('ma5')):
                continue  # 跳过没有足够数据的行

            record = (
                stock_code,
                row['trade_date'],
                _safe(row.get('ma5')),
                _safe(row.get('ma10')),
                _safe(row.get('ma20')),
                _safe(row.get('ma60')),
                _safe(row.get('ma120')),
                _safe(row.get('ma250')),
                _safe(row.get('macd_dif')),
                _safe(row.get('macd_dea')),
                _safe(row.get('macd_histogram')),
                _safe(row.get('rsi_6')),
                _safe(row.get('rsi_12')),
                _safe(row.get('rsi_24')),
                _safe(row.get('kdj_k')),
                _safe(row.get('kdj_d')),
                _safe(row.get('kdj_j')),
                _safe(row.get('bollinger_upper')),
                _safe(row.get('bollinger_middle')),
                _safe(row.get('bollinger_lower')),
                _safe(row.get('atr')),
                _safe(row.get('volume_ratio')),
                _safe(row.get('turnover_rate')),
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

    @staticmethod
    def _nan_to_none(val):
        """Convert NaN/numpy scalar to None for MySQL compatibility."""
        if val is None:
            return None
        if isinstance(val, float) and val != val:  # NaN check
            return None
        if hasattr(val, 'item'):
            val = val.item()
            if isinstance(val, float) and val != val:
                return None
        return val

    def _compute_one_stock(self, stock_code: str, df: pd.DataFrame) -> list:
        """
        Compute all indicators for one stock and return list of record tuples.
        df is already sorted by trade_date ASC and numeric-typed.
        """
        if len(df) < 5:
            return []

        df_with = self.calculate_all_indicators(df)

        # Filter rows that have at least ma5
        valid = df_with[df_with['ma5'].notna()]
        if valid.empty:
            return []

        _n = self._nan_to_none
        indicator_cols = [
            'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma250',
            'macd_dif', 'macd_dea', 'macd_histogram',
            'rsi_6', 'rsi_12', 'rsi_24',
            'kdj_k', 'kdj_d', 'kdj_j',
            'bollinger_upper', 'bollinger_middle', 'bollinger_lower',
            'atr', 'volume_ratio', 'turnover_rate',
        ]

        records = []
        for _, row in valid.iterrows():
            records.append(
                (stock_code, row['trade_date']) +
                tuple(_n(row.get(col)) for col in indicator_cols)
            )
        return records

    def calculate_for_all_stocks(self, start_date: Optional[str] = None):
        """
        Batch-compute technical indicators for all stocks.

        Optimized flow:
        1. Get stock list, load daily data in batches of 500 stocks
        2. Compute indicators with ThreadPoolExecutor per batch
        3. Batch-write results to DB
        """
        import time as _time
        import sys
        from concurrent.futures import ThreadPoolExecutor, as_completed

        t0 = _time.time()

        if start_date is None:
            from datetime import date, timedelta
            start_date = (date.today() - timedelta(days=500)).strftime('%Y-%m-%d')

        # Get all stock codes
        code_rows = execute_query(
            "SELECT DISTINCT stock_code FROM trade_stock_daily WHERE trade_date >= %s ORDER BY stock_code",
            [start_date],
        )
        all_codes = [r['stock_code'] for r in code_rows]
        total_stocks = len(all_codes)
        print(f"Total stocks: {total_stocks}, start_date: {start_date}")
        sys.stdout.flush()

        sql_insert = """
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

        batch_stock_size = 500  # stocks per SQL batch
        total_records = 0
        total_errors = 0
        processed = 0

        for batch_start in range(0, total_stocks, batch_stock_size):
            batch_codes = all_codes[batch_start:batch_start + batch_stock_size]
            batch_num = batch_start // batch_stock_size + 1
            total_batches = (total_stocks + batch_stock_size - 1) // batch_stock_size

            # Load data for this batch
            placeholders = ','.join(['%s'] * len(batch_codes))
            sql = f"""
                SELECT stock_code, trade_date, open_price, high_price,
                       low_price, close_price, volume, turnover_rate
                FROM trade_stock_daily
                WHERE trade_date >= %s AND stock_code IN ({placeholders})
                ORDER BY stock_code, trade_date ASC
            """
            params = [start_date] + batch_codes
            rows = execute_query(sql, params)

            if not rows:
                processed += len(batch_codes)
                continue

            batch_df = pd.DataFrame(rows)
            for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'turnover_rate']:
                if col in batch_df.columns:
                    batch_df[col] = pd.to_numeric(batch_df[col], errors='coerce')

            grouped = dict(list(batch_df.groupby('stock_code')))

            # Parallel compute
            batch_records = []
            errors = 0

            def _compute(code_df_pair):
                code, df = code_df_pair
                try:
                    return self._compute_one_stock(code, df.reset_index(drop=True))
                except Exception as e:
                    return f"ERROR:{code}:{e}"

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(_compute, item) for item in grouped.items()]
                for future in as_completed(futures):
                    result = future.result()
                    if isinstance(result, str) and result.startswith("ERROR:"):
                        errors += 1
                    elif result:
                        batch_records.extend(result)

            # Batch write
            write_batch = 2000
            for i in range(0, len(batch_records), write_batch):
                chunk = batch_records[i:i + write_batch]
                try:
                    execute_many(sql_insert, chunk)
                except Exception as e:
                    print(f"  [ERROR] Batch write failed: {e}")
                    errors += 1

            processed += len(batch_codes)
            total_records += len(batch_records)
            total_errors += errors

            elapsed = _time.time() - t0
            print(f"  Batch {batch_num}/{total_batches}: {len(batch_codes)} stocks, "
                  f"{len(batch_records)} records, {errors} errors "
                  f"({processed}/{total_stocks} done, {elapsed:.0f}s elapsed)")
            sys.stdout.flush()

        total_time = _time.time() - t0
        print(f"\nDone! {total_time:.1f}s total, {total_stocks} stocks, "
              f"{total_records} records, {total_errors} errors")
