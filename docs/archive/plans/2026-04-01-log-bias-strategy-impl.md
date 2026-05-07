# Log Bias Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the log bias (liu chen ming) daily monitoring module for ETF trend tracking.

**Architecture:** Load close prices from `trade_etf_daily` (online MySQL), compute `log_bias = (ln(close) - EMA(ln(close), 20)) * 100`, run a 5-state signal state machine with 10-day cooldown, persist to `trade_log_bias_daily`, and generate a Markdown daily report.

**Tech Stack:** Python 3.10+, pandas, numpy, pymysql (via `config.db`), argparse

**Design Doc:** `docs/log_bias_strategy_design.md`

---

## Key Context for the Implementer

- **No emoji** in any code, comments, reports, CSV, logs (MySQL utf8 cannot store 4-byte emoji). Use `[RED]`, `[WARN]`, `[OK]` instead.
- **Database column name discrepancy:** The DDL in `config/models.py` says `stock_code`, but the actual production table uses `fund_code`. All queries MUST use `fund_code`.
- **DB connection pattern:** `from config.db import execute_query, execute_update, get_connection, ONLINE_DB_CONFIG`
- **Module pattern:** Follow `strategist/tech_scan/` -- use `sys.path.insert(0, ...)` for cross-package imports, relative imports within the package.
- **`__init__.py`** exports key classes.
- **Config** uses `@dataclass`.
- **Storage** uses `INSERT ... ON DUPLICATE KEY UPDATE` with retry wrapper.
- **CLI entry** uses `argparse` with `if __name__ == '__main__': main()`.

---

### Task 1: Create Package Structure and Config

**Files:**
- Create: `strategist/log_bias/__init__.py`
- Create: `strategist/log_bias/config.py`

**Step 1: Create `strategist/log_bias/config.py`**

```python
# -*- coding: utf-8 -*-
"""log_bias config"""

from dataclasses import dataclass, field
from typing import Dict, List

DEFAULT_ETFS: Dict[str, str] = {
    # tech growth
    '159995.SZ': 'chipETF',
    '515050.SH': '5GETF',
    '516160.SH': 'newEnergyCarETF',
    '515790.SH': 'solarETF',
    '159941.SZ': 'nasdaqETF',
    # consumer & pharma
    '512690.SH': 'liquorETF',
    '512010.SH': 'pharmaETF',
    # cyclical & finance
    '512880.SH': 'securitiesETF',
    '515220.SH': 'coalETF',
    '518880.SH': 'goldETF',
    # broad base
    '510300.SH': 'hs300ETF',
    '588000.SH': 'star50ETF',
}

# signal thresholds
OVERHEAT_THRESHOLD = 15.0
BREAKOUT_THRESHOLD = 5.0
STALL_THRESHOLD = -5.0
COOLDOWN_DAYS = 10
EMA_WINDOW = 20


@dataclass
class LogBiasConfig:
    """config for log bias module"""
    etfs: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ETFS))
    ema_window: int = EMA_WINDOW
    overheat_threshold: float = OVERHEAT_THRESHOLD
    breakout_threshold: float = BREAKOUT_THRESHOLD
    stall_threshold: float = STALL_THRESHOLD
    cooldown_days: int = COOLDOWN_DAYS
    lookback_days: int = 400
    output_dir: str = '/Users/zhaobo/Documents/notes/Finance/Output'
    log_dir: str = 'output/log_bias'
    db_env: str = 'online'
```

**Step 2: Create `strategist/log_bias/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""log_bias - ETF trend tracking via log bias indicator"""

from .config import LogBiasConfig, DEFAULT_ETFS

__all__ = ['LogBiasConfig', 'DEFAULT_ETFS']
```

**Step 3: Commit**

```bash
git add strategist/log_bias/__init__.py strategist/log_bias/config.py
git commit -m "feat(log-bias): add config and package structure"
```

---

### Task 2: Core Calculator

**Files:**
- Create: `strategist/log_bias/calculator.py`
- Create: `strategist/log_bias/tests/__init__.py`
- Create: `strategist/log_bias/tests/test_calculator.py`

