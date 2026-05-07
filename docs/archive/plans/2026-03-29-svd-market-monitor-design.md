# SVD 滚动市场状态监控模块 - 设计文档

> 日期: 2026-03-29
> 模块位置: `data_analyst/market_monitor/`
> 参考: `CASE-QuantStats绩效分析与报告/2-SVD因子挖掘与分析.py`, `4-实盘交易绩效分析Plus.py`

---

## 1. 目标

通过滚动 SVD 分解全 A 股收益率矩阵，实时监控市场因子结构变化，为策略师模块提供市场状态信号（择时/选股环境判断）。

## 2. 目录结构

```
data_analyst/
└── market_monitor/
    ├── __init__.py              # 导出 SVDMonitor 主类
    ├── config.py                # 参数配置 + 中性化开关
    ├── schemas.py               # Pydantic 数据模型 + DDL 定义
    ├── data_builder.py          # 收益率矩阵构建 + 停牌过滤 + 预处理
    ├── svd_engine.py            # Randomized SVD 引擎 (k=10)
    ├── regime_classifier.py     # 多尺度综合分类 + 突变警报 + 冷却期
    ├── storage.py               # 数据库读写层 (trade_svd_market_state)
    ├── visualizer.py            # 多尺度叠加可视化 + 解释度视角
    ├── reporter.py              # Markdown 报告生成
    └── run_monitor.py           # CLI 入口 + scheduler 集成
```

## 3. 核心算法

### 3.1 多尺度滚动窗口

| 窗口 | 灵敏度 | 步长 | 用途 |
|------|--------|------|------|
| 20 日 | 高 | 5 日 | 短期情绪变化 |
| 60 日 | 中 | 10 日 | 中期趋势确认 |
| 120 日 | 低 | 20 日 | 长期状态判断 |

### 3.2 Randomized SVD (svd_engine.py)

使用 `sklearn.utils.extmath.randomized_svd`，仅提取前 10 个成分。

```python
from sklearn.utils.extmath import randomized_svd

def compute_svd(matrix, n_components=10, random_state=42):
    U, sigma, Vt = randomized_svd(matrix, n_components=n_components, random_state=random_state)
    return U, sigma, Vt
```

性能预估 (5000x120 矩阵):

| 方法 | 耗时 | F1 精度 |
|------|------|---------|
| numpy.linalg.svd (全秩) | ~2s | 精确 |
| Randomized SVD (k=10) | ~0.05s | 误差 < 0.1% |

3 窗口 x ~10 步 = 30 次 SVD，总耗时约 1.5s，可每日运行。

### 3.3 市场状态分类 (regime_classifier.py)

**常规加权投票**:
```
base_weights = {120: 0.50, 60: 0.30, 20: 0.20}
```

**突变检测**:
- 短窗口 F1 偏离长窗口历史分布 2σ 以上时触发
- 触发后权重重分配: `{20: 0.50, 60: 0.20, 120: 0.30}`

**突变冷却期**:
- 触发后权重调整至少持续 3 个交易日
- 直到短窗口 F1 回归到 1.5σ 以内才解除警报

**状态标签**:

| 状态 | 条件 | 含义 | 策略建议 |
|------|------|------|----------|
| 齐涨齐跌 | F1 > 50% | Beta 主导 | 指数增强，减少选股 |
| 板块分化 | F1 35%-50% | 行业轮动 | 行业配置是关键 |
| 个股行情 | F1 < 35% | Alpha 丰富 | 多因子选股，精选个股 |
| 突变警报 | 短窗口偏离 2σ | 市场结构剧变 | 降低仓位，观察 |

**核心判定伪代码**:

```python
def classify_market_regime(results_df, config):
    f1_short = results_df.query("window_size == 20")['top1_var_ratio'].iloc[-1]
    f1_mid   = results_df.query("window_size == 60")['top1_var_ratio'].iloc[-1]
    f1_long  = results_df.query("window_size == 120")['top1_var_ratio'].iloc[-1]

    long_hist = results_df.query("window_size == 120")['top1_var_ratio']
    is_mutation, _ = detect_mutation(f1_short, f1_long, long_hist)

    weights = config.base_weights.copy()
    if is_mutation:
        weights = {20: 0.50, 60: 0.20, 120: 0.30}

    final_score = f1_short * weights[20] + f1_mid * weights[60] + f1_long * weights[120]

    if final_score > 0.50:
        state = "齐涨齐跌"
    elif final_score > 0.35:
        state = "板块分化"
    else:
        state = "个股行情"

    return state, is_mutation, final_score
```

