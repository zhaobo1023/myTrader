# myTrader 每日开发日志

---

## 2026-04-15 估值数据增强 M1/M2 实施

### 今日工作内容

#### 1. 理杏仁竞品调研 + 技术方案

对标 https://www.lixinger.com/ 完成产品功能调研，制定 M1-M3 估值增强方案。
产出文档：`docs/lixinger_research.md`、`docs/plans/2026-04-15-valuation-enhancement.md`

#### 2. 申万行业数据验证与修复

- `trade_stock_basic` 新增 `sw_level1` / `sw_level2` 字段（用户已完成）
- 覆盖率分析：sw_level1 73.2% → **94.5%**（5194/5497）
  - 根因：未覆盖股票的 `industry` 字段本来就是 NULL（北交所）或已有值
  - 修复：用 `industry` 字段回填 `sw_level1`，一条 UPDATE 补充 1169 只股票
  - 剩余 303 只是北交所股票（无申万行业分类，属正常）

#### 3. 宏观数据补全（macro_fetcher.py）

新增 5 个月度宏观指标写入 `macro_data` 表：

| 指标 | indicator | 数据量 |
|------|-----------|--------|
| CPI同比 | cpi_yoy | 20 条（2024.01~2025.08） |
| PPI同比 | ppi_yoy | 20 条（2024.01~2025.08） |
| M0货币同比 | m0_yoy | 27 条（2024.01~2026.03） |
| M1货币同比 | m1_yoy | 27 条（2024.01~2026.03） |
| M2货币供应同比 | m2_supply_yoy | 27 条（2024.01~2026.03） |

新增函数：`fetch_cpi_yoy`、`fetch_ppi_yoy`、`fetch_money_supply_indicators`（联合函数）
注册到 `FETCH_FUNCTIONS` 和 `fetch_all_indicators` 的 `skip_set` / 联合调用中。

#### 4. 申万行业估值分位系统

**新建表 `sw_industry_valuation`（17 字段）：**
- trade_date / sw_name / sw_level
- pe_ttm（市值加权）/ pe_ttm_eq（等权）/ pe_ttm_med（中位数）
- pb（市值加权）/ pb_med（中位数）
- pe_pct_5y / pb_pct_5y / pe_pct_10y / pb_pct_10y（历史分位）
- valuation_score（0-100 估值温度）/ valuation_label（低估/合理/高估）

**新建 `sw_industry_valuation_fetcher.py`：**
- `calc_daily_industry_valuation(date)` -- JOIN trade_stock_daily_basic + trade_stock_basic，按申万一级行业聚合 PE/PB（三口径）
- `calc_percentile(series, window)` -- 滚动历史分位（5年/10年窗口）
- `_batch_update_percentiles()` -- 一次性加载全量历史批量计算所有分位并 UPDATE
- `run_daily()` / `run_backfill()` -- 日常增量 + 历史回填

**数据质量验证（2026-04-08）：**
- 31 个行业全覆盖（含银行 PE=6.8、国防军工 PE=56.4 等合理值）
- PE 三口径均正常（市值加权 < 等权 < 中位数，符合分布特征）

**历史回填：** 2024-01-01 起回填，后台运行中

#### 5. 估值 API（M2 完成）

**`api/services/analysis_service.py` 新增 3 个函数：**
- `get_industry_valuation_temperature(trade_date)` -- 行业估值温度列表
- `get_industry_valuation_history(industry, metric, years)` -- 行业历史走势 + 分位带
- `get_stock_valuation_history(stock_code, years)` -- 个股历史 PE/PB + 分位带

**`api/routers/analysis.py` 新增 3 个端点：**
```
GET /api/analysis/valuation/temperature               # 行业估值温度（低估排前）
GET /api/analysis/valuation/industry/{name}/history   # 行业历史走势
GET /api/analysis/valuation/stock/{code}/history      # 个股历史 PE/PB
```

**`tasks/04_indicators.yaml` 新增：**
```yaml
calc_sw_industry_valuation:  # 每日 after_gate 自动运行
```