**Step 1: Write the failing test**

Create `strategist/log_bias/tests/__init__.py` (empty file).

Create `strategist/log_bias/tests/test_calculator.py`:

```python
# -*- coding: utf-8 -*-
"""tests for log bias calculator"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
import pandas as pd
import numpy as np


class TestLogBiasCalculator:

    def test_log_bias_basic(self):
        """basic correctness: log_bias sign matches price direction"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [10.0, 10.5, 11.0, 10.8, 11.2]})
        result = calculate_log_bias(df)
        assert np.isclose(result['ln_close'].iloc[0], np.log(10.0))
        assert result['log_bias'].iloc[-1] > 0

    def test_log_bias_ema_convergence(self):
        """EMA convergence: after 120 days of constant price, log_bias ~ 0"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [100.0] * 200})
        result = calculate_log_bias(df)
        assert abs(result['log_bias'].iloc[120]) < 0.01
        assert abs(result['log_bias'].iloc[-1]) < 0.001

    def test_log_bias_nan_handling(self):
        """NaN should propagate"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [10.0, np.nan, 11.0, 10.5]})
        result = calculate_log_bias(df)
        assert pd.isna(result['ln_close'].iloc[1])

    def test_log_bias_low_price(self):
        """low price (<1 yuan) should not error"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [0.5, 0.52, 0.48, 0.51, 0.50]})
        result = calculate_log_bias(df)
        assert not result['log_bias'].isna().all()

    def test_output_columns(self):
        """output should have exact columns"""
        from strategist.log_bias.calculator import calculate_log_bias
        df = pd.DataFrame({'close': [10.0] * 30})
        result = calculate_log_bias(df)
        expected_cols = ['close', 'ln_close', 'ema_ln', 'log_bias']
        assert list(result.columns) == expected_cols
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -m pytest strategist/log_bias/tests/test_calculator.py -v`
Expected: FAIL (ImportError)

**Step 3: Write minimal implementation**

Create `strategist/log_bias/calculator.py`:

```python
# -*- coding: utf-8 -*-
"""log bias calculator: (ln(close) - EMA(ln(close), 20)) * 100"""

import numpy as np
import pandas as pd


def calculate_log_bias(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """
    calculate log bias

    Args:
        df: must have 'close' column
        window: EMA span, default 20

    Returns:
        DataFrame with columns: [close, ln_close, ema_ln, log_bias]
    """
    out = df[['close']].copy()
    out['ln_close'] = np.log(out['close'])
    out['ema_ln'] = out['ln_close'].ewm(span=window, adjust=False).mean()
    out['log_bias'] = (out['ln_close'] - out['ema_ln']) * 100
    return out
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -m pytest strategist/log_bias/tests/test_calculator.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add strategist/log_bias/calculator.py strategist/log_bias/tests/
git commit -m "feat(log-bias): add core calculator with tests"
```

---

### Task 3: Signal State Machine

**Files:**
- Create: `strategist/log_bias/signal_detector.py`
- Create: `strategist/log_bias/tests/test_signal_detector.py`

**Step 1: Write the failing test**

Create `strategist/log_bias/tests/test_signal_detector.py`:

```python
# -*- coding: utf-8 -*-
"""tests for signal detector"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
import pandas as pd
from datetime import date, timedelta


class TestSignalDetector:

    def test_breakout_signal(self):
        """log_bias crosses above 5 -> breakout"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': 4.0, 'signal_state': 'normal',
                'last_breakout_date': None, 'last_stall_date': None}
        curr = {'log_bias': 6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'breakout'

    def test_pullback_signal(self):
        """after breakout, log_bias falls to [0,5) -> pullback"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': 7.0, 'signal_state': 'breakout',
                'last_breakout_date': date.today() - timedelta(days=5),
                'last_stall_date': None}
        curr = {'log_bias': 3.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'pullback'

    def test_stall_signal(self):
        """log_bias < -5 -> stall"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': -3.0, 'signal_state': 'normal',
                'last_breakout_date': None, 'last_stall_date': None}
        curr = {'log_bias': -6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'stall'

    def test_overheat_signal(self):
        """log_bias > 15 -> overheat"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector()
        prev = {'log_bias': 12.0, 'signal_state': 'breakout',
                'last_breakout_date': date.today(), 'last_stall_date': None}
        curr = {'log_bias': 16.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'overheat'

    def test_cooldown_period(self):
        """within 10 days of stall, no breakout allowed"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector(cooldown_days=10)
        prev = {'log_bias': 4.0, 'signal_state': 'normal',
                'last_breakout_date': None,
                'last_stall_date': date.today() - timedelta(days=5)}
        curr = {'log_bias': 6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] != 'breakout'
        assert result['signal_state'] == 'normal'

    def test_cooldown_expired(self):
        """after cooldown expires, breakout is allowed again"""
        from strategist.log_bias.signal_detector import SignalDetector
        detector = SignalDetector(cooldown_days=10)
        prev = {'log_bias': 4.0, 'signal_state': 'normal',
                'last_breakout_date': None,
                'last_stall_date': date.today() - timedelta(days=15)}
        curr = {'log_bias': 6.0}
        result = detector.detect(curr, prev)
        assert result['signal_state'] == 'breakout'

    def test_detect_all(self):
        """detect_all produces signal_state column"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector
        import numpy as np
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(200) * 0.5)
        df = pd.DataFrame({'close': prices})
        result = calculate_log_bias(df)
        detector = SignalDetector()
        signals = detector.detect_all(result)
        assert 'signal_state' in signals.columns
        assert len(signals) == len(result)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -m pytest strategist/log_bias/tests/test_signal_detector.py -v`
Expected: FAIL (ImportError)

**Step 3: Write minimal implementation**

Create `strategist/log_bias/signal_detector.py`:

```python
# -*- coding: utf-8 -*-
"""signal state machine with cooldown logic"""

import logging
import pandas as pd
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SIGNAL_LABELS = {
    'overheat': '[RED] overheat',
    'breakout': '[YELLOW] breakout',
    'pullback': '[GREEN] pullback',
    'normal': '[GRAY] normal',
    'stall': '[RED] stall',
}


class SignalDetector:
    """5-state signal machine: overheat / breakout / pullback / normal / stall"""

    def __init__(self, cooldown_days: int = 10,
                 breakout_threshold: float = 5.0,
                 overheat_threshold: float = 15.0,
                 stall_threshold: float = -5.0):
        self.cooldown_days = cooldown_days
        self.breakout_threshold = breakout_threshold
        self.overheat_threshold = overheat_threshold
        self.stall_threshold = stall_threshold

    def detect(self, curr: dict, prev: dict) -> dict:
        """
        detect signal for a single day

        Args:
            curr: {'log_bias': float}
            prev: {'log_bias': float, 'signal_state': str,
                   'last_breakout_date': date|None, 'last_stall_date': date|None}

        Returns:
            dict with signal_state, last_breakout_date, last_stall_date, prev_state
        """
        lb = curr['log_bias']
        prev_state = prev.get('signal_state', 'normal')
        last_stall_date = prev.get('last_stall_date')
        last_breakout_date = prev.get('last_breakout_date')
        today = date.today()

        # check cooldown: if stall happened within cooldown_days, suppress breakout
        in_cooldown = False
        if last_stall_date is not None:
            if (today - last_stall_date).days < self.cooldown_days:
                in_cooldown = True

        # determine state by priority: overheat > stall > breakout > pullback > normal
        if lb > self.overheat_threshold:
            state = 'overheat'
        elif lb < self.stall_threshold:
            state = 'stall'
            last_stall_date = today
        elif lb >= self.breakout_threshold:
            if in_cooldown:
                state = 'normal'
            else:
                state = 'breakout'
                last_breakout_date = today
        elif lb >= 0:
            # pullback: log_bias in [0, breakout_threshold) AND recently was above breakout
            if prev_state in ('breakout', 'pullback', 'overheat'):
                state = 'pullback'
            else:
                state = 'normal'
        else:
            state = 'normal'

        return {
            'signal_state': state,
            'prev_state': prev_state,
            'last_breakout_date': last_breakout_date,
            'last_stall_date': last_stall_date,
        }

    def detect_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        detect signals for entire DataFrame

        Args:
            df: must have 'log_bias' column (output of calculate_log_bias)

        Returns:
            DataFrame with added columns: signal_state, prev_state,
            last_breakout_date, last_stall_date
        """
        out = df.copy()
        out['signal_state'] = 'normal'
        out['prev_state'] = 'normal'
        out['last_breakout_date'] = None
        out['last_stall_date'] = None

        for i in range(len(out)):
            curr = {'log_bias': out['log_bias'].iloc[i]}
            prev = {
                'log_bias': out['log_bias'].iloc[i - 1] if i > 0 else 0.0,
                'signal_state': out['signal_state'].iloc[i - 1] if i > 0 else 'normal',
                'last_breakout_date': out['last_breakout_date'].iloc[i - 1] if i > 0 else None,
                'last_stall_date': out['last_stall_date'].iloc[i - 1] if i > 0 else None,
            }
            result = self.detect(curr, prev)
            out.iloc[i, out.columns.get_loc('signal_state')] = result['signal_state']
            out.iloc[i, out.columns.get_loc('prev_state')] = result['prev_state']
            out.iloc[i, out.columns.get_loc('last_breakout_date')] = result['last_breakout_date']
            out.iloc[i, out.columns.get_loc('last_stall_date')] = result['last_stall_date']

        return out
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -m pytest strategist/log_bias/tests/test_signal_detector.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add strategist/log_bias/signal_detector.py strategist/log_bias/tests/test_signal_detector.py
git commit -m "feat(log-bias): add signal state machine with cooldown"
```

