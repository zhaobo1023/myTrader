# Claude Financial Services 插件使用指南

> 适用于 myTrader 项目，基于 Anthropic 官方 `claude-for-financial-services` 插件库，适配 A 股分析场景。

## 一、已安装插件

| 插件 | 类型 | 说明 |
|---|---|---|
| **financial-analysis** | 核心 | DCF、Comps、LBO、三表模型、Excel 审计、Deck QC |
| **equity-research** | 垂直 | 财报分析、首次覆盖、行业概览、观点追踪、晨会笔记 |
| **pitch-agent** | Agent | 端到端 Pitch Deck 生成 |
| **market-researcher** | Agent | 行业研究、竞争格局、同业比较 |
| **model-builder** | Agent | DCF/LBO/三表模型构建 |

所有插件已通过 `claude plugin marketplace add` 从本地仓库安装，scope 为 user（全局可用）。

## 二、可用 Slash 命令

### 财务建模类（financial-analysis）

| 命令 | 用途 | A 股适用场景 |
|---|---|---|
| `/comps <公司名>` | 可比公司分析 | 同行业估值比较（PE/PB/PS 倍数） |
| `/dcf <公司名>` | DCF 估值模型 | 个股内在价值测算 |
| `/lbo <公司名>` | LBO 模型 | 适用度较低，A股杠杆收购少 |
| `/3-statement-model` | 三表联动模型 | 利润表/资产负债表/现金流量表建模 |
| `/debug-model` | Excel 模型审计 | 检查公式错误、硬编码、平衡校验 |
| `/competitive-analysis` | 竞争格局分析 | 行业内公司对比定位 |
| `/ppt-template` | PPT 模板创建 | 自定义分析报告模板 |

### 研究分析类（equity-research）

| 命令 | 用途 | A 股适用场景 |
|---|---|---|
| `/earnings <公司名>` | 财报分析 | 季报/半年报/年报解读 |
| `/earnings-preview <公司名>` | 财报预览 | 财报发布前情景分析 |
| `/initiate <公司名>` | 首次覆盖报告 | 深度个股研究（30-50页） |
| `/model-update` | 模型更新 | 根据最新财报更新估值模型 |
| `/morning-note` | 晨会笔记 | 每日市场观点和交易想法 |
| `/sector <行业名>` | 行业概览 | 申万行业深度研究 |
| `/thesis <公司名>` | 观点追踪 | 持仓股投资逻辑追踪和评分 |
| `/catalysts` | 催化剂日历 | 追踪即将到来的事件催化剂 |
| `/screen` | 选股筛选 | 基于条件的选股 |

## 三、A 股数据资产（ECS MySQL）

以下是 myTrader 系统中可用于插件分析的数据：

### 核心行情数据

| 表 | 记录数 | 股票数 | 时间范围 | 内容 |
|---|---|---|---|---|
| `trade_stock_daily` | 694万 | 5,647 | 2020-01 ~ 2026-05 | 日线 OHLCV、换手率 |
| `trade_stock_daily_basic` | 586万 | 5,517 | 2022-01 ~ 2026-05 | 总市值、流通市值、PE/PB/PS |
| `trade_stock_info` | 5,495 | - | - | 股票基本信息 |

### 因子数据

| 表 | 记录数 | 股票数 | 时间范围 | 内容 |
|---|---|---|---|---|
| `trade_stock_basic_factor` | 228万 | 5,185 | 2024-01 ~ 2026-05 | 动量、反转、换手、波动率等基础因子 |
| `trade_stock_valuation_factor` | 有 | 有 | - | PE_TTM、PB、PS_TTM、市值 |
| `trade_technical_indicator` | 有 | 有 | - | MA/MACD/RSI/KDJ/BOLL/ATR |
| `trade_stock_rps` | 有 | 有 | - | 相对强度排名 |

### 财务数据

| 表 | 记录数 | 股票数 | 时间范围 | 内容 |
|---|---|---|---|---|
| `trade_stock_financial` | 30.7万 | 5,201 | 1988 ~ 2026-03 | 营收、净利润、EPS、ROE、ROA、毛利率、负债率等 |
| `financial_cashflow` | 1,459 | 78 | 1998 ~ 2025-12 | 现金流量表（部分股票） |
| `financial_income` | 0 | - | - | 利润表明细（待补充） |
| `financial_balance` | 0 | - | - | 资产负债表明细（待补充） |

### 市场情绪和宏观数据

