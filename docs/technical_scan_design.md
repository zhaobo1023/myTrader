# 持仓技术面扫描系统 - 技术设计文档

> **版本**: v1.0  
> **创建日期**: 2026-03-30  
> **状态**: 待实现

---

## 1. 系统概述

### 1.1 目标
每日盘后自动扫描持仓股票的技术面状态，生成 Markdown 报告，帮助快速识别：
- 趋势健康度（均线位置关系）
- 强度信号（RPS 排名）
- 关键点位（回踩/突破）
- 量价配合

### 1.2 触发方式
- **定时触发**: 每日 16:30（A股收盘数据同步后）
- **手动触发**: 命令行执行

### 1.3 输出
- **扫描报告**: `/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay/TechScan_YYYYMMDD.md`
- **异常记录**: `/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay/backlog.md`
- **执行日志**: `output/tech_scan/scan_YYYYMMDD.log`

---

## 2. 模块结构

```
strategist/
└── tech_scan/
    ├── __init__.py
    ├── config.py              # 配置参数
    ├── portfolio_parser.py    # 持仓文件解析
    ├── data_fetcher.py        # 数据库数据获取
    ├── indicator_calculator.py # 技术指标计算
    ├── signal_detector.py     # 信号检测逻辑
    ├── report_generator.py    # Markdown 报告生成
    ├── backlog_manager.py     # 异常记录管理
    ├── scheduler.py           # 定时调度
    └── run_scan.py            # 主入口
```

---

## 3. 数据流

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  持仓文件解析    │────▶│  数据库查询      │────▶│  指标计算        │
│  (22只A股/ETF)  │     │  (OHLCV + RPS)  │     │  (MA/MACD/RSI)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Markdown 报告  │◀────│  报告生成        │◀────│  信号检测        │
│  + Backlog     │     │                 │     │  (预警/趋势)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## 4. 核心模块设计

### 4.1 持仓解析 (portfolio_parser.py)

**输入**: `/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md`

**解析逻辑**:
- 正则匹配表格中的股票代码（6位数字）
- 识别代码后缀（沪市 .SH / 深市 .SZ）
- 跳过港股（00xxx）和美股（字母代码）
- 提取持仓层级（L1/L2/L3）

**输出**:
```python
[
    {"code": "601857.SH", "name": "中国石油", "level": "L1"},
    {"code": "600406.SH", "name": "国电南瑞", "level": "L1"},
    ...
]
```

### 4.2 数据获取 (data_fetcher.py)

**数据源**: MySQL `wucai_trade` 数据库

**查询表**:
| 表名 | 用途 | 字段 |
|------|------|------|
| `trade_stock_daily` | 日线 OHLCV | stock_code, trade_date, open/high/low/close, volume |
| `trade_rps_daily` (待确认) | RPS 数据 | stock_code, trade_date, rps_120, rps_250 |

**查询范围**: 最近 300 个交易日（确保 MA250 可计算）

### 4.3 指标计算 (indicator_calculator.py)

复用 `strategist/doctor_tao/indicators.py` 中的 `IndicatorCalculator`，计算：

| 指标 | 计算方式 | 用途 |
|------|----------|------|
| MA5/20/60/250 | 简单移动平均 | 趋势判断 |
| MACD | EMA12-EMA26, Signal=EMA9 | 金叉/死叉 |
| RSI(14) | 相对强弱指数 | 超买/超卖 |
| RPS(120/250) | 从数据库读取或实时计算 | 强度排名 |
| 20日高点 | rolling max | 突破检测 |
| 5日均量 | volume rolling mean | 放量检测 |

### 4.4 信号检测 (signal_detector.py)

**预警信号**:

| 信号类型 | 检测条件 | 级别 |
|----------|----------|------|
| 回踩20日线 | `abs(close/ma20 - 1) < 0.015` | ⚠️ 黄灯 |
| 回踩60日线 | `abs(close/ma60 - 1) < 0.015` | ⚠️ 黄灯 |
| 跌破20日线 | `close < ma20 and prev_close >= prev_ma20` | 🔴 红灯 |
| 跌破60日线 | `close < ma60 and prev_close >= prev_ma60` | 🔴 红灯 |
| 创20日新高 | `close >= rolling_max_20` | 🟢 绿灯 |
| MA5上穿MA20 | `ma5 > ma20 and prev_ma5 <= prev_ma20` | 🟢 金叉 |
| MA5下穿MA20 | `ma5 < ma20 and prev_ma5 >= prev_ma20` | 🔴 死叉 |
| MACD金叉 | `macd > signal and prev_macd <= prev_signal` | 🟢 金叉 |
| MACD死叉 | `macd < signal and prev_macd >= prev_signal` | 🔴 死叉 |
| RSI超买 | `rsi > 70` | ⚠️ 黄灯 |
| RSI超卖 | `rsi < 30` | ⚠️ 黄灯 |
| RPS掉头 | `rps_250 < 80 and prev_rps_250 >= 80` | 🔴 红灯 |
| 放量 | `volume > ma_vol_5 * 1.5` | 📊 信息 |