### 回填完成验证（2026-04-15）

- 总记录: **20739 条** = 669 交易日 x 31 行业，数据完整
- 有分位记录: 16895 条（81.5%，前 ~120 天无分位属正常，窗口未满）
- Bug 修复：唯一键 `(trade_date, sw_code)` 改为 `(trade_date, sw_name)` 后重新回填
- API 全部验证通过：食品饮料 score=12.1（低估）、通信 score=99.9（高估），符合市场认知
- 五粮液个股：PE分位=8.2%，PB分位=4.7%，历史极低位

### 待完成

- [ ] M3：前端行业估值热力表 + 个股估值历史走势图

产出文档：`docs/plans/2026-04-15-valuation-enhancement.md`

---

## 2026-04-14 策略模拟池系统 (SimPool) 完整实现

### 今日工作内容

#### 1. SimPool 系统设计与任务拆分

编写完整系统设计文档和任务拆分文档：

- `docs/sim_pool_design.md` -- 系统概念、5 张表 DDL、模块结构、数据流、API 设计
- `docs/sim_pool_tasks.md` -- 24 个任务，分 M1-M5 五个里程碑

**核心设计原则：**
- 无人工干预：创建后自动执行，不允许手动买卖
- 交易成本：佣金 0.03% + 滑点 0.1% + 印花税 0.1%（仅卖出）
- 整数手：持股数必须是 100 的整数倍，余额作为现金保留
- 等权分配：`weight = 1 / N`，不超过 max_positions

#### 2. 核心引擎实现 (M1)

| 模块 | 文件 | 功能 |
|------|------|------|
| 建表 | `strategist/sim_pool/schemas.py` | 5 张表 DDL + `ensure_tables()` |
| 配置 | `strategist/sim_pool/config.py` | `SimPoolConfig` dataclass |
| 池子管理 | `strategist/sim_pool/pool_manager.py` | 创建/查询/关闭池子 |
| 持仓跟踪 | `strategist/sim_pool/position_tracker.py` | T+1买入/价格更新/止盈止损/停牌处理 |
| 净值计算 | `strategist/sim_pool/nav_calculator.py` | 日净值/回撤/基准净值 |

**退出条件（按优先级）：**
1. `stop_loss`: 净收益率 <= -10%
2. `take_profit`: 净收益率 >= +20%
3. `max_hold`: 持有天数 >= 60
4. `suspended`: 连续停牌 >= 5 个交易日

#### 3. 策略适配器 (M2)

| 适配器 | 文件 | 封装模块 |
|--------|------|---------|
| 动量反转 | `strategies/momentum.py` | `doctor_tao.SignalScreener` |
| 行业轮动 | `strategies/industry.py` | `universe_scanner.ScoringEngine` |
| 微盘股 | `strategies/micro_cap.py` | `trade_stock_daily_basic` + `trade_stock_daily` |

微盘股筛选条件：流通市值 < 50 亿，60日均成交额 >= 1000 万，价格 > MA20，排除 ST。

#### 4. Celery 定时任务 (M2)

| 任务 | 时间 | 功能 |
|------|------|------|
| `fill_entry_prices` | 工作日 09:35 | T+1 填充买入价 |
| `daily_sim_pool_update` | 工作日 16:30 | 价格更新 -> 退出检查 -> 净值计算 -> 报告生成 -> 周报(周五) -> 关闭(全部退出) |

`create_sim_pool_task` 由 API 端点异步触发，不在 Beat 调度中。

#### 5. 报告生成 (M3)

`ReportGenerator` 复用 `strategist.backtest.metrics.MetricsCalculator`，生成三种报告：
- **日报**: 每日生成，包含累计收益/年化/回撤/Sharpe 等指标
- **周报**: 周五生成，统计本周一到周五的绩效
- **终报**: 池子关闭后生成，额外包含每只股贡献度排名和退出原因分布

#### 6. REST API (M3)

