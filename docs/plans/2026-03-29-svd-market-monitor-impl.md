# SVD 市场状态监控模块 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a production-grade rolling SVD market regime monitor under `data_analyst/market_monitor/` that processes ~5000 A-share stocks across 3 time scales (20/60/120 day windows) with mutation detection, cooldown logic, and industry-neutralization support.

**Architecture:** Pipeline pattern: `data_builder` -> `svd_engine` -> `regime_classifier` -> `storage` -> `visualizer` -> `reporter`. The `SVDMonitor` class in `run_monitor.py` orchestrates the pipeline. Each component is independently testable. Data flows through Pydantic models defined in `schemas.py`.

**Tech Stack:** Python 3.10+, scikit-learn (Randomized SVD), numpy, pandas, scipy (MAD), matplotlib, pydantic, pymysql

**Design doc:** `docs/plans/2026-03-29-svd-market-monitor-design.md`

---

## Task 1: Package skeleton + config + schemas

**Files:**
- Create: `data_analyst/market_monitor/__init__.py`
- Create: `data_analyst/market_monitor/config.py`
- Create: `data_analyst/market_monitor/schemas.py`

**Step 1: Create package directory and `__init__.py`**

```python
# data_analyst/market_monitor/__init__.py
from .run_monitor import SVDMonitor

__all__ = ['SVDMonitor']
```

**Step 2: Create `config.py`**

```python
# -*- coding: utf-8 -*-
"""
SVD 市场监控配置
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SVDMonitorConfig:
    """SVD 市场监控参数配置"""

    # 多尺度窗口配置: {window_size: step}
    windows: Dict[int, int] = field(default_factory=lambda: {
        20: 5,    # 短窗口: 高灵敏, 5日步长
        60: 10,   # 中窗口: 中等灵敏, 10日步长
        120: 20,  # 长窗口: 低滞后, 20日步长
    })

    # Randomized SVD 成分数
    n_components: int = 10

    # 停牌/僵尸股过滤: 窗口期内至少 80% 交易日有效
    min_valid_days_ratio: float = 0.80

    # 最小有效股票数 (低于此数跳过窗口)
    min_stock_count: int = 50

    # 突变检测参数
    mutation_sigma_trigger: float = 2.0     # 触发阈值: 偏离 2σ
    mutation_sigma_release: float = 1.5     # 解除阈值: 回归 1.5σ
    mutation_cooldown_days: int = 3         # 冷却期: 至少持续 3 个交易日

    # 多尺度加权投票权重
    base_weights: Dict[int, float] = field(default_factory=lambda: {
        120: 0.50,
        60: 0.30,
        20: 0.20,
    })

    # 突变触发时权重重分配
    mutation_weights: Dict[int, float] = field(default_factory=lambda: {
        20: 0.50,
        60: 0.20,
        120: 0.30,
    })

    # 市场状态阈值
    state_threshold_high: float = 0.50      # > 50% = 齐涨齐跌
    state_threshold_low: float = 0.35       # < 35% = 个股行情

    # 行业中性化开关 (默认关闭: 监控全市场 Beta 压力)
    industry_neutral: bool = False

    # MAD 去极值参数
    mad_n: float = 3.0  # ±3 中位差截断

    # 输出目录
    output_dir: str = 'output/svd_monitor'
```

**Step 3: Create `schemas.py` with Pydantic models + DDL**

```python
# -*- coding: utf-8 -*-
"""
SVD 市场监控数据模型 + DDL 定义
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


# ============================================================
# DDL
# ============================================================

SVD_MARKET_STATE_DDL = """
CREATE TABLE IF NOT EXISTS trade_svd_market_state (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    calc_date DATE NOT NULL COMMENT '计算日期',
    window_size INT NOT NULL COMMENT '窗口大小',
    top1_var_ratio DOUBLE COMMENT 'Factor1 方差占比',
    top3_var_ratio DOUBLE COMMENT 'Top3 方差占比',
    top5_var_ratio DOUBLE COMMENT 'Top5 方差占比',
    reconstruction_error DOUBLE COMMENT '前5因子重构误差',
    market_state VARCHAR(20) COMMENT '市场状态',
    stock_count INT COMMENT '有效股票数',
    is_mutation TINYINT DEFAULT 0 COMMENT '是否突变警报',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_date_window (calc_date, window_size),
    KEY idx_calc_date (calc_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


# ============================================================
# Pydantic Models
# ============================================================

class WindowSVDResult(BaseModel):
    """单个窗口的 SVD 结果"""
    calc_date: date
    window_size: int
    top1_var_ratio: float
    top3_var_ratio: float
    top5_var_ratio: float
    reconstruction_error: float
    stock_count: int


class MarketRegime(BaseModel):
    """市场状态判定结果"""
    calc_date: date
    market_state: str = Field(description="齐涨齐跌 / 板块分化 / 个股行情")
    is_mutation: bool = False
    final_score: float
    f1_short: Optional[float] = None
    f1_mid: Optional[float] = None
    f1_long: Optional[float] = None
    weights_used: dict = {}


class SVDRecord(WindowSVDResult):
    """数据库记录模型 (继承窗口结果 + 增加状态字段)"""
    market_state: str = ""
    is_mutation: int = 0
```

**Step 4: Commit**

```bash
git add data_analyst/market_monitor/__init__.py data_analyst/market_monitor/config.py data_analyst/market_monitor/schemas.py
git commit -m "feat(svd-monitor): add package skeleton, config, and schemas"
```

---

## Task 2: SVD engine + data builder

**Files:**
- Create: `data_analyst/market_monitor/svd_engine.py`
- Create: `data_analyst/market_monitor/data_builder.py`

**Step 1: Create `svd_engine.py`**

