# 估值数据增强技术方案

**日期:** 2026-04-15
**背景:** 对标理杏仁调研（见 docs/lixinger_research.md），补全数据层核心差距
**优先级:** P0 先行，分 3 个里程碑逐步交付

---

## 一、目标

| 里程碑 | 目标 | 工作量 |
|--------|------|--------|
| M1 | 申万行业指数估值分位 + 宏观数据补全 | ~3天 |
| M2 | 估值多口径（中位数/等权）+ 指数温度 | ~2天 |
| M3 | 个股估值历史走势 API + 前端展示 | ~2天 |

---

## 二、M1 - 申万行业指数估值分位 + 宏观数据补全

### M1.1 申万行业指数估值体系

**目标：** 为申万 31 个一级行业指数，每日计算并存储 PE-TTM / PB / 股息率，并计算 5 年历史分位。

#### 数据源

- AKShare `stock_sector_pe_em()`：申万行业最新 PE、PB 数据
- AKShare `sw_index_daily_indicator()`：申万行业历史估值序列

#### 新增数据库表

```sql
CREATE TABLE sw_industry_valuation (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    trade_date  DATE NOT NULL COMMENT '交易日',
    sw_code     VARCHAR(10) NOT NULL COMMENT '申万行业代码',
    sw_name     VARCHAR(50) NOT NULL COMMENT '行业名称',
    sw_level    TINYINT NOT NULL DEFAULT 1 COMMENT '行业层级 1/2/3',
    pe_ttm      DOUBLE COMMENT 'PE-TTM 市值加权',
    pe_ttm_median DOUBLE COMMENT 'PE-TTM 中位数',
    pb          DOUBLE COMMENT 'PB 市值加权',
    pb_median   DOUBLE COMMENT 'PB 中位数',
    dividend_yield DOUBLE COMMENT '股息率',
    pe_ttm_pct5y  DOUBLE COMMENT 'PE-TTM 5年历史分位 0-1',
    pb_pct5y      DOUBLE COMMENT 'PB 5年历史分位 0-1',
    pe_ttm_pct10y DOUBLE COMMENT 'PE-TTM 10年历史分位 0-1',
    pb_pct10y     DOUBLE COMMENT 'PB 10年历史分位 0-1',
    valuation_score DOUBLE COMMENT '综合估值温度 0-100',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date_code (trade_date, sw_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='申万行业指数估值';
```

#### 核心模块

**新文件：** `data_analyst/fetchers/sw_industry_fetcher.py`

```
SWIndustryFetcher
├── fetch_latest()               # 获取今日申万行业估值
├── fetch_history(start, end)    # 回填历史数据
├── calculate_percentile(df)     # 计算历史分位（5年/10年）
├── calculate_valuation_score()  # 合成估值温度 0-100
└── save_to_db(records)          # 存入 sw_industry_valuation 表
```

**估值温度计算方式（参考理杏仁）：**
```
valuation_score = (pe_ttm_pct5y * 0.5 + pb_pct5y * 0.3 + (1 - dividend_yield_pct5y) * 0.2) * 100
```
- 分数越低表示估值越低（越值得关注）
- 分数 < 30 为低估区间，> 70 为高估区间

#### 调度器集成

在 `tasks/04_indicators.yaml` 新增任务：
```yaml
sw_industry_valuation:
  description: 申万行业估值分位计算
  module: data_analyst.fetchers.sw_industry_fetcher
  func: run_daily
  schedule: "16:30"
  depends_on: []
  tags: [daily, valuation]
```

---

### M1.2 宏观数据补全

**目标：** 补充 CPI、PPI、社融 三项缺失的宏观指标，存入现有 `macro_data` 表。

#### 新增指标

| 指标 | AKShare 接口 | 频率 |
|------|-------------|------|
| CPI 同比 | `macro_china_cpi_yearly()` | 月度 |
| PPI 同比 | `macro_china_ppi_yearly()` | 月度 |
| 社融规模增量 | `macro_china_shrzgm()` | 月度 |
| 社融存量同比 | `macro_china_shrzgm()` | 月度 |

#### 实现位置

在 `data_analyst/fetchers/macro_fetcher.py`（或新建同路径文件）中新增 4 个函数：

```python
def fetch_cpi() -> List[dict]:          # CPI 月度数据
def fetch_ppi() -> List[dict]:          # PPI 月度数据
def fetch_social_financing() -> List[dict]:  # 社融增量+存量同比
```

`macro_data` 表已有 `indicator_name / value / period_date` 结构，直接复用。

#### 调度器集成

在 `tasks/02_macro.yaml` 追加：
```yaml
fetch_macro_cpi_ppi:
  description: 拉取 CPI/PPI/社融 月度宏观数据
  module: data_analyst.fetchers.macro_fetcher
  func: fetch_cpi_ppi_social_financing
  schedule: "09:00"
  tags: [monthly, macro]
```

---

## 三、M2 - 估值多口径 + 指数温度 API

### M2.1 估值多口径（中位数/等权）

**目标：** 为现有宽基指数（10只）和申万一级行业，在估值计算时同时产出**中位数口径**，用于过滤极值影响。

#### 实现策略

宽基指数估值（沪深300等）通过 AKShare `index_value_name_funddb()` 获取，当前只取市值加权 PE。
需要修改 `data_analyst/fetchers/` 中对应的拉取逻辑，同时存储：
- `pe_ttm`（市值加权，现有）
- `pe_ttm_median`（成分股 PE 中位数，新增）
- `pb_median`（成分股 PB 中位数，新增）

新增字段到 `market_index_valuation` 表（如不存在则新建）。

### M2.2 指数温度 API