| 表 | 记录数 | 时间范围 | 内容 |
|---|---|---|---|
| `trade_fear_index` | 13 | 2026-04 ~ 2026-05 | VIX、恐慌贪婪指数、市场体制 |
| `trade_north_holding` | 7.7万 | 2024-06 ~ 2024-08 | 北向资金持仓（历史数据） |
| `trade_sector_strength_daily` | 有 | - | 板块强度 |
| `sw_industry_valuation` | 有 | - | 申万行业估值 |
| `macro_data` | 有 | - | 宏观指标（油价、金价、PMI等） |
| `stock_news` | 252 | - | 股票新闻 |
| `research_announcements` | 9,726 | - | 公司公告 |
| `trade_rag_report` | 197 | - | RAG 研究报告 |

## 四、A 股分析适配方案

### 4.1 财报分析（`/earnings`）

**数据来源映射：**

| 原始（美股） | A 股替代 | myTrader 数据源 |
|---|---|---|
| 10-Q / 10-K | 季报/半年报/年报 | `trade_stock_financial` + `research_announcements` |
| Consensus Estimates | 万得一致预期 | 需额外接入 Wind 或东方财富 |
| Earnings Call Transcript | 业绩说明会纪要 | 巨潮资讯网公告 |
| Segment Data | 分部报告 | 年报附注 |

**使用流程：**

1. 从 ECS 查询目标公司的财务数据：
   ```sql
   SELECT * FROM trade_stock_financial
   WHERE stock_code = '600519.SH'
   ORDER BY report_date DESC LIMIT 8;
   ```

2. 在 Claude Code 中执行：`/earnings 贵州茅台`

3. 将查询到的财务数据提供给 Claude 作为分析输入

**关键调整：**
- 财报周期：A股使用一季报（Q1）、半年报（H1）、三季报（Q3）、年报（FY）
- 披露截止日：Q1/H1=4月30日，Q3=10月31日，FY=4月30日
- 指标差异：A股不直接披露 EBITDA，需从营业利润 + 折旧摊销计算

### 4.2 可比公司分析（`/comps`）

**数据来源映射：**

| 指标 | A 股数据 | 对应表 |
|---|---|---|
| Market Cap | 总市值 | `trade_stock_daily_basic.total_mv` |
| PE TTM | 滚动市盈率 | `trade_stock_valuation_factor.pe_ttm` |
| PB | 市净率 | `trade_stock_valuation_factor.pb` |
| PS TTM | 市销率 | `trade_stock_valuation_factor.ps_ttm` |
| Revenue Growth | 营收增速 | `trade_stock_financial.revenue`（同比计算） |
| Gross Margin | 毛利率 | `trade_stock_financial.gross_margin` |
| Net Margin | 净利率 | `trade_stock_financial.net_margin` |
| ROE | 净资产收益率 | `trade_stock_financial.roe` |

**使用流程：**

1. 确定同行业可比公司（用申万行业分类）
   ```sql
   SELECT DISTINCT ts_code FROM trade_stock_industry
   WHERE industry_name = '白酒';
   ```

2. 提取可比公司的估值和财务数据
3. 执行：`/comps 贵州茅台` 并提供数据

**A股行业特色指标：**

| 行业 | 关键指标 |
|---|---|
| 银行 | ROE、不良率、净息差、成本收入比 |
| 房地产 | 合约销售、预收账款、净负债率 |
| 新能源 | 产能、产能利用率、单瓦成本 |
| 消费 | 门店数、同店增长、渠道毛利率 |
| 医药 | 在研管线阶段、商业化产品数、医院覆盖 |
| 互联网 | MAU、ARPU、抽佣率、GMV |

### 4.3 DCF 估值（`/dcf`）

**A股关键参数调整：**

| 参数 | 美股默认 | A 股调整 |
|---|---|---|
| Risk-free Rate | US 10Y (~4.3%) | 中国 10Y 国债 (~1.6-1.8%) |
| Beta 基准 | S&P 500 | 沪深300 |
| Equity Risk Premium | 4-6% | 5-7%（新兴市场溢价） |
| Cost of Debt | 美联储基准利率 | LPR（贷款市场报价利率） |
| Tax Rate | 21% (US) | 25%（高新技术企业 15%） |
| Terminal Growth | 2-3% | 4-5%（中国长期 GDP 增速） |

**使用流程：**

1. 从 `trade_stock_financial` 获取历史财务数据（至少 3-5 年）
2. 从 `trade_stock_daily_basic` 获取当前市值和估值倍数
3. 执行：`/dcf <公司名>` 并提供数据
4. 手动调整 WACC 参数为中国市场基准