```python
# -*- coding: utf-8 -*-
"""
Randomized SVD 引擎 - 仅提取前 k 个奇异值
"""
import numpy as np
from sklearn.utils.extmath import randomized_svd
from typing import Tuple


def compute_svd(matrix: np.ndarray, n_components: int = 10,
                random_state: int = 42) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Randomized SVD，提取前 n_components 个成分

    Args:
        matrix: 输入矩阵 (stocks x days)，已去均值
        n_components: 提取成分数
        random_state: 随机种子

    Returns:
        U, sigma, Vt
    """
    # 确保没有 NaN/inf
    if np.any(~np.isfinite(matrix)):
        matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)

    # n_components 不能超过矩阵最小维度
    k = min(n_components, min(matrix.shape) - 1)
    if k < 1:
        k = 1

    U, sigma, Vt = randomized_svd(
        matrix, n_components=k, random_state=random_state
    )
    return U, sigma, Vt


def compute_variance_ratios(sigma: np.ndarray) -> dict:
    """
    从奇异值计算方差占比和重构误差

    Args:
        sigma: 奇异值数组

    Returns:
        dict: top1_var_ratio, top3_var_ratio, top5_var_ratio, reconstruction_error
    """
    sigma_sq = sigma ** 2
    total_var = np.sum(sigma_sq)

    if total_var == 0:
        return {
            'top1_var_ratio': 0.0,
            'top3_var_ratio': 0.0,
            'top5_var_ratio': 0.0,
            'reconstruction_error': 1.0,
        }

    top5_var = np.sum(sigma_sq[:min(5, len(sigma_sq))])
    return {
        'top1_var_ratio': float(sigma_sq[0] / total_var),
        'top3_var_ratio': float(np.sum(sigma_sq[:min(3, len(sigma_sq))]) / total_var),
        'top5_var_ratio': float(top5_var / total_var),
        'reconstruction_error': float(1.0 - top5_var / total_var),
    }
```

**Step 2: Create `data_builder.py`**

```python
# -*- coding: utf-8 -*-
"""
收益率矩阵构建 - 数据加载 + 预处理 + 停牌过滤
"""
import sys
import os
import logging
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query
from .config import SVDMonitorConfig

logger = logging.getLogger(__name__)


class DataBuilder:
    """收益率矩阵构建器"""

    def __init__(self, config: SVDMonitorConfig = None):
        self.config = config or SVDMonitorConfig()

    def load_returns(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从数据库加载全 A 股日收益率矩阵

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame: index=trade_date, columns=stock_code, values=close_price
        """
        # 需要额外加载 start_date 之前的数据用于计算首日收益率
        # 估算需要多取 max(windows) 天
        max_window = max(self.config.windows.keys())
        extended_start = self._subtract_trading_days(start_date, max_window + 10)

        sql = """
            SELECT stock_code, trade_date, close_price, volume
            FROM trade_stock_daily
            WHERE trade_date >= %s AND trade_date <= %s
            ORDER BY stock_code, trade_date ASC
        """
        rows = execute_query(sql, [extended_start, end_date])

        if not rows:
            raise ValueError(f"未加载到数据: {extended_start} ~ {end_date}")

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        # Pivot: index=trade_date, columns=stock_code, values=close_price
        price_df = df.pivot(index='trade_date', columns='stock_code', values='close_price')
        price_df = price_df.sort_index()

        # 计算收益率
        returns_df = price_df.pct_change()

        # 处理 inf 值 (涨停/跌停后一字板产生的 inf)
        returns_df = returns_df.replace([np.inf, -np.inf], np.nan)

        # 仅保留目标日期范围
        target_start = pd.Timestamp(start_date)
        returns_df = returns_df.loc[target_start:]

        logger.info(f"加载收益率矩阵: {returns_df.shape[0]} 天 x {returns_df.shape[1]} 只股票")
        return returns_df

    def build_window_matrix(self, returns_df: pd.DataFrame,
                            start_idx: int, window_size: int) -> tuple:
        """
        构建单个窗口的预处理后矩阵

        Args:
            returns_df: 全量收益率 DataFrame
            start_idx: 窗口起始索引
            window_size: 窗口大小

        Returns:
            (processed_matrix, stock_count, valid_stocks)
            processed_matrix: numpy array (stocks x days), 已去均值
            stock_count: 有效股票数
        """
        window_data = returns_df.iloc[start_idx:start_idx + window_size]

        if len(window_data) < window_size:
            return None, 0, []

        # 1. 停牌/僵尸股过滤
        min_valid = int(window_size * self.config.min_valid_days_ratio)
        valid_mask = window_data.notna().sum(axis=0) >= min_valid
        valid_stocks = window_data.columns[valid_mask]

        if len(valid_stocks) < self.config.min_stock_count:
            logger.warning(
                f"窗口有效股票不足: {len(valid_stocks)} < {self.config.min_stock_count}, 跳过"
            )
            return None, 0, []

        window_filtered = window_data[valid_stocks].copy()

        # 2. 停牌日设为 0 (代表无超额波动)
        window_filtered = window_filtered.fillna(0)

        # 3. MAD 去极值 (截面)
        window_filtered = self._mad_winsorize(window_filtered)

        # 4. Z-Score 截面标准化
        window_filtered = self._zscore_cross_section(window_filtered)

        # 5. [可选] 行业中性化
        if self.config.industry_neutral:
            window_filtered = self._industry_neutralize(window_filtered)
            # 中性化后必须重新 Z-Score 标准化
            window_filtered = self._zscore_cross_section(window_filtered)

        # 转置为 (stocks x days) 并去均值
        matrix = window_filtered.values.T  # (stocks, days)
        matrix = matrix - matrix.mean(axis=1, keepdims=True)

        return matrix, len(valid_stocks), list(valid_stocks)

    def _mad_winsorize(self, df: pd.DataFrame) -> pd.DataFrame:
        """MAD 去极值: ±n*MAD 截断"""
        median = df.median(axis=0)
        mad = (df - median).abs().median(axis=0)
        mad = mad.replace(0, 1e-8)  # 防止除零
        upper = median + self.config.mad_n * 1.4826 * mad
        lower = median - self.config.mad_n * 1.4826 * mad
        return df.clip(lower, upper, axis=0)

    def _zscore_cross_section(self, df: pd.DataFrame) -> pd.DataFrame:
        """截面 Z-Score 标准化"""
        mean = df.mean(axis=0)
        std = df.std(axis=0)
        std = std.replace(0, 1e-8)  # 防止除零
        return (df - mean) / std

    def _industry_neutralize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        行业中性化: 申万一级行业哑变量回归取残差

        使用简单方法: 每日截面减去行业均值
        """
        try:
            industry_map = self._load_industry_map()
            if not industry_map:
                logger.warning("行业数据加载失败，跳过行业中性化")
                return df

            # 为每只股票匹配行业
            stocks = df.columns
            industries = pd.Series([industry_map.get(s, 'unknown') for s in stocks],
                                   index=stocks)

            # 每日: 减去同行业均值
            result = df.copy()
            for date in df.index:
                row = df.loc[date]
                for ind_name in industries.unique():
                    if ind_name == 'unknown':
                        continue
                    mask = industries == ind_name
                    ind_stocks = mask[mask].index
                    if len(ind_stocks) < 3:
                        continue
                    ind_mean = row[ind_stocks].mean()
                    result.loc[date, ind_stocks] = row[ind_stocks] - ind_mean

            return result

        except Exception as e:
            logger.warning(f"行业中性化失败: {e}, 跳过")
            return df

    def _load_industry_map(self) -> dict:
        """加载股票-行业映射"""
        try:
            rows = execute_query(
                "SELECT stock_code, industry_name FROM trade_stock_industry"
            )
            return {r['stock_code']: r['industry_name'] for r in rows if r.get('industry_name')}
        except Exception:
            return {}

    def _subtract_trading_days(self, date_str: str, n_days: int) -> str:
        """从日期往前减去约 n_days 个交易日 (粗估: 交易日/自然日 ≈ 5/7)"""
        from datetime import datetime, timedelta
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        natural_days = int(n_days * 7 / 5)
        extended = dt - timedelta(days=natural_days)
        return extended.strftime('%Y-%m-%d')
```

