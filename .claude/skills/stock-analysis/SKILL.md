---
name: stock-analysis
description: A股个股全面分析。基于 myTrader 系统数据（ECS MySQL）和 Claude Financial Services 插件框架，生成结构化分析报告。触发条件：用户说"分析一下XX公司"、"做个全面分析"、"帮我研究XX"、"XX投资分析"，或输入 /stock-analysis。
---

# A 股个股全面分析

基于 myTrader 系统（ECS MySQL）的全量 A 股数据，结合 Claude Financial Services 插件分析框架，生成八章节结构化报告。

## 输入解析

从用户消息中提取：
1. **公司名称或股票代码**（必须） — 如"长电科技"、"600584"、"贵州茅台"
2. **输出路径**（可选） — 默认 `~/Documents/notes/Finance/`

如果用户未指定公司，主动询问。

## 数据源

所有数据从 ECS MySQL 获取。连接方式：

```bash
ssh aliyun-ecs "mysql -u mytrader_user -p'lGgS^uruPhv%AK0ZifeC' trade -e \"SQL\""
```

### 核心数据表

| 表 | 内容 | 日期列 |
|---|---|---|
| `trade_stock_info` | 股票名称→代码映射 | - |
| `trade_stock_daily` | 日线行情 OHLCV | `trade_date` |
| `trade_stock_daily_basic` | 估值：总市值、PE/PB/PS | `trade_date` |
| `trade_stock_financial` | 财务汇总：营收、净利、ROE、毛利率等 | `report_date` |
| `financial_income` | 利润表明细（亿元） | `report_date` |
| `financial_balance` | 资产负债表明细（亿元） | `report_date` |
| `financial_cashflow` | 现金流量表（亿元） | `report_date` |
| `financial_dividend` | 分红历史 | `ex_date` |
| `trade_stock_basic_factor` | 基础因子：动量、换手、波动率 | `calc_date` |
| `trade_stock_valuation_factor` | 估值因子：PE/PB/PS/市值 | `calc_date` |
| `trade_technical_indicator` | 技术指标：MA/MACD/RSI/KDJ | `trade_date` |
| `stock_news` | 新闻 | - |
| `research_announcements` | 公司公告 | `ann_date` |

### 注意事项

- `trade_stock_financial` 中的金额单位是**元**（原始值），需除以 1e8 转换为亿元
- `financial_income` / `financial_balance` / `financial_cashflow` 中的金额单位已经是**亿元**
- `trade_stock_daily_basic.total_mv` 单位是**万元**，需除以 10000 转换为亿元
- 股票代码格式：`600584.SH`（带后缀），`financial_income` 等表中可能不带后缀（`600584`），查询时两种都试

## 工作流程

### Step 1: 确认公司信息

查询 `trade_stock_info` 确认股票代码和名称。如果找不到，告知用户并停止。

### Step 2: 拉取全部数据（并行）

一次性并行拉取以下数据（每个查询一个 Bash 调用）：

1. **财务汇总** — `trade_stock_financial` 最近 12 个报告期
2. **利润表明细** — `financial_income` 最近 12 个报告期
3. **资产负债表** — `financial_balance` 最近 8 个报告期
4. **现金流量表** — `financial_cashflow` 最近 8 个报告期
5. **最新估值** — `trade_stock_daily_basic` 最近 5 个交易日
6. **近期行情** — `trade_stock_daily` 最近 20 个交易日
7. **技术因子** — `trade_stock_basic_factor` 最近 5 个交易日
8. **公司公告** — `research_announcements` 最近 10 条（如 code 不带后缀则用 6 位纯数字）
9. **最新新闻** — `stock_news` 最近 5 条

### Step 3: 数据完备性检查

**逐项检查数据是否充分，如有缺失必须明确告知用户：**

| 检查项 | 最低要求 | 缺失处理 |
|---|---|---|
| 财务数据 | 至少 4 个年度报告 | 告知"财务数据不足，无法做趋势分析" |
| 现金流数据 | 至少 3 个年度 | 告知"现金流数据不足，盈利质量分析受限" |
| 资产负债数据 | 至少 2 个报告期 | 告知"资产负债数据不足，无法评估杠杆" |
| 估值数据 | 当前 PE/PB | 告知"估值数据缺失" |
| 行情数据 | 至少 10 个交易日 | 告知"行情数据不足" |

**如果关键数据缺失严重（财务数据 < 2 年），先询问用户是否继续，不要直接生成不完整的报告。**

### Step 4: 查找可比公司

根据公司所在行业，查找 2-5 家同行业可比公司：
- 拉取可比公司的 `trade_stock_daily_basic`（最新日估值）和 `trade_stock_financial`（最新年报）
- 确保对比数据使用**同一交易日**的估值数据
- 如果某家可比公司数据缺失，补齐或标注

### Step 5: 生成分析报告

按以下八个章节生成报告：

#### 第一章：公司概览
- 一句话定位（行业、排名、主营业务）
- 主要客户/产品

#### 第二章：财报分析
- 营收/净利润 3 年趋势 + 同比增速
- 毛利率/净利率/ROE 趋势
- 最新季度 vs 去年同期对比
- 盈利质量：经营现金流/净利润比率（至少 3 年）

#### 第三章：可比公司分析
- 同行业 3-5 家公司对比表格（市值、PE、PB、PS、营收、净利、毛利率、ROE）
- 统计摘要（最大值、75%/50%/25%分位、最小值）
- 关键发现：估值高低、盈利效率对比

#### 第四章：DCF 估值框架
- A 股调整参数：无风险利率（中国 10Y 国债 ~1.7%）、Beta（沪深300）、ERP（5-7%）、WACC
- 三情景估值（Bear/Base/Bull）
- 敏感性分析表（WACC vs 终端增速）
- 当前市值在估值区间中的位置

#### 第五章：竞争格局
- 行业全球/全国排名
- 核心竞争壁垒评估
- 主要风险

#### 第六章：行业研究
- 行业周期定位
- 增长驱动因素
- 核心风险

#### 第七章：技术面与动量
- 股价、20/60 日动量、波动率、换手率
- 简要技术面信号解读

#### 第八章：投资观点卡片
- 核心观点（1-2 句话）
- 投资支柱（2-3 条）+ 风险（2-3 条），附信心度
- 催化剂列表
- 目标价区间 + 止损线
- **免责声明：本分析仅供参考，不构成投资建议**

### Step 6: 写入文档

将完整报告写入 `~/Documents/notes/Finance/` 目录：
- 文件名格式：`{公司名}-全面分析-{YYYYMMDD}.md`
- 使用 Markdown 格式
- 表格对齐，数字保留合理精度

### Step 7: 向用户汇报

简要汇报：
1. 报告已写入的文件路径
2. 关键发现摘要（2-3 句）
3. 如有数据缺失，列出缺失项

## 约束

- 所有分析基于 myTrader 系统中的实际数据，不编造数字
- 估值参数明确标注来源和假设
- 区分事实和分析，分析部分标注"判断"/"估计"
- 报告末尾必须包含免责声明
- 不使用 emoji