**趋势状态**:
- **多头排列**: MA5 > MA20 > MA60 > MA250
- **空头排列**: MA5 < MA20 < MA60 < MA250
- **震荡**: 其他情况

### 4.5 报告生成 (report_generator.py)

**输出格式**:

```markdown
# 技术面扫描报告 - 2026-03-30

> 扫描时间: 2026-03-30 16:35:00  
> 持仓数量: 22 只 A股/ETF

---

## 🔴 红灯预警 (需关注)

| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 预警信号 |
|------|------|------|--------|--------|----------|
| 000408 | 藏格矿业 | L2 | 80.50 | -2.3% | 跌破20日线, MACD死叉 |

## ⚠️ 黄灯提醒

| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 提醒信号 |
|------|------|------|--------|--------|----------|
| 601857 | 中国石油 | L1 | 12.07 | +0.5% | 回踩20日线 |

## 🟢 积极信号

| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 积极信号 |
|------|------|------|--------|--------|----------|
| 000792 | 盐湖股份 | L1 | 39.45 | +1.2% | 创20日新高, 放量 |

---

## 📊 全持仓概览

| 代码 | 名称 | 层级 | 最新价 | MA20 | MA60 | RPS250 | 趋势 | 信号 |
|------|------|------|--------|------|------|--------|------|------|
| 601857 | 中国石油 | L1 | 12.07 | 11.85 | 11.50 | 75 | 多头 | 回踩20日线 |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

---

## 📈 技术指标明细

### 601857 中国石油
- **趋势**: 多头排列 (MA5 > MA20 > MA60)
- **均线偏离**: 距MA20 +1.8%, 距MA60 +4.9%
- **RPS**: 120日=68, 250日=75
- **MACD**: DIF=0.12, DEA=0.10, 柱状=0.02
- **RSI(14)**: 55.3
- **成交量**: 今日 1.2亿, 5日均量 0.9亿 (放量 1.3x)
```

### 4.6 异常记录 (backlog_manager.py)

**记录内容**:
- 数据缺失（某只股票无行情数据）
- 指标计算失败（历史数据不足）
- RPS 数据缺失

**格式**:
```markdown
# 技术扫描 Backlog

## 2026-03-30

- [ ] **000408.SZ 藏格矿业**: RPS数据缺失，需运行RPS计算任务
- [ ] **159992.SZ 创新药ETF**: 历史数据不足250日，MA250无法计算
```

---

## 5. 配置参数 (config.py)

```python
# 文件路径
PORTFOLIO_FILE = "/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md"
OUTPUT_DIR = "/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay"
LOG_DIR = "output/tech_scan"

# 数据库
DB_ENV = "online"  # 使用线上数据库

# 指标参数
MA_WINDOWS = [5, 20, 60, 250]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# 信号阈值
PULLBACK_THRESHOLD = 0.015  # 回踩阈值 ±1.5%
VOLUME_RATIO_THRESHOLD = 1.5  # 放量阈值
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RPS_WARNING_THRESHOLD = 80  # RPS 预警线

# 定时任务
SCHEDULE_TIME = "16:30"
```

---

## 6. 数据库表结构（待确认）

### 6.1 trade_stock_daily (已有)
```sql
CREATE TABLE trade_stock_daily (
    stock_code VARCHAR(20),
    trade_date DATE,
    open_price DECIMAL(10,2),
    high_price DECIMAL(10,2),
    low_price DECIMAL(10,2),
    close_price DECIMAL(10,2),
    volume BIGINT,
    amount DECIMAL(20,2),
    turnover_rate DECIMAL(10,4),
    PRIMARY KEY (stock_code, trade_date)
);
```

### 6.2 trade_rps_daily (待确认)
```sql
-- 需要确认是否存在，如不存在需要先运行 RPS 计算任务
CREATE TABLE trade_rps_daily (
    stock_code VARCHAR(20),
    trade_date DATE,
    rps_120 DECIMAL(5,2),  -- 120日涨幅排名分位
    rps_250 DECIMAL(5,2),  -- 250日涨幅排名分位
    PRIMARY KEY (stock_code, trade_date)
);
```

---

## 7. 依赖

```
pandas>=2.0
pandas-ta>=0.3.14b
pymysql>=1.0
python-dotenv>=1.0
schedule>=1.2  # 定时任务
```

---

## 8. 使用方式

```bash
# 手动执行扫描
python -m strategist.tech_scan.run_scan

# 启动定时任务（后台运行）
python -m strategist.tech_scan.scheduler

# 指定日期扫描（用于补扫）
python -m strategist.tech_scan.run_scan --date 2026-03-29
```

---

## 9. 待确认事项

1. **RPS 数据表**: 确认 `trade_rps_daily` 表是否存在，字段名是什么
2. **ETF 数据**: 确认 ETF（如 159992）是否在 `trade_stock_daily` 表中
3. **股票名称**: 是否有 `trade_stock_info` 表存储股票名称映射

---

## 10. 后续扩展

- [ ] 支持微信/飞书推送通知
- [ ] 支持自定义监控指标
- [ ] 支持行业对比分析
- [ ] 支持历史信号回溯