**Step 3: Verify imports work**

```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "from data_analyst.market_monitor.schemas import SVD_MARKET_STATE_DDL, WindowSVDResult; print('schemas OK')"
```

Expected: `schemas OK`

**Step 4: Commit**

```bash
git add data_analyst/market_monitor/svd_engine.py data_analyst/market_monitor/data_builder.py
git commit -m "feat(svd-monitor): add SVD engine and data builder with preprocessing"
```

---

## Task 3: Regime classifier with mutation detection + cooldown

**Files:**
- Create: `data_analyst/market_monitor/regime_classifier.py`

**Step 1: Create `regime_classifier.py`**

```python
# -*- coding: utf-8 -*-
"""
市场状态分类器 - 多尺度综合判定 + 突变警报 + 冷却期
"""
import logging
from datetime import date
from typing import Optional, Tuple, Dict

import pandas as pd
import numpy as np

from .config import SVDMonitorConfig
from .schemas import MarketRegime

logger = logging.getLogger(__name__)


class MutationTracker:
    """突变状态追踪器 (带冷却期)"""

    def __init__(self, config: SVDMonitorConfig):
        self.config = config
        self._active = False           # 当前是否处于突变状态
        self._trigger_count = 0        # 连续触发计数

    def update(self, is_triggered: bool) -> bool:
        """
        更新突变状态，考虑冷却期逻辑

        Args:
            is_triggered: 本次是否检测到突变信号

        Returns:
            当前是否应使用突变权重
        """
        if is_triggered:
            self._active = True
            self._trigger_count += 1
            return True

        if self._active:
            self._trigger_count += 1
            # 冷却期内: 即使信号消失也保持突变状态
            if self._trigger_count < self.config.mutation_cooldown_days:
                return True
            else:
                self._active = False
                self._trigger_count = 0
                return False

        return False

    @property
    def is_active(self) -> bool:
        return self._active

    def reset(self):
        self._active = False
        self._trigger_count = 0


class RegimeClassifier:
    """市场状态分类器"""

    def __init__(self, config: SVDMonitorConfig = None):
        self.config = config or SVDMonitorConfig()
        self.mutation_tracker = MutationTracker(self.config)

    def detect_mutation(self, f1_short: float, f1_long: float,
                        long_history: pd.Series) -> Tuple[bool, float]:
        """
        突变检测: 短窗口 F1 偏离长窗口历史分布 2σ 以上

        Args:
            f1_short: 短窗口当前 F1
            f1_long: 长窗口当前 F1
            long_history: 长窗口历史 F1 序列

        Returns:
            (is_triggered, deviation_sigma)
        """
        if len(long_history) < 10:
            return False, 0.0

        hist_mean = long_history.mean()
        hist_std = long_history.std()

        if hist_std < 1e-8:
            return False, 0.0

        deviation = (f1_short - hist_mean) / hist_std

        if abs(deviation) > self.config.mutation_sigma_trigger:
            return True, abs(deviation)

        return False, abs(deviation)

    def classify(self, results_df: pd.DataFrame, calc_date: date) -> MarketRegime:
        """
        多尺度综合判定市场状态

        Args:
            results_df: 所有窗口的 SVD 结果 DataFrame
                        必须包含列: calc_date, window_size, top1_var_ratio
            calc_date: 当前计算日期

        Returns:
            MarketRegime 判定结果
        """
        # 提取各尺度当前值
        f1_values = {}
        for ws in self.config.windows.keys():
            subset = results_df[
                (results_df['window_size'] == ws) &
                (results_df['calc_date'] == calc_date)
            ]
            if len(subset) > 0:
                f1_values[ws] = subset['top1_var_ratio'].iloc[-1]

        # 如果某些窗口没有数据，用 None 填充
        f1_short = f1_values.get(20)
        f1_mid = f1_values.get(60)
        f1_long = f1_values.get(120)

        # 如果长窗口数据不足，使用可用的最长窗口
        available_windows = [w for w in [20, 60, 120] if f1_values.get(w) is not None]

        if not available_windows:
            return MarketRegime(
                calc_date=calc_date,
                market_state="数据不足",
                is_mutation=False,
                final_score=0.0,
                weights_used={},
            )

        # 突变检测 (需要长窗口历史)
        is_mutation = False
        if f1_short is not None and f1_long is not None:
            long_hist = results_df[
                (results_df['window_size'] == 120) &
                (results_df['calc_date'] < calc_date)
            ]['top1_var_ratio']

            if len(long_hist) >= 10:
                triggered, deviation = self.detect_mutation(f1_short, f1_long, long_hist)
                is_mutation = self.mutation_tracker.update(triggered)
                if triggered:
                    logger.info(f"突变信号: deviation={deviation:.2f}σ, active={is_mutation}")

        # 动态权重分配
        weights = self.config.base_weights.copy()
        if is_mutation:
            weights = self.config.mutation_weights.copy()

        # 加权得分
        final_score = 0.0
        weight_sum = 0.0
        for ws in [20, 60, 120]:
            if f1_values.get(ws) is not None and ws in weights:
                final_score += f1_values[ws] * weights[ws]
                weight_sum += weights[ws]

        if weight_sum > 0:
            final_score /= weight_sum

        # 状态判定
        if final_score > self.config.state_threshold_high:
            state = "齐涨齐跌"
        elif final_score > self.config.state_threshold_low:
            state = "板块分化"
        else:
            state = "个股行情"

        return MarketRegime(
            calc_date=calc_date,
            market_state=state,
            is_mutation=is_mutation,
            final_score=round(final_score, 4),
            f1_short=round(f1_short, 4) if f1_short is not None else None,
            f1_mid=round(f1_mid, 4) if f1_mid is not None else None,
            f1_long=round(f1_long, 4) if f1_long is not None else None,
            weights_used=weights,
        )

    def reset_mutation(self):
        """重置突变追踪器"""
        self.mutation_tracker.reset()
```