**新增 API 端点：**

```
GET /api/analysis/valuation/temperature
  ?type=sw_industry | index
  &date=2026-04-15  (可选，默认最新)

响应：
{
  "date": "2026-04-15",
  "items": [
    {
      "code": "801010",
      "name": "农林牧渔",
      "pe_ttm": 22.5,
      "pe_ttm_pct5y": 0.35,
      "pb": 1.8,
      "pb_pct5y": 0.28,
      "valuation_score": 31.5,
      "label": "低估"   // 低估/合理/高估
    },
    ...
  ]
}

GET /api/analysis/valuation/history/{code}
  ?metric=pe_ttm | pb | dividend_yield
  &years=5 | 10

响应：时序数据 + 分位带（20%/50%/80%）
```

**实现位置：** `api/routers/analysis.py` + `api/services/analysis_service.py`

---

## 四、M3 - 个股估值历史走势 + 前端展示

### M3.1 个股估值历史走势 API

**新增 API 端点：**

```
GET /api/analysis/valuation/stock/{code}/history
  ?years=5

响应：
{
  "code": "000858",
  "name": "五粮液",
  "current": { "pe_ttm": 18.5, "pb": 3.2, "pct5y": 0.22 },
  "history": [
    { "date": "2021-01-04", "pe_ttm": 55.2, "pb": 8.1 },
    ...
  ],
  "percentile_bands": {
    "p20": { "pe_ttm": 15.2, "pb": 2.5 },
    "p50": { "pe_ttm": 26.8, "pb": 4.2 },
    "p80": { "pe_ttm": 45.1, "pb": 6.8 }
  }
}
```

数据来源：`trade_stock_daily_basic` 表（已有 `pe_ttm` / `pb` 字段）。

### M3.2 前端展示

**在 `web/src/app/analysis/` 页面新增"估值分析"Tab：**

1. **行业估值温度热力表**
   - 行：申万 31 个一级行业
   - 列：PE分位、PB分位、综合温度
   - 颜色：绿（低估）→ 黄（合理）→ 红（高估）

2. **个股估值历史走势图**
   - PE-TTM / PB 历史曲线
   - 叠加 20% / 50% / 80% 分位带
   - 使用现有的折线图组件（或 ECharts）

---

## 五、任务清单

### M1 任务（约3天）

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| T1.1 | 创建 `sw_industry_valuation` 表 DDL | P0 | 0.5h |
| T1.2 | 实现 `SWIndustryFetcher.fetch_latest()` | P0 | 2h |
| T1.3 | 实现历史分位计算 `calculate_percentile()` | P0 | 2h |
| T1.4 | 实现估值温度评分 `calculate_valuation_score()` | P0 | 1h |
| T1.5 | 历史数据回填（2年+） | P0 | 1h |
| T1.6 | 集成调度器任务 | P0 | 0.5h |
| T1.7 | 补充 CPI/PPI 宏观数据拉取 | P0 | 2h |
| T1.8 | 补充社融规模数据拉取 | P0 | 2h |
| T1.9 | 调度器集成宏观月度任务 | P0 | 0.5h |

### M2 任务（约2天）

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| T2.1 | 宽基指数估值增加中位数口径 | P1 | 2h |
| T2.2 | 更新 `market_index_valuation` 表结构 | P1 | 0.5h |
| T2.3 | 实现 `GET /api/analysis/valuation/temperature` | P1 | 2h |
| T2.4 | 实现 `GET /api/analysis/valuation/history/{code}` | P1 | 2h |
| T2.5 | 编写 analysis_service 中的 valuation 业务逻辑 | P1 | 2h |

### M3 任务（约2天）

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| T3.1 | 个股估值历史走势 API | P2 | 2h |
| T3.2 | 前端行业估值温度热力表组件 | P2 | 3h |
| T3.3 | 前端个股估值历史走势图组件 | P2 | 3h |
| T3.4 | analysis 页面集成"估值分析"Tab | P2 | 2h |

---

## 六、技术依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| AKShare `stock_sector_pe_em` | 需验证 | 申万行业 PE/PB 是否稳定可用 |
| `trade_stock_daily_basic.pe_ttm` | 已有 | 个股历史 PE 数据 |
| `macro_data` 表 | 已有 | 复用现有宏观数据表结构 |
| 调度器 YAML | 已有 | 集成到现有 DAG 框架 |
| FastAPI analysis router | 已有 | 在现有路由文件扩展 |

---

## 七、验收标准

**M1 验收：**
- [ ] `sw_industry_valuation` 表包含近 2 年历史数据
- [ ] 每个工作日 16:30 自动更新当日数据
- [ ] 分位计算正确（对比手动计算验证 3 个行业）
- [ ] CPI/PPI/社融 数据在 `macro_data` 表中可查询

**M2 验收：**
- [ ] `GET /api/analysis/valuation/temperature` 返回 31 个行业的估值温度
- [ ] `label` 字段分类符合分位阈值（<30低估，>70高估）
- [ ] 历史走势接口返回完整时序 + 分位带

**M3 验收：**
- [ ] 前端行业热力表颜色渐变正确，点击行业可钻取
- [ ] 个股估值曲线图包含分位带参考线
- [ ] 整体与 analysis 页面风格一致

---

## 八、参考文档

- [理杏仁竞品调研](../lixinger_research.md)
- [数据补充方案](../data_supplement_guide.md)
- [市场看板设计](../market_dashboard_design.md)
- [理杏仁 Wiki - PE-TTM 计算说明](https://www.lixinger.com/wiki/pe-ttm)
- [理杏仁 Wiki - 分位点说明](https://www.lixinger.com/wiki/percentile)