9 个端点，注册在 `/api/sim-pool`：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 池子列表（支持 strategy_type/status 过滤） |
| POST | `/` | 创建模拟池（异步，返回 task_id） |
| GET | `/tasks/{task_id}` | 轮询任务状态 |
| GET | `/{id}` | 池子详情 |
| GET | `/{id}/positions` | 持仓列表（支持 status 过滤） |
| GET | `/{id}/nav` | 净值序列 |
| GET | `/{id}/reports` | 报告列表 |
| GET | `/{id}/reports/{date}/{type}` | 报告详情 |
| GET | `/{id}/trades` | 交易日志 |
| POST | `/{id}/close` | 强制关闭 |

#### 7. 前端页面 (M4)

**页面：** `web/src/app/sim-pool/page.tsx`

**功能：**
- 池子列表：卡片式展示，支持策略类型/状态过滤，"创建模拟池"按钮
- 创建弹窗：策略类型选择、交易参数配置、异步任务轮询
- 池子详情 4-Tab：
  - 概览：8 个指标卡片（总收益/年化/超额收益/最大回撤/Sharpe/胜率/盈亏比/均持天数）+ SVG 净值曲线
  - 持仓：表格含退出原因中文标签和颜色，支持 open/exited/all 过滤
  - 报告：日报/周报/终报列表，点击展开 metrics JSON
  - 交易记录：买卖明细表格（价格/数量/手续费/印花税/净金额）
- 强制关闭按钮：仅非 closed 状态显示
- 侧边栏新增"模拟池"导航项

#### 8. 测试 (M5)

41 个测试全部通过（25 单元 + 16 集成）：

| 测试文件 | 数量 | 覆盖 |
|---------|------|------|
| `test_pool_manager.py` | 5 | 创建/等权/max_positions/过滤/关闭 |
| `test_position_tracker.py` | 7 | 买入成本/止损/止盈/到期/不触发/印花税/停牌 |
| `test_nav_calculator.py` | 4 | NAV=1/价格上涨/回撤计算/基准净值 |
| `test_report_generator.py` | 4 | 日报字段/终报退出分布/终报贡献度/周报区间 |
| `test_strategy_adapters.py` | 5 | 抽象类/动量DataFrame/meta序列化/行业过滤/市值过滤 |
| `test_full_lifecycle.py` | 4 | 完整生命周期/止损/止盈/到期 |
| `test_api_endpoints.py` | 12 | 列表/详情/持仓/净值/交易/关闭/报告/无效策略 |

---

### 修改的文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `strategist/sim_pool/` (12 文件) | 新增 | 核心引擎 + 策略适配器 |
| `api/tasks/sim_pool_tasks.py` | 新增 | 3 个 Celery 任务 |
| `api/services/sim_pool_service.py` | 新增 | 服务层 |
| `api/routers/sim_pool.py` | 新增 | 9 个 REST 端点 |
| `api/main.py` | 修改 | 注册 sim_pool router |
| `api/tasks/__init__.py` | 修改 | 注册 sim_pool_tasks |
| `api/tasks/celery_app.py` | 修改 | 添加 2 个 Beat 调度 |
| `web/src/app/sim-pool/page.tsx` | 新增 | 前端页面 |
| `web/src/components/layout/AppShell.tsx` | 修改 | 添加导航项 |
| `tests/unit/sim_pool/` (5 文件) | 新增 | 单元测试 |
| `tests/integration/sim_pool/` (2 文件) | 新增 | 集成测试 |
| `docs/sim_pool_design.md` | 新增 | 系统设计文档 |
| `docs/sim_pool_tasks.md` | 新增 | 任务拆分文档 |

### 相关 Git 提交

```
13c3ec9 feat: implement Strategy Simulation Pool (SimPool) system
612a1b1 docs: add sim_pool system design and task breakdown
```

---

### 待解决问题

1. **线上建表**：需在 API 容器内执行 `ensure_tables(env='online')` 创建 5 张 sim_pool 相关表
2. **端到端验证**：实际创建一个动量策略模拟池，观察 T+1 买入和后续每日更新流程
3. **Celery Beat 更新**：重启 Celery worker 以加载新的 Beat 调度配置