**Step 2: Commit**

```bash
git add data_analyst/market_monitor/regime_classifier.py
git commit -m "feat(svd-monitor): add regime classifier with mutation detection and cooldown"
```

---

## Task 4: Storage layer (database CRUD)

**Files:**
- Create: `data_analyst/market_monitor/storage.py`

**Step 1: Create `storage.py`**

```python
# -*- coding: utf-8 -*-
"""
SVD 市场状态存储层 - 数据库读写
"""
import logging
from datetime import date
from typing import List, Optional

from config.db import execute_query, get_connection, execute_update
from .schemas import SVD_MARKET_STATE_DDL, SVDRecord, WindowSVDResult, MarketRegime

logger = logging.getLogger(__name__)

# INSERT/UPDATE SQL (幂等: ON DUPLICATE KEY UPDATE)
UPSERT_SQL = """
INSERT INTO trade_svd_market_state
    (calc_date, window_size, top1_var_ratio, top3_var_ratio, top5_var_ratio,
     reconstruction_error, market_state, stock_count, is_mutation)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    top1_var_ratio = VALUES(top1_var_ratio),
    top3_var_ratio = VALUES(top3_var_ratio),
    top5_var_ratio = VALUES(top5_var_ratio),
    reconstruction_error = VALUES(reconstruction_error),
    market_state = VALUES(market_state),
    stock_count = VALUES(stock_count),
    is_mutation = VALUES(is_mutation)
"""


class SVDStorage:
    """SVD 市场状态存储"""

    @staticmethod
    def init_table():
        """初始化表结构"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(SVD_MARKET_STATE_DDL)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("trade_svd_market_state 表已初始化")

    @staticmethod
    def save_record(record: SVDRecord):
        """保存单条记录 (幂等)"""
        execute_update(UPSERT_SQL, [
            record.calc_date, record.window_size,
            record.top1_var_ratio, record.top3_var_ratio, record.top5_var_ratio,
            record.reconstruction_error, record.market_state,
            record.stock_count, record.is_mutation,
        ])

    @staticmethod
    def save_batch(records: List[SVDRecord]):
        """批量保存记录"""
        if not records:
            return
        conn = get_connection()
        cursor = conn.cursor()
        for record in records:
            cursor.execute(UPSERT_SQL, [
                record.calc_date, record.window_size,
                record.top1_var_ratio, record.top3_var_ratio, record.top5_var_ratio,
                record.reconstruction_error, record.market_state,
                record.stock_count, record.is_mutation,
            ])
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"批量保存 {len(records)} 条 SVD 记录")

    @staticmethod
    def load_results(start_date: str = None, end_date: str = None) -> list:
        """
        加载 SVD 结果

        Args:
            start_date: 可选开始日期
            end_date: 可选结束日期

        Returns:
            list of dict
        """
        sql = "SELECT * FROM trade_svd_market_state WHERE 1=1"
        params = []

        if start_date:
            sql += " AND calc_date >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND calc_date <= %s"
            params.append(end_date)

        sql += " ORDER BY calc_date ASC, window_size ASC"

        return execute_query(sql, params or ())

    @staticmethod
    def get_latest_state(window_size: int = 120) -> Optional[dict]:
        """获取指定窗口的最新市场状态"""
        rows = execute_query(
            "SELECT * FROM trade_svd_market_state "
            "WHERE window_size = %s ORDER BY calc_date DESC LIMIT 1",
            [window_size]
        )
        return rows[0] if rows else None
```

**Step 2: Commit**

```bash
git add data_analyst/market_monitor/storage.py
git commit -m "feat(svd-monitor): add storage layer with idempotent upsert"
```

---

## Task 5: Visualizer

**Files:**
- Create: `data_analyst/market_monitor/visualizer.py`

**Step 1: Create `visualizer.py`**