### 4.4 行业研究（`/sector`）

**直接可用的数据：**
- `sw_industry_valuation` — 申万行业估值水平
- `trade_sector_strength_daily` — 板块强度
- `trade_stock_industry` — 股票行业分类
- `trade_north_holding` — 北向资金流向

**使用流程：**

1. 执行：`/sector 白酒行业`（或新能源/医药等）
2. 从 ECS 提取该行业的整体估值和资金流数据作为补充
3. 插件会生成行业概览、竞争格局、估值对比

### 4.5 投资观点追踪（`/thesis`）

**适用于你的持仓管理：**

1. 为你的 28 只持仓股建立投资逻辑
2. 每次财报/公告后用 `/thesis` 更新评分
3. 生成催化剂日历（`/catalysts`）追踪关键时间点

**持仓股示例（from holdings.json）：**
```
000858.SZ 五粮液 | 601318.SH 中国平安 | 600519.SH 贵州茅台
300750.SZ 宁德时代 | 000568.SZ 泸州老窖 | ...
```

### 4.6 竞争分析（`/competitive-analysis`）

**结合 myTrader 数据的最佳场景：**
- 分析某个申万行业内的竞争格局
- 对比同行业公司的因子表现（动量、估值、质量等）
- 为选股策略提供定性分析支撑

## 五、日常使用建议

### 每日流程

| 时间 | 动作 | 命令 |
|---|---|---|
| 盘前 | 浏览晨会笔记 | `/morning-note` |
| 盘中 | 关注持仓公告 | 查 `research_announcements` 表 |
| 盘后 | 查看技术扫描报告 | myTrader 已有 `trade_tech_report` |
| 财报季 | 分析财报 | `/earnings <公司名>` + ECS 财务数据 |
| 周末 | 更新投资观点 | `/thesis <公司名>` |

### 与 myTrader 系统协作

```
                    Claude Code + FS 插件
                    ┌──────────────────┐
                    │  /earnings       │
                    │  /comps          │
                    │  /dcf            │
                    │  /sector         │
                    │  /thesis         │
                    └────────┬─────────┘
                             │ 查询数据
                    ┌────────▼─────────┐
                    │  ECS MySQL       │
                    │  ┌──────────────┐│
                    │  │ 行情数据      ││
                    │  │ 因子数据      ││
                    │  │ 财务数据      ││
                    │  │ 公告/新闻     ││
                    │  └──────────────┘│
                    └────────┬─────────┘
                             │ 数据产出
                    ┌────────▼─────────┐
                    │  myTrader 系统    │
                    │  - RAG 研究报告   │
                    │  - 策略信号       │
                    │  - 风控检查       │
                    └──────────────────┘
```

### 数据补充建议

当前数据缺口及补充优先级：

| 优先级 | 缺口 | 建议 |
|---|---|---|
| **高** | `financial_income`（利润表明细）为空 | 补充收入、成本、费用明细行 |
| **高** | `financial_balance`（资产负债表）为空 | 补充资产、负债、权益明细 |
| **高** | 北向资金仅到 2024-08 | 恢复北向资金采集 |
| **中** | 一致预期数据缺失 | 接入东方财富或万得一致预期 |
| **低** | 业绩说明会纪要 | 可从巨潮资讯抓取 |

## 六、插件管理命令

```bash
# 查看已安装插件
claude plugin list

# 安装更多插件
claude plugin install <插件名>@claude-for-financial-services

# 可选插件：investment-banking, private-equity, wealth-management,
#           fund-admin, operations, earnings-reviewer, gl-reconciler 等

# 更新插件（从 marketplace 拉取最新）
claude plugin marketplace update claude-for-financial-services

# 禁用/启用插件
claude plugin disable <插件名>
claude plugin enable <插件名>

# 卸载插件
claude plugin uninstall <插件名>
```

## 七、注意事项

1. **数据时效性**：插件中的分析框架基于美股体系，A股使用时需手动调整参数（见第四章）
2. **MCP 数据源**：插件内置的 FactSet/Morningstar 等 MCP 连接器面向全球市场，A股数据建议直接从 myTrader 的 MySQL 获取
3. **输出格式**：插件默认输出 DOCX/XLSX，可根据需要调整为 Markdown
4. **语言**：插件提示词为英文，但 Claude 可以用中文输出分析结果
5. **合规声明**：插件产出的分析报告仅供参考，不构成投资建议