---

*文档维护：每次开发后更新此文件，新日期追加在上方*

---

## 2026-04-14 大盘总览 Dashboard Phase 1 数据补全与性能优化

### 今日工作内容

#### 1. 数据管道补全

Dashboard 部署到线上后发现 6 个板块大量指标为空，根本原因是数据管道未在线上执行过。

**数据管道现状梳理：**

| 管道 | 功能 | 状态 |
|------|------|------|
| `macro_fetcher` | 指数序列、QVIX、北向资金、国债、PMI、M2、AH溢价 | 首次执行，补全 25 个指标 13,443 条记录 |
| `dashboard fetcher` | 成交额、涨跌家数、涨跌停、融资、创新高低 | 补全 60 天历史数据 |
| `sentiment fear_index` | VIX/OVX/GVZ 恐慌指数 | 存在异常（VIX=0.0），待排查 |

#### 2. AKShare 云服务器 IP 限流问题

**问题：** `index_zh_a_hist`（东财 Web 接口）在阿里云服务器上被封，所有指数日线数据拉取失败。

**解决方案：** 修改 `macro_fetcher.py` 中的 `fetch_index_daily` 函数，添加三级回退机制：

```
index_zh_a_hist (东财 Web) -> stock_zh_index_daily_em (东财 App) -> stock_zh_index_daily (新浪)
```

stock_zh_index_daily_em 在云服务器可用，成功拉取了 CSI300/CSI500/CSI1000 等 7 个核心指数 549 天数据。

**仍不可用的指数（接口均被封）：**
- `idx_growth300`（沪深300成长，000918）-- 导致风格板块 style.direction=unknown
- `idx_equity_fund`（偏股混合基金指数，885001）
- `idx_hk_dividend`（港股通高股息，930914）

#### 3. 成交额数据修正

**问题：** `stock_zh_index_daily(symbol="sh000001")` 返回的 volume 字段是**成交量（股数）**，不是**成交额（元）**。导致页面显示"成交额 546 亿"（实际应为 2.15 万亿）。

**解决方案：** 修改 `fetcher.py` 中的 `fetch_market_volume`：
- 主方案：使用 `stock_sse_deal_daily`（上交所）+ `stock_szse_summary`（深交所）获取两市真实成交额
- 回退方案：使用新浪接口的 volume（股数，精度较低）
- 回填 60 个交易日的历史数据

修正后：4月13日成交额 = SSE 9203亿 + SZSE 12318亿 = **21522 亿元**

#### 4. 性能优化（122s -> 2.8s）

**问题：** Dashboard API 首次请求耗时 122 秒，原因是 `calc_temperature` 中调用 `calc_market_turnover()`，该函数对 `trade_stock_daily` 表执行 `AVG(turnover_rate) ... GROUP BY trade_date ... INTERVAL 400 DAY` 全表扫描，在线上大表上极其缓慢甚至触发 OOM。

**解决方案：** 移除对 `trade_stock_daily` 的依赖，改用 `macro_data.market_volume` 的分位数排名计算成交量活跃度。

**效果：**
- 冷计算：122s -> 2.8s（43x 提升）
- 缓存命中：< 0.1s

#### 5. 日期显示修正

**问题：** `updated_at` 使用 `date.today()` 显示为 2026-04-14（非交易日），应显示最近交易日。

**解决方案：** 新增 `_get_latest_trade_date()` 从 `macro_data` 表查询 `idx_csi300` 的最新日期。

#### 6. MA 阈值修正

**问题：** 趋势板块要求 `len(csi300) >= 250` 个交易日，但 `_load_macro` 用 `days=300` 自然日回溯只能获取约 199 个交易日。

**解决方案：**
- `_load_macro` 的 `days` 参数从 300 改为 500
- MA 最低要求从 250 降为 60（MA250 在数据不足时设为 None）

---

### 修改的文件