```python
# -*- coding: utf-8 -*-
"""
SVD 市场状态可视化 - 多尺度叠加图 + 解释度视角
"""
import os
import logging
import platform

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Polygon

# 中文字体配置
if platform.system() == "Darwin":
    matplotlib.rcParams['font.family'] = ["Heiti TC", "STHeiti", "Arial Unicode MS", "sans-serif"]
elif platform.system() == "Windows":
    matplotlib.rcParams['font.family'] = ["SimHei", "Microsoft YaHei", "sans-serif"]
else:
    matplotlib.rcParams['font.family'] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
matplotlib.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


# 状态颜色映射
STATE_COLORS = {
    '齐涨齐跌': '#e74c3c',
    '板块分化': '#f39c12',
    '个股行情': '#27ae60',
}


def plot_regime_chart(results_df: pd.DataFrame, regimes: list,
                      output_path: str = None, output_dir: str = 'output/svd_monitor'):
    """
    绘制多尺度市场状态监控图

    上半区: F1 方差占比 (三窗口 + 综合线 + 阈值线 + 突变标记)
    下半区: Top1/Top3/Top5 累计解释度

    Args:
        results_df: SVD 结果 DataFrame (columns: calc_date, window_size, top1_var_ratio, top3_var_ratio, top5_var_ratio)
        regimes: MarketRegime 列表
        output_path: 可选指定输出路径
        output_dir: 输出目录

    Returns:
        chart_path: 图表路径
    """
    if results_df.empty:
        logger.warning("无数据，跳过可视化")
        return None

    os.makedirs(output_dir, exist_ok=True)
    if output_path is None:
        output_path = os.path.join(output_dir, 'svd_market_regime.png')

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), height_ratios=[3, 2],
                                     sharex=True)

    # 准备数据
    results_df['calc_date'] = pd.to_datetime(results_df['calc_date'])

    # ---- 上半区: F1 方差占比 ----
    window_styles = {
        20: {'color': '#3498db', 'alpha': 0.3, 'linewidth': 1, 'label': '20日窗口'},
        60: {'color': '#9b59b6', 'alpha': 0.5, 'linewidth': 1.5, 'label': '60日窗口'},
        120: {'color': '#e74c3c', 'alpha': 0.8, 'linewidth': 2.5, 'label': '120日窗口'},
    }

    for ws, style in window_styles.items():
        subset = results_df[results_df['window_size'] == ws].sort_values('calc_date')
        if subset.empty:
            continue
        ax1.fill_between(subset['calc_date'], subset['top1_var_ratio'] * 100,
                         alpha=style['alpha'], color=style['color'])
        ax1.plot(subset['calc_date'], subset['top1_var_ratio'] * 100,
                 color=style['color'], linewidth=style['linewidth'], label=style['label'])

    # 综合状态线
    if regimes:
        regime_df = pd.DataFrame([r.model_dump() for r in regimes])
        regime_df['calc_date'] = pd.to_datetime(regime_df['calc_date'])
        regime_df = regime_df.sort_values('calc_date')
        ax1.plot(regime_df['calc_date'], regime_df['final_score'] * 100,
                 color='#2c3e50', linewidth=2, linestyle='-', label='综合得分')

        # 突变标记
        mutations = regime_df[regime_df['is_mutation'] == True]
        if not mutations.empty:
            ax1.scatter(mutations['calc_date'], mutations['final_score'] * 100,
                        color='red', marker='^', s=100, zorder=5, label='突变警报')

    # 阈值线
    ax1.axhline(y=50, color='red', linestyle='--', alpha=0.5, linewidth=1)
    ax1.axhline(y=35, color='green', linestyle='--', alpha=0.5, linewidth=1)

    # 背景色块
    ylim = ax1.get_ylim()
    ax1.axhspan(50, ylim[1], alpha=0.05, color='red')
    ax1.axhspan(35, 50, alpha=0.05, color='orange')
    ax1.axhspan(ylim[0], 35, alpha=0.05, color='green')

    ax1.set_ylabel('Factor 1 方差占比 (%)', fontsize=12)
    ax1.set_title('滚动 SVD 市场状态监控', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=9, loc='upper right', ncol=3)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, max(80, ax1.get_ylim()[1]))

    # ---- 下半区: 解释度视角 ----
    for ws in [120]:  # 用长窗口展示解释度
        subset = results_df[results_df['window_size'] == ws].sort_values('calc_date')
        if subset.empty:
            continue
        ax2.fill_between(subset['calc_date'], subset['top5_var_ratio'] * 100,
                         alpha=0.1, color='gray')
        ax2.plot(subset['calc_date'], subset['top1_var_ratio'] * 100,
                 color='#e74c3c', linewidth=2, label='Top 1')
        ax2.plot(subset['calc_date'], subset['top3_var_ratio'] * 100,
                 color='#3498db', linewidth=1.5, label='Top 3')
        ax2.plot(subset['calc_date'], subset['top5_var_ratio'] * 100,
                 color='#95a5a6', linewidth=1, linestyle='--', label='Top 5')

    ax2.set_xlabel('日期', fontsize=12)
    ax2.set_ylabel('累计解释度 (%)', fontsize=12)
    ax2.set_title('因子解释度分布 (120日窗口)', fontsize=12)
    ax2.legend(fontsize=9, loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 100)

    # X 轴日期格式
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    fig.autofmt_xdate()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    logger.info(f"图表已保存: {output_path}")
    return output_path
```

**Step 2: Commit**

```bash
git add data_analyst/market_monitor/visualizer.py
git commit -m "feat(svd-monitor): add multi-scale visualization with explained variance view"
```

---

## Task 6: Reporter

**Files:**
- Create: `data_analyst/market_monitor/reporter.py`

**Step 1: Create `reporter.py`**