---

### Task 4: Data Loader

**Files:**
- Create: `strategist/log_bias/data_loader.py`

**Step 1: Write implementation**

Create `strategist/log_bias/data_loader.py`:

```python
# -*- coding: utf-8 -*-
"""load ETF daily close prices from trade_etf_daily"""

import logging
import sys
import os

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query

logger = logging.getLogger(__name__)


class DataLoader:
    """load close prices from trade_etf_daily"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def load(self, ts_code: str, lookback_days: int = 400) -> pd.DataFrame:
        """
        load close prices for a single ETF

        Args:
            ts_code: e.g. '510300.SH'
            lookback_days: number of calendar days to look back

        Returns:
            DataFrame with columns: [trade_date, close], sorted by trade_date ASC
        """
        from datetime import timedelta
        end = pd.Timestamp.now().strftime('%Y-%m-%d')
        start = (pd.Timestamp.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

        sql = """
            SELECT trade_date, close_price as close
            FROM trade_etf_daily
            WHERE fund_code = %s AND trade_date >= %s AND trade_date <= %s
            ORDER BY trade_date ASC
        """
        rows = execute_query(sql, (ts_code, start, end), env=self.env)
        if not rows:
            logger.warning(f"No data for {ts_code} in [{start}, {end}]")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        df = df.reset_index(drop=True)
        logger.info(f"Loaded {len(df)} rows for {ts_code}")
        return df

    def load_multi(self, ts_codes: list, lookback_days: int = 400) -> dict:
        """
        load close prices for multiple ETFs

        Returns:
            dict: {ts_code: DataFrame}
        """
        result = {}
        for code in ts_codes:
            df = self.load(code, lookback_days)
            if len(df) > 0:
                result[code] = df
        return result

    def get_latest_trade_date(self) -> str:
        """get the latest trade date in the database"""
        sql = "SELECT MAX(trade_date) as latest FROM trade_etf_daily"
        rows = execute_query(sql, env=self.env)
        if rows and rows[0]['latest']:
            return str(rows[0]['latest'])
        return ''
```