| 文件 | 改动说明 |
|------|---------|
| `data_analyst/fetchers/macro_fetcher.py` | fetch_index_daily 三级回退；默认起始日期改为 2024-01-01 |
| `data_analyst/market_dashboard/calculator.py` | 移除 trade_stock_daily 查询；MA 阈值放宽；updated_at 取最近交易日 |
| `data_analyst/market_dashboard/fetcher.py` | fetch_market_volume 改用交易所成交额 API |

### 相关 Git 提交

```
ac34a6c fix: market_volume use turnover amount (yuan) instead of shares
3c2de70 perf: replace slow trade_stock_daily query with macro_data volume
6eaeeb8 fix: dashboard trend section require 60+ days instead of 250+
fcf9dba fix: macro_fetcher index fallback to stock_zh_index_daily_em
```

---

### 当前 Dashboard 数据状态

| 板块 | 等级 | 关键指标 | 完整度 |
|------|------|---------|--------|
| 温度 | 常温 (score=45) | 成交额 21522 亿, 量比 1.04, 分位 37.1%, 涨停 59/跌停 4 | 5/7 |
| 趋势 | 震荡蓄势 | MA5/20/250 上方, MA60 下方, MACD 零轴下收敛, ADX=23.4 | 5/6 |
| 情绪 | 中性 (score=49) | QVIX=15.94, 北向-67.75 亿, 创新高 130/低 49 | 5/7 |
| 风格 | scale=均衡 | 大小盘中性, style 数据不足 | 部分 |
| 股债 | 股票吸引力强 | 19 点序列 | 完整 |
| 宏观 | 顺风 (score=2) | PMI=50.4(扩张), AH 溢价=11.51(低) | 4/6 |

---

### 待解决问题

#### P0 - 需尽快修复

1. **`advance_decline`（涨跌家数）缺失**
   - 原因：`stock_zh_a_spot_em`（东财 EM 接口）在云服务器被封
   - 方案：可用 `stock_market_activity_legu`（乐股网）替代，该接口已验证可用且返回涨跌家数
   - 影响：温度板块缺少涨跌家数比

2. **`trade_fear_index` VIX=0.0 异常**
   - 原因：sentiment 模块的 fear_index 数据写入异常，VIX 值为 0
   - 方案：排查 `data_analyst/sentiment/fear_index.py` 的数据拉取逻辑
   - 影响：情绪和宏观板块的 VIX 指标不准确

3. **`idx_growth300`（沪深300成长）不可用**
   - 原因：三个 AKShare 接口均在云服务器被封
   - 方案 A：找替代指数（如 399370 国证成长）
   - 方案 B：用创业板指（399006）代替成长风格
   - 影响：风格板块 style.direction 显示"数据不足"

#### P1 - 短期优化

4. **`margin_change_5d` 为空**
   - 原因：融资数据只有 1 天（刚开始采集），需积累 5 天以上
   - 方案：自然积累，每日执行 dashboard fetcher 即可
   - 预计：5 个交易日后自动解决

5. **`m2_yoy` 最新值为空**
   - 原因：AKShare 的 M2 数据滞后，目前只到 2025-09
   - 方案：这是数据源本身的滞后性，月度数据正常延迟 1-2 个月

6. **`svd` 状态 unknown**
   - 原因：线上数据库没有 `trade_svd_market_state` 表
   - 方案：在线上执行 SVD 模块的数据回填，或忽略该指标

7. **定时任务未配置**
   - dashboard fetcher 和 macro_fetcher 尚未加入每日调度
   - 需要添加到 `tasks/` YAML 配置中

#### P2 - 中期改进

8. **前端 UI 优化**
   - 信号卡片的数据展示需根据实际数据调整布局
   - Sparkline 图表需验证视觉效果
   - 移动端适配

9. **信号变化日志（signal_log）为空**
   - 需要实现每日计算结果的持久化和 diff 比较逻辑
   - 存储每日各板块 level 变化记录

10. **API 缓存刷新机制**
    - 当前 Redis 缓存 6 小时 TTL
    - 需要在每日数据更新后主动刷新缓存