```python
# -*- coding: utf-8 -*-
"""
SVD 市场状态 Markdown 报告生成
"""
import os
import logging
from datetime import date
from typing import List, Optional

import pandas as pd

from .schemas import MarketRegime, WindowSVDResult

logger = logging.getLogger(__name__)


# 策略建议映射
ADVICE_MAP = {
    '齐涨齐跌': (
        '当前市场齐涨齐跌特征明显，Beta 因子主导。\n'
        '- **建议**: 指数增强策略更有效，个股选择的 alpha 空间有限\n'
        '- **操作**: 可考虑增大仓位跟随大盘趋势，减少个股博弈\n'
        '- **风险**: 板块普跌时需注意系统性风险'
    ),
    '板块分化': (
        '当前市场处于板块分化阶段，行业轮动特征显著。\n'
        '- **建议**: 行业配置是关键，选对板块比选对个股更重要\n'
        '- **操作**: 关注行业动量因子，超配强势板块\n'
        '- **风险**: 轮动速度过快时容易被两头打脸'
    ),
    '个股行情': (
        '当前市场个股分化明显，Alpha 机会丰富。\n'
        '- **建议**: 选股策略更有效，多因子模型价值凸显\n'
        '- **操作**: 精选个股，降低对大盘方向的依赖\n'
        '- **风险**: 需要更严格的风控和止损'
    ),
}


def generate_report(regime: MarketRegime, results_df: pd.DataFrame,
                    chart_path: Optional[str] = None,
                    output_dir: str = 'output/svd_monitor') -> str:
    """
    生成 Markdown 报告

    Args:
        regime: 当前市场状态
        results_df: SVD 结果 DataFrame
        chart_path: 图表路径
        output_dir: 输出目录

    Returns:
        report_path: 报告路径
    """
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"svd_report_{regime.calc_date}.md")

    lines = []
    lines.append(f"# SVD 市场状态监控报告")
    lines.append(f"\n**日期**: {regime.calc_date}")
    lines.append(f"**市场状态**: {regime.market_state}")
    lines.append(f"**综合得分**: {regime.final_score:.1%}")
    lines.append(f"**突变警报**: {'是' if regime.is_mutation else '否'}")
    lines.append("")

    # 多尺度明细
    lines.append("## 多尺度因子集中度")
    lines.append("")
    lines.append("| 窗口 | F1 占比 | 权重 |")
    lines.append("|------|---------|------|")
    for ws, weight in regime.weights_used.items():
        f1 = getattr(regime, f'f1_{_ws_label(ws)}', 'N/A')
        if f1 is not None:
            lines.append(f"| {ws}日 | {f1:.1%} | {weight:.0%} |")
    lines.append("")

    # 策略建议
    lines.append("## 策略建议")
    lines.append("")
    advice = ADVICE_MAP.get(regime.market_state, '数据不足，无法给出建议。')
    lines.append(advice)
    lines.append("")

    # 突变警报说明
    if regime.is_mutation:
        lines.append("## 突变警报")
        lines.append("")
        lines.append("> 当前市场结构发生剧烈变化，短窗口指标偏离长期均值 2σ 以上。")
        lines.append("> 建议: 降低仓位，观察市场方向，等待结构稳定后再入场。")
        lines.append("")

    # 图表
    if chart_path and os.path.exists(chart_path):
        lines.append("## 市场状态图")
        lines.append("")
        lines.append(f"![SVD 市场状态]({chart_path})")
        lines.append("")

    # 历史状态变化 (最近 30 天)
    lines.append("## 近期状态变化")
    lines.append("")
    recent = results_df[results_df['window_size'] == 120].tail(30)
    if not recent.empty:
        lines.append("| 日期 | F1 占比 | Top3 占比 | 重构误差 | 股票数 |")
        lines.append("|------|---------|----------|---------|--------|")
        for _, row in recent.iterrows():
            lines.append(
                f"| {row['calc_date']} | {row['top1_var_ratio']:.1%} | "
                f"{row['top3_var_ratio']:.1%} | {row['reconstruction_error']:.1%} | "
                f"{row['stock_count']} |"
            )
    lines.append("")

    report_text = "\n".join(lines)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    logger.info(f"报告已保存: {report_path}")
    return report_path


def _ws_label(ws: int) -> str:
    """窗口大小转标签"""
    return {20: 'short', 60: 'mid', 120: 'long'}.get(ws, str(ws))
```

**Step 2: Commit**

```bash
git add data_analyst/market_monitor/reporter.py
git commit -m "feat(svd-monitor): add Markdown report generator"
```

---

## Task 7: SVDMonitor orchestrator + CLI entry point

**Files:**
- Create: `data_analyst/market_monitor/run_monitor.py`
- Modify: `data_analyst/market_monitor/__init__.py`

**Step 1: Create `run_monitor.py`**

