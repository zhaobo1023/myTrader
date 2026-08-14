# 数据表与单位换算

> 何时读：需要手写 SQL 时（`fetch_stock_data.py` 未覆盖的临时查询）。
> 常规九项数据拉取由脚本完成，不需要读本文件。

## 连接方式

密码从仓库根目录 `.env` 的 `ONLINE_DB_PASSWORD` 读取（与 `config/settings.py` 同源，
`.env` 已在 gitignore 中）。`fetch_stock_data.py` 已封装，常规查询不需要手写连接。

需要临时手查时：

```bash
python .claude/skills/stock-analysis/scripts/fetch_stock_data.py --code 600584.SH --json
```

> **不要把密码写进命令行**。直接拼 `mysql -p'明文密码'` 会让密码进入
> shell 历史、进程列表和对话记录。要跑脚本没覆盖的 SQL，
> 优先在 `fetch_stock_data.py` 里加一个查询函数，而不是在对话里手拼连接串。

## 主键列名

**所有表的股票代码列都叫 `stock_code`，不是 `ts_code`。**
（全仓 905 处 `stock_code` vs 29 处 `ts_code`，后者是历史遗留。）
写错列名 MySQL 会报 Unknown column，属于容易发现的错误；
但下面「字段陷阱」里的问题是静默的。

## 核心数据表

| 表 | 内容 | 日期列 |
|---|---|---|
| `trade_stock_info` | 股票名称→代码映射、行业、主营业务 | - |
| `trade_stock_daily` | 日线行情 OHLCV | `trade_date` |
| `trade_stock_daily_basic` | 估值：总市值、PE/PB/PS | `trade_date` |
| `trade_stock_financial` | 财务汇总：营收、净利（**元**）、ROE、毛利率等 | `report_date` |
| `financial_income` | 利润表明细（亿元） | `report_date` |
| `financial_balance` | 资产负债表明细（亿元） | `report_date` |
| `financial_cashflow` | 现金流量表（亿元） | `report_date` |
| `financial_dividend` | 分红历史 | `ex_date` |
| `trade_stock_basic_factor` | 基础因子：动量、换手、波动率 | `calc_date` |
| `trade_stock_valuation_factor` | 估值因子：PE/PB/PS/市值 | `calc_date` |
| `trade_technical_indicator` | 技术指标：MA/MACD/RSI/KDJ | `trade_date` |
| `stock_news` | 新闻 | - |
| `research_announcements` | 公司公告 | `ann_date` |

## 字段陷阱（静默出错，务必先看）

**仓库里的 DDL 文件与线上真实表结构不一致**。以下字段名以线上 `trade` 库
（`information_schema` 实测）为准，不要照 `config/models.py` 或
`data_analyst/financial_fetcher/schemas.py` 写 SQL——那些 DDL 有过时字段。

已踩过的坑：`net_profit_margin`、`gross_profit_margin`、`debt_to_asset`、
`quick_ratio`、`bvps`、`cfps`、`dv_ttm` 这些**线上都不存在**，写进 SQL 会
报 Unknown column。

各表线上实际字段：

| 表 | 关键字段 |
|---|---|
| `trade_stock_financial` | `revenue`、`net_profit`（**元**）、`eps`、`roe`、`roa`、`gross_margin`、`net_margin`、`debt_ratio`、`current_ratio`、`operating_cashflow`、`total_assets`、`total_equity`、`data_source` |
| `financial_income` | `revenue`、`net_profit`、`net_profit_yoy`、`roe`、`gross_margin`、`eps`（亿元） |
| `financial_balance` | `total_assets`、`total_equity`（亿元）+ 一批银行专用指标 |
| `financial_cashflow` | `operating_cashflow`、`investing_cashflow`、`financing_cashflow`、`net_cashflow`（亿元） |
| `trade_stock_daily_basic` | `total_mv`、`circ_mv`（**亿元**）、`pe_ttm`、`pb`、`ps_ttm`、`total_share`、`circ_share`、`turnover_rate` |
| `trade_stock_daily` | `open_price`、`high_price`、`low_price`、`close_price`、`volume`、`amount`、`turnover_rate`（注意不是 open/close/vol） |
| `trade_stock_basic_factor` | `calc_date`、`mom_20`、`mom_60`、`reversal_5`、`turnover`、`vol_ratio`、`volatility_20`、`close` |
| `trade_technical_indicator` | `ma5/10/20/60/120/250`、`macd_dif`、`macd_dea`、`macd_histogram`、`rsi_6/12/24`、`kdj_k/d/j`、`bollinger_*`、`atr` |
| `research_announcements` | **`code`（不是 `stock_code`）**、`ann_date`、`ann_type`、`title`、`direction`、`magnitude`、`summary` |
| `stock_news` | `stock_code`、`title`、`content`、`source`、`publish_time`、`event_type`、`event_category`、`event_signal` |
| `trade_stock_info` | `stock_name`、`industry`、`listed_date`、`main_business` |

## 单位换算速查表（生成报告时统一换算为亿元）

| 数据表 | 字段 | 原始单位 | 换算方式 | 报告中单位 |
|---|---|---|---|---|
| `trade_stock_financial` | `revenue` / `net_profit` / `operating_cashflow` / `total_assets` / `total_equity` | **元** | ÷ 1e8 | 亿元 |
| `financial_income` | `revenue` / `net_profit` | 亿元 | 无需换算 | 亿元 |
| `financial_balance` | 所有金额 | 亿元 | 无需换算 | 亿元 |
| `financial_cashflow` | 所有金额 | 亿元 | 无需换算 | 亿元 |
| `trade_stock_daily_basic` | `total_mv` / `circ_mv` | **亿元** | 无需换算 | 亿元 |

> DDL 注释说 `total_mv` 是万元，**实测是亿元**（中兴通讯 `total_mv=1678.06`，
> 真实市值约 1678 亿）。按万元换算会把市值缩小 1 万倍。

**注意**：只有 `trade_stock_financial` 的金额是元，其余（含市值）都已是亿元。
`fetch_stock_data.py` 已内置换算，输出统一为亿元；手写 SQL 时必须自己按上表换算。

## 股票代码格式

标准格式为 `600584.SH`（带后缀）。`financial_income` 等财务表中可能不带后缀（`600584`），查询时两种都试。
`research_announcements` 实测存的是**裸 6 位**且列名是 `code`。

`fetch_stock_data.py` 已内置该重试逻辑（先带后缀，返回 0 行则换纯 6 位数字）。