---

### 技术总结

**AKShare 在云服务器的可用性矩阵：**

| 接口 | 数据源 | 云服务器可用 | 备注 |
|------|--------|:---:|------|
| `stock_zh_index_daily` | 新浪 | YES | 只有 volume（股数），无成交额 |
| `stock_zh_index_daily_em` | 东财 App | YES | 大部分指数可用 |
| `index_zh_a_hist` | 东财 Web | NO | IP 被封 |
| `stock_zh_a_spot_em` | 东财 EM | NO | IP 被封 |
| `stock_sse_deal_daily` | 上交所 | YES | 成交额、换手率等 |
| `stock_szse_summary` | 深交所 | YES | 成交额、市值等 |
| `stock_market_activity_legu` | 乐股 | YES | 涨跌家数、涨停数 |
| `index_option_50etf_qvix` | 东财 | YES | 中国波指 |
| `stock_hsgt_hist_em` | 东财 EM | YES | 北向资金 |
| `bond_zh_us_rate` | 东财 | YES | 国债收益率 |
| `macro_china_pmi` | 东财 | YES | PMI 数据 |
| `stock_zt_pool_em` | 东财 EM | YES | 涨停池 |

**经验教训：**
- 云服务器使用 AKShare 必须有备用接口，东财 Web 端接口限制最严格
- `stock_zh_index_daily` 的 volume 字段是股数不是金额，需要用交易所官方接口获取成交额
- 对大表（如 trade_stock_daily）的聚合查询不适合放在实时 API 中，应预计算存入 macro_data
- `_load_macro(days=N)` 的 `N` 是自然日，转换为交易日约乘以 250/365

---

*文档维护：每次开发后更新此文件，新日期追加在上方*

---

## 2026-04-14 策略系统重构与数据完备性监控

### 今日工作内容

#### 1. 预设策略从 Threading 迁移到 Celery

**问题：** 之前使用 threading 执行策略任务，微盘股策略卡住（运行6小时+），无法监控和重试。

**解决方案：**
- 创建 `/root/app/api/tasks/celery_app.py` 配置 Celery Beat 定时任务
- 修改 `/root/app/api/tasks/preset_strategies.py` 使用 Celery 任务
- 添加 `_get_recent_occurrence_counts()` 统计5日出现次数

**定时任务配置：**
```python
'watchlist-scan': '0 16:30 * * 1-5'      # 工作日 16:30 扫描自选股
'preset-strategies': '0 19:30 * * 1-5'  # 工作日 19:30 运行预设策略
'log-bias-daily': '0 16:00 * * 1-5'     # 工作日 16:00 对数乖离率
```

#### 2. 策略日期逻辑修复

**问题：** 策略使用 `date.today()` 作为日期，导致盘后运行时日期不匹配。

**解决：** 从数据库查询最新交易日期：
```python
trade_date_rows = execute_query(
    "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily WHERE ..."
)
trade_date_str = str(trade_date_rows[0]['max_date'])
```

#### 3. 动量反转策略5日出现次数统计

**功能：** 显示每只股票在最近5日内的出现次数，便于识别频繁信号股票。

**实现：**
- 后端：`_get_recent_occurrence_counts(stock_codes, days=5)`
- 前端：策略信号表格新增"5日出现"列
- 颜色标识：≥3次红色，≥2次橙色
- 已回填历史数据（04-12、04-13）

#### 4. 数据完备性检查系统

**问题：** 各数据表状态未知，缺少监控。

**解决方案：**
- 创建 `scheduler/check_data_completeness.py` 每日检查脚本
- 新建 `trade_data_health` 表存储检查历史
- API 端点：
  - `GET /api/analysis/health-check/latest` - 最新检查结果
  - `GET /api/analysis/health-check/summary` - 状态摘要
  - `POST /api/analysis/health-check/run` - 手动触发检查

**检查状态分类：**
| 状态 | 含义 |
|------|------|
| ok | 数据正常 |
| warning | 数据滞后1-3天 |
| critical | 数据滞后>3天 |
| empty | 空表 |