```python
# -*- coding: utf-8 -*-
"""
SVD 市场状态监控 - 主入口

支持:
  1. CLI 手动运行: python -m data_analyst.market_monitor.run_monitor --latest
  2. 编程调用: SVDMonitor().run(start_date, end_date)
  3. 定时调度: run_daily_monitor()
"""
import sys
import os
import argparse
import logging
from datetime import date, datetime, timedelta
from time import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from .config import SVDMonitorConfig
from .schemas import SVDRecord, MarketRegime
from .data_builder import DataBuilder
from .svd_engine import compute_svd, compute_variance_ratios
from .regime_classifier import RegimeClassifier
from .storage import SVDStorage
from .visualizer import plot_regime_chart
from .reporter import generate_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SVDMonitor:
    """SVD 市场状态监控器"""

    def __init__(self, config: SVDMonitorConfig = None):
        self.config = config or SVDMonitorConfig()
        self.data_builder = DataBuilder(self.config)
        self.classifier = RegimeClassifier(self.config)
        self.storage = SVDStorage

    def run(self, start_date: str, end_date: str = None,
            save_db: bool = True, generate_chart: bool = True,
            generate_report: bool = True) -> dict:
        """
        运行 SVD 市场监控

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD), 默认为今天
            save_db: 是否保存到数据库
            generate_chart: 是否生成图表
            generate_report: 是否生成报告

        Returns:
            dict: {records, regimes, chart_path, report_path}
        """
        if end_date is None:
            end_date = date.today().strftime('%Y-%m-%d')

        logger.info(f"=" * 60)
        logger.info(f"SVD 市场监控: {start_date} ~ {end_date}")
        logger.info(f"窗口配置: {self.config.windows}")
        logger.info(f"行业中性化: {self.config.industry_neutral}")
        logger.info(f"=" * 60)

        t0 = time()

        # 1. 初始化数据库
        if save_db:
            self.storage.init_table()

        # 2. 加载收益率数据
        logger.info("[1/5] 加载收益率数据...")
        returns_df = self.data_builder.load_returns(start_date, end_date)

        if returns_df.empty or len(returns_df) < max(self.config.windows.keys()):
            logger.error("数据不足，退出")
            return {'records': [], 'regimes': [], 'chart_path': None, 'report_path': None}

        # 3. 滚动窗口 SVD
        logger.info("[2/5] 滚动窗口 SVD 计算...")
        all_records = []
        T = len(returns_df)

        for window_size, step in self.config.windows.items():
            window_records = []
            for start_idx in range(0, T - window_size, step):
                mid_idx = start_idx + window_size // 2
                mid_date = returns_df.index[mid_idx]
                calc_date = mid_date.date() if hasattr(mid_date, 'date') else mid_date

                matrix, stock_count, _ = self.data_builder.build_window_matrix(
                    returns_df, start_idx, window_size
                )

                if matrix is None:
                    continue

                # SVD
                _, sigma, _ = compute_svd(matrix, self.config.n_components)
                ratios = compute_variance_ratios(sigma)

                record = SVDRecord(
                    calc_date=calc_date,
                    window_size=window_size,
                    top1_var_ratio=ratios['top1_var_ratio'],
                    top3_var_ratio=ratios['top3_var_ratio'],
                    top5_var_ratio=ratios['top5_var_ratio'],
                    reconstruction_error=ratios['reconstruction_error'],
                    stock_count=stock_count,
                    market_state="",  # 后续填充
                    is_mutation=0,
                )
                window_records.append(record)

            all_records.extend(window_records)
            logger.info(f"  窗口 {window_size}日: {len(window_records)} 个计算点")

        if not all_records:
            logger.error("无有效 SVD 结果")
            return {'records': [], 'regimes': [], 'chart_path': None, 'report_path': None}

        # 4. 市场状态分类
        logger.info("[3/5] 市场状态分类...")
        results_df = pd.DataFrame([r.model_dump() for r in all_records])
        unique_dates = sorted(results_df['calc_date'].unique())
        regimes = []

        for calc_date in unique_dates:
            regime = self.classifier.classify(results_df, calc_date)
            regimes.append(regime)

            # 回填 market_state 和 is_mutation 到 records
            for r in all_records:
                if r.calc_date == calc_date:
                    r.market_state = regime.market_state
                    r.is_mutation = 1 if regime.is_mutation else 0

        latest_regime = regimes[-1] if regimes else None
        if latest_regime:
            logger.info(f"  最新状态: {latest_regime.market_state} "
                        f"(score={latest_regime.final_score:.1%}, "
                        f"mutation={latest_regime.is_mutation})")

        # 5. 保存 + 可视化 + 报告
        chart_path = None
        report_path = None

        if save_db:
            logger.info("[4/5] 保存到数据库...")
            self.storage.save_batch(all_records)
            logger.info(f"  保存 {len(all_records)} 条记录")

        if generate_chart:
            logger.info("[5/5] 生成图表...")
            chart_path = plot_regime_chart(
                results_df, regimes,
                output_dir=self.config.output_dir
            )

        if generate_report and latest_regime:
            report_path = generate_report(
                latest_regime, results_df, chart_path,
                output_dir=self.config.output_dir
            )

        elapsed = time() - t0
        logger.info(f"=" * 60)
        logger.info(f"完成! 耗时 {elapsed:.1f}s")
        logger.info(f"图表: {chart_path}")
        logger.info(f"报告: {report_path}")
        logger.info(f"=" * 60)

        return {
            'records': all_records,
            'regimes': regimes,
            'chart_path': chart_path,
            'report_path': report_path,
        }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='SVD 市场状态监控')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--latest', action='store_true', help='仅计算最新一天')
    parser.add_argument('--backfill-days', type=int, default=365,
                        help='回填天数 (默认 365)')
    parser.add_argument('--no-db', action='store_true', help='不保存数据库')
    parser.add_argument('--no-chart', action='store_true', help='不生成图表')
    parser.add_argument('--industry-neutral', action='store_true',
                        help='开启行业中性化')

    args = parser.parse_args()

    config = SVDMonitorConfig()
    if args.industry_neutral:
        config.industry_neutral = True

    monitor = SVDMonitor(config)

    if args.latest:
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=config.backfill_days)).strftime('%Y-%m-%d')
    elif args.start:
        start_date = args.start
        end_date = args.end or date.today().strftime('%Y-%m-%d')
    else:
        # 默认: 最近一年
        end_date = date.today().strftime('%Y-%m-%d')
        start_date = (date.today() - timedelta(days=config.backfill_days)).strftime('%Y-%m-%d')

    monitor.run(
        start_date=start_date,
        end_date=end_date,
        save_db=not args.no_db,
        generate_chart=not args.no_chart,
    )


def run_daily_monitor():
    """供 scheduler_service 调用的每日监控入口"""
    config = SVDMonitorConfig()
    monitor = SVDMonitor(config)

    end_date = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=400)).strftime('%Y-%m-%d')

    result = monitor.run(start_date=start_date, end_date=end_date)

    # 如果检测到突变，可以在这里触发飞书报警
    if result['regimes']:
        latest = result['regimes'][-1]
        if latest.is_mutation:
            logger.warning(f"突变警报! 市场状态: {latest.market_state}, "
                           f"综合得分: {latest.final_score:.1%}")
            try:
                from data_analyst.services.alert_service import AlertService
                alert = AlertService()
                alert.send_text(
                    f"SVD 突变警报\n"
                    f"市场状态: {latest.market_state}\n"
                    f"综合得分: {latest.final_score:.1%}\n"
                    f"请关注市场风险!"
                )
            except Exception as e:
                logger.warning(f"发送报警失败: {e}")


if __name__ == '__main__':
    main()
```