## 4. 数据预处理 (data_builder.py)

### 4.1 停牌/僵尸股过滤

```python
MIN_VALID_DAYS_RATIO = 0.80  # 窗口期内至少 80% 交易日有效

# 对每只股票:
valid_count = stock_returns.notna().sum()
if valid_count < window * MIN_VALID_DAYS_RATIO:
    剔除该股票  # 不参与本窗口 SVD
```

**停牌日处理**: 设为 0（代表无超额波动），不使用均值填充（均值填充会人为制造相关性，导致 F1 虚高）。

### 4.2 标准化流程

```
原始收益率矩阵
  → 计算 pct_change()
  → 处理 inf 值（设为 NaN）
  → 剔除低活跃股票 (min_valid_days_ratio < 0.80)
  → 停牌日设为 0
  → MAD 去极值 (±3 中位差截断)
  → [可选] 行业中性化 (行业哑变量回归取残差)
  → [行业中性化后] 重新 Z-Score 截面标准化
  → Z-Score 截面标准化
```

### 4.3 行业中性化开关 (config.py)

```python
INDUSTRY_NEUTRAL = False  # 默认关闭

# 关闭: 监控全市场 Beta 压力（适合择时）
# 开启: 监控市场真正的结构化强度（适合 Alpha 选股环境判断）
```

中性化方法: 对每日截面，用申万一级行业哑变量回归取残差。残差必须重新 Z-Score 标准化（因为不同交易日残差方差可能差异很大，不重新标准化会导致高波动交易日过度主导 SVD 结果）。

## 5. 数据库设计 (schemas.py + storage.py)

### DDL

```sql
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
);
```

### 字段说明

- `reconstruction_error = 1 - (sigma_1^2 + ... + sigma_5^2) / sum(sigma_i^2)`
  - 高值 = 前 5 因子解释不了多少方差 = 市场处于极度混沌或"电风扇轮动"状态
  - 这是对任何基于因子的策略都极其危险的信号
- `is_mutation`: 突变警报标志，供下游策略模块查询使用
- `UNIQUE KEY uk_date_window`: 支持幂等重跑 (ON DUPLICATE KEY UPDATE)

## 6. 可视化 (visualizer.py)

单张图，三层信息:

### 上半区: 因子集中度
- 三个窗口的 F1 曲线（不同颜色/透明度）
- 综合状态加权线
- 50%/35% 阈值虚线
- 突变警报标记（红色三角 ▲）

### 下半区: 解释度视角
- Top1 / Top3 / Top5 累计解释度曲线
- 解读逻辑:
  - F1 暴跌但 Top5 稳定 → 力量从指数大票转移到多板块轮动
  - Top5 也暴跌 → 市场进入彻底无序随机走势 (High Entropy)

### 背景色块
- 红/黄/绿标注历史状态区间

## 7. 报告 (reporter.py)

生成 Markdown 报告，包含:
- 当前市场状态判定及综合得分
- 多尺度因子集中度明细表
- 突变警报记录
- Top5 重构误差趋势
- 策略建议

## 8. 运行方式 (run_monitor.py)

### CLI 手动运行
```bash
# 指定日期范围
python -m data_analyst.market_monitor.run_monitor --start 2025-01-01 --end 2026-03-28

# 仅计算最新一天
python -m data_analyst.market_monitor.run_monitor --latest
```

### 集成 scheduler_service
```python
from data_analyst.market_monitor.run_monitor import run_daily_monitor

# 注册到 scheduler_service，每日 18:30 运行（数据检查之后）
scheduler.add_job(run_daily_monitor, 'cron', hour=18, minute=30)
```

## 9. 鲁棒性要求

1. **inf 值处理**: pct_change() 可能产生 inf（涨停/跌停后一字板），必须在 SVD 前清理
2. **空矩阵兜底**: 如果某窗口有效股票 < 50 只，跳过该窗口并记录警告
3. **重跑幂等**: 通过 UNIQUE KEY uk_date_window + ON DUPLICATE KEY UPDATE 保证
4. **降级策略**: 内存不足时自动降级为市值分层采样（抽取 500 只）

## 10. 依赖

```
scikit-learn   # Randomized SVD
scipy          # MAD 计算
numpy          # 矩阵运算
pandas         # 数据处理
matplotlib     # 可视化
pymysql        # 数据库
pydantic       # 数据模型 (schemas.py)
```