#### 5. 前端修复

**问题修复：**
- 统一 API 环境变量：`NEXT_PUBLIC_API_URL` → `NEXT_PUBLIC_API_BASE_URL`
- 修复搜索接口指向 localhost 的问题
- 隐藏组合管理入口（暂时）

#### 6. Docker 部署问题修复

**问题1：** uvicorn 找不到
```
exec: "uvicorn": executable file not found in PATH
```
**原因：** `-v /root/app/.pip_cache:/root/.local` 覆盖了镜像中的依赖
**解决：** 移除该卷挂载

**问题2：** RAG_API_KEY 未配置
**解决：** 配置 DashScope API Key 到环境变量

#### 7. 数据完备性检查结果

| 数据表 | 记录数 | 最新日期 | 状态 |
|--------|--------|----------|------|
| trade_stock_daily | 662万+ | 2026-04-13 | ✅ OK |
| trade_stock_daily_basic | 567万+ | 2026-04-10 | ⚠️ 滞后3天 |
| trade_stock_rps | 658万+ | 2026-03-31 | 🔴 滞后13天 |
| trade_log_bias_daily | 3,180 | 2026-04-10 | ⚠️ 滞后3天 |
| financial_income | 0 | - | ❌ 空表 |
| financial_balance | 0 | - | ❌ 空表 |
| financial_dividend | 0 | - | ❌ 空表 |

**待办事项：**
- [x] 下载财务数据（一页纸研报需要）
- [x] 更新 daily_basic 数据
- [x] 更新 RPS 数据
- [x] 更新 extended_factor 数据

---

## 2026-04-14 数据完备度页面 + 因子补算 + OOM 修复

### 今日工作内容

#### 1. 数据完备度检查页面 `/data-health`

新增数据完备度可视化页面，展示各数据维度的最新更新时间、距今天数和记录数。

**后端 (`GET /api/admin/data-health`)：**
- 查询 16 个数据维度，按分组展示（行情/因子/财务/资金/情绪/宏观/策略）
- 不暴露表名，使用友好描述
- 状态判断：正常(绿点)/偏旧(黄点)/异常(红点)
- 无需登录即可访问（方便快速检查）

**前端 (`/data-health`)：**
- 紧凑表格布局，分组标题行
- 状态圆点 + 等宽字体日期 + 距今标签
- 每2分钟自动刷新

#### 2. 数据补算

发现多个数据表严重滞后，逐一补算：

| 数据 | 补算前 | 补算后 | 方式 |
|------|--------|--------|------|
| A股每日指标 | 4月10日 (1586只) | 4月13日 (5199只) | AKShare `daily_basic_history_fetcher` |
| 基础量价因子 | 3月22日 | 4月13日 (5171只) | `basic_factor_calculator --backfill` |
| 扩展因子 | 3月23日 | 4月13日 (4707只) | `extended_factor_calculator --start` |

#### 3. 因子回填 OOM 修复

**问题：** `basic_factor_calculator.backfill_factors()` 一次性加载全量K线数据（5000只 x 3年），导致 ECS 3.6G RAM + 4G Swap OOM 崩溃。

**修复：** 改为分批模式，每批500只股票，加载该批数据 -> 计算因子 -> 保存 -> 释放内存 -> 下一批。内存峰值从 4GB+ 降至约 200MB。

同步为 `extended_factor_calculator` 添加 `--start`/`--end` 命令行参数，支持指定回填范围。

#### 4. 各数据维度使用情况梳理

| 数据 | 使用方 |
|------|--------|
| 基础量价因子 | strategist 本地回测（doctor_tao/multi_factor），API 未直接使用 |
| 扩展因子 | `analysis_service` 个股基本面分析、`theme_pool_score` 主题评分（ROE/利润增长） |
| A股每日指标 | doctor_tao/multi_factor/microcap 策略（市值过滤/PE筛选）、research_pipeline |

---

*文档维护：每次开发后更新此文件，新日期追加在上方*