**Step 2: Update `__init__.py`**

```python
# data_analyst/market_monitor/__init__.py
from .run_monitor import SVDMonitor, run_daily_monitor

__all__ = ['SVDMonitor', 'run_daily_monitor']
```

**Step 3: Verify module imports**

```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "from data_analyst.market_monitor import SVDMonitor; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add data_analyst/market_monitor/
git commit -m "feat(svd-monitor): add SVDMonitor orchestrator with CLI and scheduler integration"
```

---

## Task 8: Integration - update scheduler_service + CLAUDE.md

**Files:**
- Modify: `data_analyst/services/scheduler_service.py:196-214` (add SVD monitor job)
- Modify: `CLAUDE.md` (add module documentation)

**Step 1: Add SVD monitor to scheduler_service**

In `data_analyst/services/scheduler_service.py`, modify the `init_scheduler()` function to add the SVD monitor job at 18:30 (after data check at 18:00):

```python
def init_scheduler():
    """初始化定时任务"""
    # 创建服务实例
    alert_service = AlertService()
    scheduler = SchedulerService()
    scheduler.set_alert_service(alert_service)

    # 添加每日 18:00 数据检查任务
    scheduler.add_daily_job(
        func=check_data_and_trigger_factor,
        hour=18,
        minute=0,
        job_id='daily_data_check'
    )

    # 添加每日 18:30 SVD 市场状态监控
    scheduler.add_daily_job(
        func=run_svd_monitor,
        hour=18,
        minute=30,
        job_id='daily_svd_monitor'
    )

    logger.info("定时任务初始化完成")
    return scheduler


def run_svd_monitor():
    """SVD 市场状态监控任务"""
    try:
        from data_analyst.market_monitor.run_monitor import run_daily_monitor
        run_daily_monitor()
    except Exception as e:
        logger.error(f"SVD 市场监控失败: {e}")
```

**Step 2: Add to CLAUDE.md**

In the CLAUDE.md file, under the `strategist/xgboost_strategy/` section, add a new section:

```markdown
## SVD 市场状态监控

### 2026-03-29 新增模块

基于滚动 SVD 分解全 A 股收益率矩阵，监控市场因子结构变化。

**核心特性**：
- **多尺度窗口** - 20日/60日/120日三窗口并行监控
- **Randomized SVD** - 仅提取前 10 成分，极速计算
- **突变检测** - 短窗口偏离 2σ 自动触发警报 + 3 日冷却期
- **行业中性化** - 可选开关，适配择时/选股不同场景
- **重构误差** - Top5 因子解释不了的部分 = 市场混沌度

**快速开始**：
```bash
# 仅计算最新状态
python -m data_analyst.market_monitor.run_monitor --latest

# 回填历史数据
python -m data_analyst.market_monitor.run_monitor --start 2025-01-01 --end 2026-03-28

# 开启行业中性化
python -m data_analyst.market_monitor.run_monitor --latest --industry-neutral
```

**输出结果**：
- `output/svd_monitor/svd_market_regime.png` - 多尺度监控图
- `output/svd_monitor/svd_report_YYYY-MM-DD.md` - 每日报告
- 数据库表 `trade_svd_market_state` - 历史数据
```

**Step 3: Commit**

```bash
git add data_analyst/services/scheduler_service.py CLAUDE.md
git commit -m "feat(svd-monitor): integrate with scheduler service and update docs"
```

---

## Task 9: End-to-end smoke test

**Step 1: Run the monitor with `--no-db` to verify the pipeline**

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m data_analyst.market_monitor.run_monitor --start 2025-06-01 --end 2025-12-31 --no-db
```

Expected output:
- Data loading: ~5000 stocks x ~150 trading days
- Rolling SVD: 3 windows, each with multiple calculation points
- Final regime classification
- Chart saved to `output/svd_monitor/svd_market_regime.png`

**Step 2: If successful, run with database**

```bash
cd /Users/zhaobo/data0/person/myTrader && python -m data_analyst.market_monitor.run_monitor --latest
```

**Step 3: Verify database records**

```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "
from data_analyst.market_monitor.storage import SVDStorage
rows = SVDStorage.load_results()
print(f'Total records: {len(rows)}')
if rows:
    print(f'Latest: {rows[-1]}')
"
```

**Step 4: Fix any issues found during testing**

Debug any import errors, SQL issues, or data issues. Common issues to watch for:
- `from config.settings import settings` in scheduler_service.py (this import may fail)
- Database connection issues
- Insufficient data for some windows
- matplotlib font issues on the current platform

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(svd-monitor): address issues found during smoke test"
```

---

## Summary

| Task | Component | Key Files | Est. Time |
|------|-----------|-----------|-----------|
| 1 | Package skeleton | `__init__.py`, `config.py`, `schemas.py` | 3 min |
| 2 | SVD engine + data builder | `svd_engine.py`, `data_builder.py` | 5 min |
| 3 | Regime classifier | `regime_classifier.py` | 4 min |
| 4 | Storage layer | `storage.py` | 3 min |
| 5 | Visualizer | `visualizer.py` | 5 min |
| 6 | Reporter | `reporter.py` | 3 min |
| 7 | Orchestrator + CLI | `run_monitor.py` | 5 min |
| 8 | Integration | `scheduler_service.py`, `CLAUDE.md` | 3 min |
| 9 | Smoke test | E2E verification | 5 min |

**Total: ~9 commits, ~36 minutes**