**Step 2: Quick smoke test (manual)**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -c "from strategist.log_bias.data_loader import DataLoader; dl = DataLoader(); print(dl.get_latest_trade_date()); df = dl.load('510300.SH', lookback_days=30); print(len(df), df.tail(3))"`
Expected: prints latest date and last 3 rows

**Step 3: Commit**

```bash
git add strategist/log_bias/data_loader.py
git commit -m "feat(log-bias): add data loader from trade_etf_daily"
```

---

### Task 5: Storage Layer

**Files:**
- Create: `strategist/log_bias/storage.py`

**Step 1: Write implementation**

Create `strategist/log_bias/storage.py`:

```python
# -*- coding: utf-8 -*-
"""storage layer for trade_log_bias_daily"""

import logging
import sys
import os
import time
from typing import Optional

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query, execute_update, get_connection

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS trade_log_bias_daily (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts_code VARCHAR(20) NOT NULL COMMENT 'code',
    trade_date DATE NOT NULL COMMENT 'trade date',
    close_price DOUBLE COMMENT 'close price',
    ln_close DOUBLE COMMENT 'ln(close)',
    ema_ln_20 DOUBLE COMMENT 'EMA(ln_close, 20)',
    log_bias DOUBLE COMMENT 'log bias',
    signal_state VARCHAR(20) COMMENT 'signal: overheat/breakout/pullback/normal/stall',
    prev_state VARCHAR(20) COMMENT 'previous state',
    last_breakout_date DATE COMMENT 'last breakout date',
    last_stall_date DATE COMMENT 'last stall date',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_date (ts_code, trade_date),
    INDEX idx_date (trade_date),
    INDEX idx_signal (signal_state, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='log bias daily data';
"""

UPSERT_SQL = """
INSERT INTO trade_log_bias_daily
    (ts_code, trade_date, close_price, ln_close, ema_ln_20, log_bias,
     signal_state, prev_state, last_breakout_date, last_stall_date)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    close_price = VALUES(close_price),
    ln_close = VALUES(ln_close),
    ema_ln_20 = VALUES(ema_ln_20),
    log_bias = VALUES(log_bias),
    signal_state = VALUES(signal_state),
    prev_state = VALUES(prev_state),
    last_breakout_date = VALUES(last_breakout_date),
    last_stall_date = VALUES(last_stall_date)
"""


def _retry(func, desc: str, max_retries: int = 3, delay: int = 5):
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise
            logger.warning(f"{desc} attempt {attempt} failed: {e}, retry in {delay}s")
            time.sleep(delay)


class LogBiasStorage:
    """storage for trade_log_bias_daily"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def init_table(self):
        """create table if not exists"""
        def _do():
            conn = get_connection(self.env)
            cursor = conn.cursor()
            cursor.execute(DDL)
            conn.commit()
            cursor.close()
            conn.close()
        _retry(_do, "init trade_log_bias_daily table")
        logger.info("table trade_log_bias_daily ready")

    def save(self, ts_code: str, df: pd.DataFrame) -> int:
        """
        save DataFrame to database

        Args:
            ts_code: ETF code
            df: must have columns [trade_date, close, ln_close, ema_ln, log_bias,
                                   signal_state, prev_state, last_breakout_date, last_stall_date]

        Returns:
            number of rows saved
        """
        if df.empty:
            return 0

        count = 0
        conn = get_connection(self.env)
        try:
            cursor = conn.cursor()
            for _, row in df.iterrows():
                trade_date = row['trade_date']
                if hasattr(trade_date, 'strftime'):
                    trade_date = trade_date.strftime('%Y-%m-%d')
                else:
                    trade_date = str(trade_date)

                params = [
                    ts_code,
                    trade_date,
                    float(row['close']) if pd.notna(row['close']) else None,
                    float(row['ln_close']) if pd.notna(row['ln_close']) else None,
                    float(row['ema_ln']) if pd.notna(row['ema_ln']) else None,
                    float(row['log_bias']) if pd.notna(row['log_bias']) else None,
                    row.get('signal_state', ''),
                    row.get('prev_state', ''),
                    row.get('last_breakout_date'),
                    row.get('last_stall_date'),
                ]
                cursor.execute(UPSERT_SQL, params)
                count += 1
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

        logger.info(f"Saved {count} rows for {ts_code}")
        return count

    def get_latest_date(self, ts_code: str) -> Optional[str]:
        """get latest trade_date for a given ts_code"""
        sql = """
            SELECT MAX(trade_date) as latest
            FROM trade_log_bias_daily
            WHERE ts_code = %s
        """
        rows = execute_query(sql, (ts_code,), env=self.env)
        if rows and rows[0]['latest']:
            return str(rows[0]['latest'])
        return None

    def load_history(self, ts_code: str, start_date: str = None) -> pd.DataFrame:
        """load stored log_bias data for a ts_code"""
        if start_date:
            sql = """
                SELECT * FROM trade_log_bias_daily
                WHERE ts_code = %s AND trade_date >= %s
                ORDER BY trade_date ASC
            """
            rows = execute_query(sql, (ts_code, start_date), env=self.env)
        else:
            sql = """
                SELECT * FROM trade_log_bias_daily
                WHERE ts_code = %s
                ORDER BY trade_date ASC
            """
            rows = execute_query(sql, (ts_code,), env=self.env)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
```

**Step 2: Smoke test (manual)**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -c "from strategist.log_bias.storage import LogBiasStorage; s = LogBiasStorage(); s.init_table(); print('OK')"`
Expected: prints "OK"

**Step 3: Commit**

```bash
git add strategist/log_bias/storage.py
git commit -m "feat(log-bias): add storage layer with DDL and upsert"
```

---

### Task 6: Report Generator

**Files:**
- Create: `strategist/log_bias/report_generator.py`

**Step 1: Write implementation**

Create `strategist/log_bias/report_generator.py`:

```python
# -*- coding: utf-8 -*-
"""markdown report generator for log bias daily"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

SIGNAL_DISPLAY = {
    'overheat': '[RED] overheat',
    'breakout': '[YELLOW] breakout',
    'pullback': '[GREEN] pullback',
    'normal': '[GRAY] normal',
    'stall': '[RED] stall',
}

STATE_CN = {
    'overheat': 'overheat',
    'breakout': 'breakout',
    'pullback': 'pullback',
    'normal': 'normal',
    'stall': 'stall',
}


class ReportGenerator:
    """generate markdown daily report"""

    def __init__(self, output_dir: str, etf_names: Dict[str, str]):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.etf_names = etf_names

    def generate(self, summary_data: List[dict], report_date: str) -> str:
        """
        generate report

        Args:
            summary_data: list of dicts, each with keys:
                ts_code, name, close, log_bias, signal_state, prev_state
            report_date: YYYY-MM-DD

        Returns:
            path to the generated report file
        """
        if not summary_data:
            logger.warning("No data to generate report")
            return ''

        df = pd.DataFrame(summary_data)

        lines = []
        lines.append(f"# Log Bias Daily Report - {report_date}")
        lines.append("")

        # signal summary
        lines.append("## Signal Summary")
        lines.append("")
        lines.append("| Status | Count | ETFs |")
        lines.append("|--------|-------|------|")

        for state in ['overheat', 'breakout', 'pullback', 'normal', 'stall']:
            subset = df[df['signal_state'] == state]
            if len(subset) == 0:
                names_str = '-'
            else:
                names_str = ', '.join(subset['name'].tolist())
            display = SIGNAL_DISPLAY.get(state, state)
            lines.append(f"| {display} | {len(subset)} | {names_str} |")

        lines.append("")

        # detail table sorted by log_bias desc
        lines.append("## Detail Data")
        lines.append("")
        lines.append("| ETF | Code | Close | LogBias | Status | Change |")
        lines.append("|-----|------|-------|---------|--------|--------|")

        df_sorted = df.sort_values('log_bias', ascending=False)
        for _, row in df_sorted.iterrows():
            display = SIGNAL_DISPLAY.get(row['signal_state'], row['signal_state'])
            change = f"{row.get('prev_state', '')}->{row['signal_state']}" if row.get('prev_state') and row['prev_state'] != row['signal_state'] else '-'
            lines.append(
                f"| {row['name']} | {row['ts_code']} | {row['close']:.4f} | "
                f"{row['log_bias']:.2f}% | {display} | {change} |"
            )

        lines.append("")
        lines.append("---")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        report_text = "\n".join(lines)
        filename = f"LogBias_{report_date.replace('-', '')}.md"
        filepath = self.output_dir / filename
        filepath.write_text(report_text, encoding='utf-8')
        logger.info(f"Report saved: {filepath}")
        return str(filepath)
```

**Step 2: Commit**

```bash
git add strategist/log_bias/report_generator.py
git commit -m "feat(log-bias): add markdown report generator"
```

---

### Task 7: CLI Entry Point (run_daily.py)

**Files:**
- Create: `strategist/log_bias/run_daily.py`

**Step 1: Write implementation**

Create `strategist/log_bias/run_daily.py`:

```python
# -*- coding: utf-8 -*-
"""CLI entry point for log bias daily monitoring"""

import argparse
import logging
import sys
import os
from datetime import datetime, timedelta

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from strategist.log_bias.config import LogBiasConfig, DEFAULT_ETFS
from strategist.log_bias.calculator import calculate_log_bias
from strategist.log_bias.signal_detector import SignalDetector
from strategist.log_bias.data_loader import DataLoader
from strategist.log_bias.storage import LogBiasStorage
from strategist.log_bias.report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('log_bias')


def run_daily(config: LogBiasConfig, target_date: str = None):
    """
    run daily log bias calculation for all tracked ETFs

    Args:
        config: LogBiasConfig
        target_date: target date string (YYYY-MM-DD), None = use latest trade date
    """
    logger.info("=" * 60)
    logger.info("Start log bias daily calculation")
    logger.info("=" * 60)

    # init
    loader = DataLoader(env=config.db_env)
    storage = LogBiasStorage(env=config.db_env)
    detector = SignalDetector(
        cooldown_days=config.cooldown_days,
        breakout_threshold=config.breakout_threshold,
        overheat_threshold=config.overheat_threshold,
        stall_threshold=config.stall_threshold,
    )
    generator = ReportGenerator(output_dir=config.output_dir, etf_names=config.etfs)

    storage.init_table()

    # determine target date
    if target_date:
        report_date = target_date
    else:
        latest = loader.get_latest_trade_date()
        report_date = latest
        if not latest:
            logger.error("Cannot determine latest trade date")
            return

    logger.info(f"Report date: {report_date}")
    logger.info(f"Tracking {len(config.etfs)} ETFs")

    summary_data = []
    for ts_code, name in config.etfs.items():
        try:
            df = loader.load(ts_code, lookback_days=config.lookback_days)
            if df.empty:
                logger.warning(f"No data for {ts_code} ({name})")
                continue

            result = calculate_log_bias(df, window=config.ema_window)
            signals = detector.detect_all(result)

            # save to db
            storage.save(ts_code, signals)

            # get the row for report_date
            signals['trade_date_str'] = pd.to_datetime(signals['trade_date']).dt.strftime('%Y-%m-%d')
            row = signals[signals['trade_date_str'] == report_date]
            if row.empty:
                # use last row if target date not found
                row = signals.tail(1)

            if not row.empty:
                r = row.iloc[0]
                summary_data.append({
                    'ts_code': ts_code,
                    'name': name,
                    'close': r['close'],
                    'log_bias': r['log_bias'],
                    'signal_state': r['signal_state'],
                    'prev_state': r['prev_state'],
                })
                logger.info(f"  {name} ({ts_code}): log_bias={r['log_bias']:.2f}, state={r['signal_state']}")

        except Exception as e:
            logger.error(f"Error processing {ts_code} ({name}): {e}")

    # generate report
    if summary_data:
        report_path = generator.generate(summary_data, report_date)
        if report_path:
            logger.info(f"Report: {report_path}")
    else:
        logger.warning("No data for report")

    logger.info("=" * 60)
    logger.info("Done")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Log Bias Daily Monitor')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'])
    parser.add_argument('--output', type=str, help='Output directory for report')

    args = parser.parse_args()

    config = LogBiasConfig()
    if args.env:
        config.db_env = args.env
    if args.output:
        config.output_dir = args.output

    try:
        run_daily(config, target_date=args.date)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
```

**Step 2: End-to-end smoke test**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -m strategist.log_bias.run_daily --date 2026-03-31`
Expected: processes 12 ETFs, saves to DB, generates report markdown file

**Step 3: Commit**

```bash
git add strategist/log_bias/run_daily.py
git commit -m "feat(log-bias): add CLI entry point run_daily"
```

---

### Task 8: Integration Test

**Files:**
- Create: `strategist/log_bias/tests/test_integration.py`

**Step 1: Write integration test**

Create `strategist/log_bias/tests/test_integration.py`:

```python
# -*- coding: utf-8 -*-
"""integration tests for log bias module"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
import pandas as pd
import numpy as np


class TestIntegration:

    def test_full_pipeline_single_etf(self):
        """end-to-end: load -> calculate -> detect -> save -> load back"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector
        from strategist.log_bias.storage import LogBiasStorage

        # build synthetic data
        np.random.seed(42)
        dates = pd.date_range('2025-01-01', periods=300, freq='B')
        prices = 1.0 + np.cumsum(np.random.randn(300) * 0.01)
        df = pd.DataFrame({'trade_date': dates, 'close': prices})

        # calculate
        result = calculate_log_bias(df)
        assert 'log_bias' in result.columns
        assert len(result) == 300

        # detect
        detector = SignalDetector()
        signals = detector.detect_all(result)
        assert 'signal_state' in signals.columns

        # verify all states are valid
        valid_states = {'overheat', 'breakout', 'pullback', 'normal', 'stall'}
        actual_states = set(signals['signal_state'].unique())
        assert actual_states.issubset(valid_states)

    def test_incremental_update_logic(self):
        """verify that detect_all can resume from a previous state"""
        from strategist.log_bias.calculator import calculate_log_bias
        from strategist.log_bias.signal_detector import SignalDetector
        import numpy as np

        np.random.seed(99)
        dates = pd.date_range('2025-01-01', periods=200, freq='B')
        prices = 1.0 + np.cumsum(np.random.randn(200) * 0.01)
        df = pd.DataFrame({'trade_date': dates, 'close': prices})

        result = calculate_log_bias(df)
        detector = SignalDetector()

        # run on first 150 days
        signals_150 = detector.detect_all(result.iloc[:150])

        # manually set prev state from day 150 and run remaining 50
        last_state = signals_150.iloc[-1]['signal_state']
        assert last_state in ('overheat', 'breakout', 'pullback', 'normal', 'stall')
```

**Step 2: Run integration test**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -m pytest strategist/log_bias/tests/test_integration.py -v`
Expected: 2 passed

**Step 3: Commit**

```bash
git add strategist/log_bias/tests/test_integration.py
git commit -m "feat(log-bias): add integration tests"
```

---

### Task 9: Run All Tests and Final Verification

**Step 1: Run all tests**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -m pytest strategist/log_bias/tests/ -v`
Expected: all tests pass (14 total)

**Step 2: Run full end-to-end with online DB**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -m strategist.log_bias.run_daily --date 2026-03-31`
Expected: processes all 12 ETFs, generates report

**Step 3: Verify report content**

Read the generated report file and confirm it has the correct structure with signal summary table and detail table.

**Step 4: Commit (if any fixes were needed)**

---

## Summary

| Task | File | Description |
|------|------|-------------|
| 1 | `config.py`, `__init__.py` | Package structure and configuration |
| 2 | `calculator.py`, `tests/test_calculator.py` | Core algorithm with 5 unit tests |
| 3 | `signal_detector.py`, `tests/test_signal_detector.py` | 5-state machine with 7 tests |
| 4 | `data_loader.py` | Load from `trade_etf_daily` |
| 5 | `storage.py` | DDL + upsert to `trade_log_bias_daily` |
| 6 | `report_generator.py` | Markdown report |
| 7 | `run_daily.py` | CLI entry point with argparse |
| 8 | `tests/test_integration.py` | Integration tests |
| 9 | Final verification | All tests + e2e run |
